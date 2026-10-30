#!/usr/bin/env python3
"""Offline artifact/review regressions; synthetic files are not Golden evidence."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

import verify_physical_media_goldens as golden  # noqa: E402

VISUAL_SUMMARY = "初見が入ったら短く挨拶し、今の話題を一言添えてコメントしやすい入口を作る。"
ITEM = {"account_id": "liver_manager", "source_id": "registered", "source_handle": "@owner",
        "url": "https://x.com/owner/status/123456"}
REGISTRY = [{"source_id": "registered", "source_platform": "x", "source_handle": "@owner",
             "source_url": "https://x.com/owner", "active": True,
             "target_account_ids": ["liver_manager"]}]
METADATA = {"id": "separate-media-id", "display_id": "123456", "webpage_url": ITEM["url"],
            "uploader_id": "owner", "description": "配信者が初見のコメントへ挨拶を返す。",
            "formats": [{"vcodec": "h264"}]}
PROBE = {"video_stream_count": 1, "audio_stream_count": 1, "width": 1280,
         "height": 720, "duration_seconds": 30.0}
PERMISSION = {
    "source_id": "registered", "source_handle": "owner", "account_id": "liver_manager",
    "allowed_accounts": ["liver_manager"], "rights_status": "approved_creator_clip",
    "permission_status": "approved", "usage_mode": "direct_and_clip",
    "evidence_type": "owner_attestation", "evidence_reference": "offline-fixture",
    "approved_by": "fixture", "approved_at": "2026-10-30T00:00:00+09:00", "revoked": False,
    **{flag: True for flag in ("allow_download", "allow_cloudinary_storage", "allow_original_repost", "allow_new_caption")},
}


def understanding(data: bytes, *, account_id: str = "liver_manager", summary: str = VISUAL_SUMMARY) -> dict:
    digest = hashlib.sha256(data).hexdigest()
    asset_id = f"ma_{digest[:24]}"
    return {
        "schema_version": 1, "account_id": account_id, "source_id": ITEM["source_id"],
        "canonical_url": ITEM["url"], "external_post_id": "123456",
        "media_asset_id": asset_id, "content_hash": digest,
        "analysis": {
            "status": "PASS", "vision_status": "PASS", "provider": "gemini",
            "visual_summary": summary, "visible_action": "初見のコメントへ挨拶を返す。",
            "key_moment": "配信者がコメントを読み上げ、短い挨拶を返す場面。",
            "http_status": 200, "response_schema_status": "PASS",
            "visual_facts": [{"id": "VF1", "type": "visible_action", "text": "初見へ挨拶を返す。"}],
            "visual_evidence": {
                "status": "UNDERSTOOD", "provider": "gemini", "frame_hashes": ["a" * 64],
                "content_hash": digest, "media_asset_id": asset_id,
            },
        },
    }


class PhysicalGoldenEvidenceIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.path = self.directory / "owner_123456.mp4"
        self.data = b"synthetic video fixture; ffprobe is mocked, never production evidence"
        self.path.write_bytes(self.data)
        self.write_json(self.path.with_suffix(".info.json"), METADATA)
        self.write_json(self.path.with_suffix(".understanding.json"), understanding(self.data))

    @staticmethod
    def write_json(path: Path, value: dict) -> None:
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def verify(self, *, item=None, registry=None, permissions=None, probe=None):
        with patch.object(golden, "probe_media_streams", return_value=deepcopy(PROBE if probe is None else probe)):
            return golden.verify_item(
                ITEM if item is None else item, None, {},
                [PERMISSION] if permissions is None else permissions,
                registry_rows=REGISTRY if registry is None else registry, directories=[self.directory],
            )

    def assert_blocked(self, result):
        self.assertEqual(result["queue_status"], "BLOCKED", result)
        self.assertFalse(result["publisher_eligible"], result)

    def test_complete_evidence_and_actual_local_composer_reach_human_review_only(self):
        result = self.verify()
        self.assertEqual(result["queue_status"], "WAITING_REVIEW", result)
        self.assertEqual(result["content_hash"], hashlib.sha256(self.data).hexdigest())
        self.assertEqual(result["content_understanding"], "PASS")
        self.assertEqual(result["generation_quality"], "PASS")
        self.assertEqual(result["media_text_quality"], "PASS")
        self.assertFalse(result["publisher_eligible"])
        self.assertTrue(result["preserve_source"])

    def test_valid_av_and_manifest_summary_without_semantic_proof_are_blocked(self):
        self.path.with_suffix(".understanding.json").unlink()
        with patch.object(golden, "generate_production_post", side_effect=AssertionError("no generation")):
            result = self.verify(item={**ITEM, "source_text": "manifest fallback summary"})
        self.assertEqual(result["technical_bytes"], "PASS")
        self.assertEqual(result["content_understanding"], "BLOCKED")
        self.assert_blocked(result)

    def test_changed_actual_bytes_cannot_inherit_stale_understanding(self):
        self.path.write_bytes(b"different actual bytes")
        result = self.verify()
        self.assertEqual(result["technical_bytes"], "PASS")
        self.assertEqual(result["content_understanding"], "BLOCKED")
        self.assert_blocked(result)

    def test_other_post_same_author_prefix_id_and_author_only_names_do_not_match(self):
        for name in ("owner_999999.mp4", "owner_1234567.mp4", "owner.mp4"):
            with self.subTest(name=name):
                alternate = self.path.with_name(name)
                self.path.rename(alternate)
                try:
                    result = self.verify()
                    self.assertEqual(result["artifact_binding"], "BLOCKED")
                    self.assert_blocked(result)
                finally:
                    alternate.rename(self.path)

    def test_duplicate_exact_post_artifacts_are_ambiguous(self):
        duplicate = self.directory / "other_123456.mp4"
        duplicate.write_bytes(self.data)
        self.write_json(duplicate.with_suffix(".info.json"), METADATA)
        result = self.verify()
        self.assertEqual(result["artifact_binding"], "BLOCKED")
        self.assert_blocked(result)

    def test_sidecar_with_different_basename_is_not_paired(self):
        sidecar = self.path.with_suffix(".info.json")
        sidecar.rename(self.directory / "other_123456.info.json")
        self.assertEqual(self.verify()["artifact_binding"], "BLOCKED")

    def test_missing_wrong_and_request_echo_metadata_are_blocked(self):
        for metadata in ({"formats": METADATA["formats"]},
                         {"webpage_url": ITEM["url"], "formats": METADATA["formats"]},
                         {**METADATA, "display_id": "999999"},
                         {**METADATA, "uploader_id": "other_author"}):
            with self.subTest(metadata=metadata):
                self.write_json(self.path.with_suffix(".info.json"), metadata)
                result = self.verify()
                self.assertEqual(result["artifact_binding"], "BLOCKED")
                self.assert_blocked(result)

    def test_symlink_video_or_metadata_cannot_be_read_as_evidence(self):
        for path in (self.path, self.path.with_suffix(".info.json")):
            with self.subTest(path=path.name):
                target = path.with_name("target-" + path.name)
                path.rename(target)
                path.symlink_to(target)
                try:
                    self.assertEqual(self.verify()["artifact_binding"], "BLOCKED")
                finally:
                    path.unlink()
                    target.rename(path)

    def test_symlink_semantic_sidecar_cannot_prove_understanding(self):
        sidecar = self.path.with_suffix(".understanding.json")
        target = sidecar.with_name("target-proof.json")
        sidecar.rename(target)
        sidecar.symlink_to(target)
        result = self.verify()
        self.assert_blocked(result)
        self.assertNotEqual(result["content_understanding"], "PASS")

    def test_missing_permission_and_latest_revocation_remain_blocked(self):
        revoked = {**PERMISSION, "revoked": True, "approved_at": "2026-10-30T01:00:00+09:00"}
        for permissions in ([], [PERMISSION, revoked], [revoked, PERMISSION]):
            with self.subTest(permissions=permissions):
                result = self.verify(permissions=permissions)
                self.assertEqual(result["effective_permission"], "BLOCKED")
                self.assert_blocked(result)

    def test_unscoped_or_other_account_permission_cannot_be_promoted(self):
        for row in ({**PERMISSION, "account_id": "", "allowed_accounts": ""},
                    {**PERMISSION, "account_id": "night_scout"},
                    {**PERMISSION, "allowed_accounts": ["night_scout"]}):
            with self.subTest(row=row):
                result = self.verify(permissions=[row])
                self.assertEqual(result["effective_permission"], "BLOCKED")
                self.assert_blocked(result)

    def test_missing_required_operation_flag_remains_blocked(self):
        for flag in ("allow_download", "allow_cloudinary_storage", "allow_original_repost", "allow_new_caption"):
            with self.subTest(flag=flag):
                result = self.verify(permissions=[{**PERMISSION, flag: False}])
                self.assertEqual(result["effective_permission"], "BLOCKED")
                self.assert_blocked(result)

    def test_unregistered_inactive_and_duplicate_source_block_before_probe(self):
        for registry in ([], [{**REGISTRY[0], "active": False}], REGISTRY + REGISTRY):
            with self.subTest(registry=registry), \
                    patch.object(golden, "probe_media_streams", side_effect=AssertionError("no probe")):
                result = golden.verify_item(ITEM, self.path, METADATA, [PERMISSION], registry_rows=registry)
            self.assertEqual(result["registered_source"], "BLOCKED")
            self.assert_blocked(result)

    def test_probe_exception_is_returned_as_blocked(self):
        with patch.object(golden, "probe_media_streams", side_effect=subprocess.CalledProcessError(1, "ffprobe")):
            result = golden.verify_item(ITEM, self.path, METADATA, [PERMISSION], registry_rows=REGISTRY)
        self.assertEqual(result["technical_bytes"], "BLOCKED")
        self.assert_blocked(result)

    def test_probe_timeout_is_bounded_and_returned_as_blocked(self):
        with patch.object(golden, "probe_media_streams", side_effect=subprocess.TimeoutExpired("ffprobe", 30)) as probe:
            result = golden.verify_item(ITEM, self.path, METADATA, [PERMISSION], registry_rows=REGISTRY)
        probe.assert_called_once_with(self.path, timeout_seconds=30)
        self.assertEqual(result["technical_bytes"], "BLOCKED")
        self.assert_blocked(result)

    def test_nonfinite_duration_missing_audio_or_invalid_geometry_are_blocked(self):
        for change in ({"duration_seconds": float("nan")}, {"duration_seconds": float("inf")},
                       {"duration_seconds": 0}, {"audio_stream_count": 0},
                       {"width": 0}, {"video_stream_count": 0}):
            with self.subTest(change=change):
                result = self.verify(probe={**PROBE, **change})
                self.assertEqual(result["technical_bytes"], "BLOCKED")
                self.assert_blocked(result)

    def test_quality_blocked_or_blocked_reason_cannot_pass_other_validators(self):
        original = golden.generate_production_post
        for extra in ({"generation_quality": {"status": "BLOCKED"}, "blocked_reasons": ["GENERATION_QUALITY_BLOCKED"]},
                      {"generation_quality": {"status": "PASS"}, "blocked_reasons": ["another_gate"]},
                      {"generation_quality": None, "blocked_reasons": []}):
            def compose(*args, **kwargs):
                return {**original(*args, **kwargs), **extra}
            with self.subTest(extra=extra), patch.object(golden, "generate_production_post", side_effect=compose):
                result = self.verify()
            self.assertEqual(result["persona_generation"], "PASS")
            self.assertEqual(result["public_validation"], "PASS")
            self.assertEqual(result["generation_quality"], "BLOCKED")
            self.assert_blocked(result)

    def test_actual_local_night_composer_quality_failure_remains_blocked(self):
        item = {**ITEM, "account_id": "night_scout"}
        registry = [{**REGISTRY[0], "target_account_ids": ["night_scout"]}]
        self.write_json(self.path.with_suffix(".understanding.json"), understanding(
            self.data, account_id="night_scout", summary="配信の始めに笑顔で挨拶し初見のコメントを拾う。"))
        result = self.verify(item=item, registry=registry, permissions=[{
            **PERMISSION, "account_id": "night_scout", "allowed_accounts": ["night_scout"]}])
        self.assertEqual(result["persona_generation"], "PASS")
        self.assertEqual(result["public_validation"], "PASS")
        self.assertEqual(result["generation_quality"], "BLOCKED")
        self.assert_blocked(result)

    def test_strict_registry_load_preserves_ambiguity_instead_of_deduplicating(self):
        path = self.directory / "registry.json"
        self.write_json(path, {"sources": REGISTRY + REGISTRY})
        self.assertEqual(len(golden.load_registry(str(path))), 1)
        strict = golden.load_registry(str(path), preserve_duplicates=True)
        self.assertEqual(len(strict), 2)
        self.assertEqual(self.verify(registry=strict)["registered_source"], "BLOCKED")

    def test_video_changed_during_probe_invalidates_prior_hash(self):
        def mutate(*_args, **_kwargs):
            self.path.write_bytes(b"mutated during probe")
            return deepcopy(PROBE)
        with patch.object(golden, "probe_media_streams", side_effect=mutate):
            result = golden.verify_item(ITEM, self.path, METADATA, [PERMISSION], registry_rows=REGISTRY)
        self.assertEqual(result["technical_bytes"], "BLOCKED")
        self.assert_blocked(result)

    def test_metadata_changed_after_selection_is_not_trusted(self):
        original = golden.select_artifact
        def select_and_mutate(*args, **kwargs):
            bundle = original(*args, **kwargs)
            self.write_json(self.path.with_suffix(".info.json"), {**METADATA, "uploader_id": "other_author"})
            return bundle
        with patch.object(golden, "select_artifact", side_effect=select_and_mutate):
            result = self.verify()
        self.assertEqual(result["technical_bytes"], "BLOCKED")
        self.assert_blocked(result)

    def test_inplace_metadata_rewrite_with_restored_mtime_is_detected(self):
        sidecar = self.path.with_suffix(".info.json")
        before = sidecar.stat()
        original = golden._hash_video
        def hash_then_mutate(path):
            digest = original(path)
            self.write_json(sidecar, {**METADATA, "uploader_id": "other"})
            os.utime(sidecar, ns=(before.st_atime_ns, before.st_mtime_ns))
            return digest
        with patch.object(golden, "_hash_video", side_effect=hash_then_mutate):
            result = self.verify()
        self.assertEqual(result["technical_bytes"], "BLOCKED")
        self.assert_blocked(result)


if __name__ == "__main__":
    unittest.main()
