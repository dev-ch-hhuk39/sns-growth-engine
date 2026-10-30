#!/usr/bin/env python3
"""Offline ingest/selection integration using the real private evidence store."""
from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
from tempfile import TemporaryDirectory
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

import ingest_direct_reference_media as ingest  # noqa: E402
import run_direct_reference_media_pipeline as pipeline  # noqa: E402
from generation.content_quality_v2 import prepare_media_context  # noqa: E402
from media import understanding_evidence_store as store  # noqa: E402
from sheets_client import TAB_DEFINITIONS  # noqa: E402

ACCOUNT = "liver_manager"
DATA = b"0000ftypoffline-fixture-video-without-real-provider-or-media"
DIGEST = hashlib.sha256(DATA).hexdigest()
URL = "https://x.com/registered_owner/status/123456789"
SOURCE = {"source_id": "registered_source", "source_platform": "x", "source_handle": "@registered_owner",
          "source_url": "https://x.com/registered_owner", "active": True, "target_account_ids": [ACCOUNT],
          "rights_status": "approved_creator_clip", "permission_status": "approved",
          "permission_scope": sorted(pipeline.DIRECT_SCOPE), "media_usage_mode": "direct_media_reuse"}
POST = {"source_post_id": "post_one", "source_id": SOURCE["source_id"], "target_account_id": ACCOUNT,
        "platform": "x", "author_handle": "registered_owner", "canonical_post_url": URL,
        "external_post_id": "123456789", "original_post_text": "初見のコメントへ挨拶を返す配信。",
        "rights_status": "approved_creator_clip", "permission_status": "approved",
        "permission_scope": sorted(pipeline.DIRECT_SCOPE)}
PERMISSION = {"source_id": SOURCE["source_id"], "source_handle": "registered_owner", "account_id": ACCOUNT,
              "allowed_accounts": [ACCOUNT], "rights_status": "approved_creator_clip",
              "permission_status": "approved", "usage_mode": "direct_media_reuse", "evidence_type": "owner_attestation",
              "evidence_reference": "offline-fixture", "approved_by": "fixture", "approved_at": "2026-10-30T00:00:00+09:00",
              "revoked": False, **{flag: True for flag in (
                  "allow_download", "allow_cloudinary_storage", "allow_original_repost", "allow_new_caption", "allow_analysis")}}


def analysis_for(path: Path, *, media_asset_id: str, **_kwargs):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"status": "PASS", "aggregate_status": "PASS_VISION", "provider": "gemini", "vision_status": "PASS",
            "http_status": 200, "response_schema_status": "PASS", "visual_summary": "初見のコメントへ短い挨拶を返す。",
            "visible_action": "コメントへ挨拶する", "key_moment": "初見のコメントへ挨拶を返す場面。",
            "visual_facts": [{"id": "VF1", "type": "visible_action", "text": "初見のコメントへ挨拶を返す。"}],
            "transcript_status": "UNAVAILABLE", "transcript_text": "", "transcription_provider": "offline_fixture",
            "representative_frame_count": "1", "visual_evidence": {"status": "UNDERSTOOD", "provider": "gemini",
                "content_hash": digest, "media_asset_id": media_asset_id, "frame_hashes": ["a" * 64]}}


class Worksheet:
    def __init__(self, client, logical):
        self.client, self.logical = client, logical
        self.headers = list(TAB_DEFINITIONS[logical])

    def row_values(self, number):
        if number != 1:
            raise AssertionError("fixture only reads headers")
        return list(self.headers)

    def get_all_records(self):
        return deepcopy(self.client.rows.get(self.logical, []))

    def append_row(self, values, **_kwargs):
        self.client.events.append(("write", self.logical))
        self.client.rows.setdefault(self.logical, []).append(dict(zip(self.headers, values)))

    def batch_update(self, updates, **_kwargs):
        self.client.events.append(("write", self.logical))
        for update in updates:
            match = re.match(r"([A-Z]+)([0-9]+)", update["range"])
            if not match:
                raise AssertionError(update)
            column = 0
            for char in match[1]:
                column = column * 26 + ord(char) - ord("A") + 1
            row = self.client.rows[self.logical][int(match[2]) - 2]
            for offset, value in enumerate(update["values"][0]):
                row[self.headers[column - 1 + offset]] = value


class Client:
    def __init__(self, *, uploaded: bool):
        self.events = []
        self.rows = {
            "source_accounts": [deepcopy(SOURCE)], "reference_sources": [], "source_posts": [deepcopy(POST)],
            "source_post_media": [{"source_post_media_id": "spm_one", "source_post_id": "post_one", "media_index": "0",
                "media_type": "video", "original_media_url": URL, "canonical_post_url": URL,
                "media_asset_id": "legacy_custom_asset" if uploaded else "", "content_hash": DIGEST if uploaded else "",
                "cloudinary_status": "UPLOADED" if uploaded else "", "download_status": "DOWNLOADED" if uploaded else "PENDING",
                "storage_url": "https://res.cloudinary.com/offline/video/upload/original.mp4" if uploaded else "",
                "duration_seconds": "20", "width": "1280", "height": "720", "aspect_ratio": "16:9"}],
            "source_media_understanding": [{"understanding_id": "smu_spm_one", "source_post_media_id": "spm_one",
                "source_post_id": "post_one", "account_id": ACCOUNT, "status": "PASS", "content_hash": DIGEST,
                "visual_summary": "legacy summary without raw proof", "transcript_status": ""}] if uploaded else [],
            "media_assets": [{"media_id": "legacy_custom_asset", "account_id": ACCOUNT, "reference_post_id": "post_one",
                "original_media_url": URL, "source_post_url": URL, "source_platform": "x", "media_type": "video",
                "storage_url": "https://res.cloudinary.com/offline/video/upload/original.mp4", "content_hash": DIGEST,
                "duration_seconds": "20", "width": "1280", "height": "720", "upload_status": "UPLOADED",
                "rights_status": "approved_creator_clip", "permission_status": "approved", "reuse_status": "APPROVED"}] if uploaded else [],
            "media_permissions": [deepcopy(PERMISSION)], "posted_results": [], "queue": [],
        }

    def _ws(self, logical):
        return Worksheet(self, logical)

    def _ensure_tab(self, logical, _headers):
        self.rows.setdefault(logical, [])
        return self._ws(logical)

    @staticmethod
    def _call_with_rate_limit_retry(_label, function):
        return function()


class DurableUnderstandingPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name).resolve()
        self.runtime = self.directory / "runtime"
        self.runtime.mkdir(mode=0o700)
        (self.runtime / "shared").mkdir(mode=0o700)
        self.workspace = self.directory / "workspace"
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ, {
            "BUFFERED_RUNTIME_ROOT": str(self.runtime), "SNS_MEDIA_PREP_WORKSPACE": str(self.workspace),
            "ALLOW_LOCAL_TRANSCRIPTION": "true"}))
        self.stack.enter_context(patch.object(store, "load_registry", return_value=[deepcopy(SOURCE)]))
        self.stack.enter_context(patch.object(pipeline, "load_registry", return_value=[deepcopy(SOURCE)]))
        self.stack.enter_context(patch.object(ingest, "safe_https_url", return_value=True))
        self.stack.enter_context(patch("socket.getaddrinfo", side_effect=AssertionError("no DNS/network")))
        self.stack.enter_context(patch("subprocess.run", side_effect=AssertionError("no external process")))
        self.source_download = self.stack.enter_context(patch.object(ingest, "download_source_media", side_effect=self.source_bytes))
        self.stored_download = self.stack.enter_context(patch.object(ingest, "download_direct_https_media", side_effect=self.stored_bytes))
        self.stack.enter_context(patch.object(ingest, "probe_video", return_value={
            "duration_seconds": "20", "width": "1280", "height": "720", "aspect_ratio": "16:9"}))
        self.analysis = self.stack.enter_context(patch.object(ingest, "analyze_local_media", side_effect=analysis_for))
        self.original_upsert = ingest.upsert_media_understanding
        self.upsert = self.stack.enter_context(patch.object(ingest, "upsert_media_understanding", wraps=self.original_upsert))
        self.save = self.stack.enter_context(patch.object(ingest, "save_understanding_evidence", wraps=store.save_understanding_evidence))
        cloudinary = ModuleType("cloudinary")
        cloudinary.__path__ = []
        cloudinary.config = Mock()
        uploader = ModuleType("cloudinary.uploader")
        uploader.upload = Mock(return_value={"secure_url": "https://res.cloudinary.com/offline/video/upload/new.mp4", "public_id": "offline/new"})
        cloudinary.uploader = uploader
        self.upload = uploader.upload
        self.stack.enter_context(patch.dict(sys.modules, {"cloudinary": cloudinary, "cloudinary.uploader": uploader}))

    @staticmethod
    def stored_bytes(_url, path, **_kwargs):
        path.write_bytes(DATA)

    @staticmethod
    def source_bytes(*, path, **_kwargs):
        path.write_bytes(DATA)
        return "offline_fixture"

    def ingest(self, client, **kwargs):
        return ingest.ingest_one(client, client.rows["source_posts"][0], client.rows["source_post_media"][0], **kwargs)

    def receipt(self):
        receipts = list((self.runtime / "shared" / store.STORE_DIRECTORY).glob("*.json"))
        self.assertEqual(len(receipts), 1)
        return receipts[0]

    def select(self, client):
        # The production selector snapshots one invocation; each call below is a fresh invocation.
        if hasattr(client, "_direct_media_records_cache"):
            del client._direct_media_records_cache
        return pipeline.select_direct_candidates(client, ACCOUNT)

    def test_new_ingest_retains_raw_proof_before_summary_persistence_and_upload(self):
        client = Client(uploaded=False)
        def upsert_only_after_durable_readback(current_client, post, media, analysis, *, content_hash):
            retained = store.load_understanding_evidence(self.runtime, post,
                {**media, "media_asset_id": f"ma_{DIGEST[:24]}", "content_hash": DIGEST}, content_hash=DIGEST)
            self.assertEqual(retained["status"], "PASS", retained)
            self.assertEqual(current_client.rows["source_media_understanding"], [])
            return self.original_upsert(current_client, post, media, analysis, content_hash=content_hash)
        self.upsert.side_effect = upsert_only_after_durable_readback
        result = self.ingest(client)
        self.assertEqual(result["status"], "INGESTED", result)
        self.assertEqual(self.analysis.call_args.kwargs["media_asset_id"], f"ma_{DIGEST[:24]}")
        self.source_download.assert_called_once()
        self.stored_download.assert_not_called()
        self.upload.assert_called_once()
        self.assertTrue(self.receipt().is_file())
        summary = client.rows["source_media_understanding"][0]
        self.assertNotIn("visual_evidence", summary)
        candidates, reasons = self.select(client)
        self.assertEqual(len(candidates), 1, reasons)
        self.assertEqual(prepare_media_context(candidates[0][1], account_id=ACCOUNT)["visual_status"], "VISUAL_VERIFIED")

    def test_stored_custom_asset_refresh_preserves_asset_id_and_survives_workspace_cleanup(self):
        client = Client(uploaded=True)
        result = self.ingest(client)
        self.assertEqual(result["status"], "UNDERSTANDING_REFRESHED", result)
        self.assertEqual(self.analysis.call_args.kwargs["media_asset_id"], "legacy_custom_asset")
        self.stored_download.assert_called_once()
        self.source_download.assert_not_called()
        self.upload.assert_not_called()
        self.assertFalse((self.workspace / "direct_media" / "spm_one.mp4").exists())
        shutil.rmtree(self.workspace)
        envelope = json.loads(self.receipt().read_text())
        self.assertEqual(envelope["media_asset_id"], "legacy_custom_asset")
        self.assertEqual(envelope["content_hash"], DIGEST)
        candidates, reasons = self.select(client)
        self.assertEqual(len(candidates), 1, reasons)
        context = prepare_media_context(candidates[0][1], account_id=ACCOUNT)
        self.assertEqual(context["visual_status"], "VISUAL_VERIFIED")
        self.assertEqual(context["visual_evidence"]["media_asset_id"], "legacy_custom_asset")
        self.assertNotEqual(context["visual_summary"], "legacy summary without raw proof")

    def test_changed_stored_hash_rejects_before_analysis_save_or_understanding_upsert(self):
        for changed in ("media", "understanding"):
            with self.subTest(changed=changed):
                client = Client(uploaded=True)
                logical = "source_post_media" if changed == "media" else "source_media_understanding"
                client.rows[logical][0]["content_hash"] = "b" * 64
                result = self.ingest(client)
                self.assertEqual(result["status"], "FAILED", result)
                self.assertIn("content_hash_mismatch", result["reason"])
                self.analysis.assert_not_called()
                self.save.assert_not_called()
                self.upsert.assert_not_called()
                self.upload.assert_not_called()
                self.assertFalse(any(logical == "source_media_understanding" for kind, logical in client.events if kind == "write"))

    def test_private_store_failure_prevents_understanding_write_and_cloudinary_upload(self):
        (self.runtime / "shared").chmod(0o777)
        client = Client(uploaded=False)
        result = self.ingest(client)
        self.assertEqual(result["status"], "FAILED", result)
        self.assertIn("media_understanding_evidence_blocked", result["reason"])
        self.analysis.assert_called_once()
        self.upsert.assert_not_called()
        self.upload.assert_not_called()
        self.assertEqual(client.rows["source_media_understanding"], [])
        self.assertFalse((self.runtime / "shared" / store.STORE_DIRECTORY).exists())

    def test_missing_corrupt_or_cross_asset_receipt_blocks_selector_despite_legacy_pass(self):
        for mode in ("missing", "corrupt", "cross_asset", "wrong_hash"):
            with self.subTest(mode=mode):
                client = Client(uploaded=True)
                self.assertEqual(self.ingest(client)["status"], "UNDERSTANDING_REFRESHED")
                receipt = self.receipt()
                original = receipt.read_bytes()
                if mode == "missing":
                    receipt.unlink()
                elif mode == "corrupt":
                    receipt.write_text("{}")
                elif mode == "cross_asset":
                    client.rows["source_post_media"][0]["media_asset_id"] = "foreign_asset"
                    client.rows["media_assets"][0]["media_id"] = "foreign_asset"
                else:
                    client.rows["source_post_media"][0]["content_hash"] = "c" * 64
                    client.rows["media_assets"][0]["content_hash"] = "c" * 64
                candidates, reasons = self.select(client)
                self.assertEqual(candidates, [])
                expected_reason = "media_asset_binding_conflict" if mode == "wrong_hash" else "media_visual_evidence_unverified"
                self.assertTrue(any(expected_reason in reason for reason in reasons), reasons)
                if not receipt.exists():
                    receipt.write_bytes(original)
                    receipt.chmod(0o600)
                else:
                    receipt.write_bytes(original)

    def test_retained_proof_does_not_override_latest_revoked_permission(self):
        client = Client(uploaded=True)
        self.assertEqual(self.ingest(client)["status"], "UNDERSTANDING_REFRESHED")
        client.rows["media_permissions"].append({**PERMISSION, "revoked": True, "approved_at": "2026-10-30T01:00:00+09:00"})
        candidates, reasons = self.select(client)
        self.assertEqual(candidates, [], reasons)
        self.assertTrue(any("permission_ledger_blocked" in reason for reason in reasons), reasons)

    def test_each_raw_media_asset_and_understanding_hash_must_match_before_merge(self):
        baseline = Client(uploaded=True)
        self.assertEqual(self.ingest(baseline)["status"], "UNDERSTANDING_REFRESHED")
        candidates, reasons = self.select(baseline)
        self.assertEqual(len(candidates), 1, reasons)
        self.assertEqual(prepare_media_context(candidates[0][1], account_id=ACCOUNT)["visual_status"], "VISUAL_VERIFIED")
        receipt = self.receipt().read_bytes()
        analysis_calls = self.analysis.call_count
        for logical in ("source_post_media", "media_assets", "source_media_understanding"):
            with self.subTest(logical=logical):
                client = deepcopy(baseline)
                client.rows[logical][0]["content_hash"] = "b" * 64
                blocked, reasons = self.select(client)
                self.assertEqual(blocked, [], reasons)
                self.assertTrue(any("media_asset_binding_conflict" in reason for reason in reasons), reasons)
                self.assertEqual(self.receipt().read_bytes(), receipt)
                self.assertEqual(self.analysis.call_count, analysis_calls)

    def test_each_raw_storage_url_and_asset_id_must_match_before_merge(self):
        baseline = Client(uploaded=True)
        self.assertEqual(self.ingest(baseline)["status"], "UNDERSTANDING_REFRESHED")
        candidates, reasons = self.select(baseline)
        self.assertEqual(len(candidates), 1, reasons)
        receipt = self.receipt().read_bytes()
        changes = (
            ("source_post_media", "storage_url", "https://res.cloudinary.com/offline/video/upload/foreign.mp4"),
            ("media_assets", "storage_url", "https://res.cloudinary.com/offline/video/upload/foreign.mp4"),
            ("source_post_media", "media_asset_id", "foreign_asset"),
            ("media_assets", "media_id", "foreign_asset"),
        )
        for logical, field, value in changes:
            with self.subTest(logical=logical, field=field):
                client = deepcopy(baseline)
                client.rows[logical][0][field] = value
                blocked, reasons = self.select(client)
                self.assertEqual(blocked, [], reasons)
                self.assertTrue(any("media_asset_binding_conflict" in reason for reason in reasons), reasons)
                self.assertEqual(self.receipt().read_bytes(), receipt)

    def test_raw_child_identity_cannot_be_replaced_by_asset_metadata(self):
        baseline = Client(uploaded=True)
        self.assertEqual(self.ingest(baseline)["status"], "UNDERSTANDING_REFRESHED")
        candidates, reasons = self.select(baseline)
        self.assertEqual(len(candidates), 1, reasons)
        changes = (
            ("source_id", "foreign_source", SOURCE["source_id"]),
            ("account_id", "night_scout", ACCOUNT),
            ("target_account_id", "night_scout", ACCOUNT),
            ("canonical_post_url", "https://x.com/registered_owner/status/999999999", URL),
            ("media_index", "1", "0"),
        )
        for field, child_value, asset_value in changes:
            with self.subTest(field=field):
                client = deepcopy(baseline)
                client.rows["source_post_media"][0][field] = child_value
                client.rows["media_assets"][0][field] = asset_value
                blocked, reasons = self.select(client)
                self.assertEqual(blocked, [], reasons)
                self.assertTrue(any("media_visual_evidence_unverified" in reason for reason in reasons), reasons)

    def test_retained_proof_does_not_override_missing_permission_ledger(self):
        client = Client(uploaded=True)
        self.assertEqual(self.ingest(client)["status"], "UNDERSTANDING_REFRESHED")
        client.rows["media_permissions"] = []
        candidates, reasons = self.select(client)
        self.assertEqual(candidates, [], reasons)
        self.assertTrue(any("permission_ledger_missing" in reason for reason in reasons), reasons)

    def test_explicit_account_and_registered_author_remain_required_after_proof(self):
        client = Client(uploaded=True)
        self.assertEqual(self.ingest(client)["status"], "UNDERSTANDING_REFRESHED")
        invalid = ({"account_id": "", "allowed_accounts": ""},
                   {"account_id": "night_scout", "allowed_accounts": [ACCOUNT]},
                   {"source_handle": "other_author"}, {"source_handle": ""})
        for change in invalid:
            with self.subTest(change=change):
                row = {**PERMISSION, **change}
                self.assertFalse(ingest.permission_ok_from_rows([row], SOURCE["source_id"], ACCOUNT, POST["author_handle"]))
                client.rows["media_permissions"] = [row]
                candidates, reasons = self.select(client)
                self.assertEqual(candidates, [], reasons)

    def test_rights_revoked_after_selection_are_read_fresh_before_caption_provider(self):
        client = Client(uploaded=True)
        self.assertEqual(self.ingest(client)["status"], "UNDERSTANDING_REFRESHED")
        candidates, reasons = self.select(client)
        self.assertEqual(len(candidates), 1, reasons)
        # The selection invocation has cached the permitted ledger.
        self.assertIn("media_permissions", client._direct_media_records_cache)
        client.rows["media_permissions"].append({**PERMISSION, "revoked": True,
            "approved_at": "2026-10-30T01:00:00+09:00"})
        service = Mock()
        service.generate_media_context.side_effect = AssertionError("revoked rights cannot call a provider")
        with patch.object(pipeline, "select_direct_candidates", return_value=(candidates, [])):
            plan = pipeline.build_plan(ACCOUNT, "", client, apply=False, manual_e2e_proof=True, caption_service=service)
        service.generate_media_context.assert_not_called()
        self.assertTrue(any("current_media_permission_unverified" in item.get("blocked_reasons", [])
                            for item in plan.get("skipped_candidate_attempts", [])), plan)
        self.assertFalse(plan.get("would_post", False))

    def test_unconfigured_runtime_preserves_legacy_summary_without_inventing_visual_proof(self):
        client = Client(uploaded=True)
        with patch.dict(os.environ, {"BUFFERED_RUNTIME_ROOT": ""}):
            result = self.ingest(client)
            self.assertEqual(result["status"], "UNDERSTANDING_REFRESHED", result)
            candidates, reasons = self.select(client)
        self.assertEqual(len(candidates), 1, reasons)
        self.assertEqual(prepare_media_context(candidates[0][1], account_id=ACCOUNT)["visual_status"], "VISUAL_UNVERIFIED")
        self.assertFalse((self.runtime / "shared" / store.STORE_DIRECTORY).exists())

    def test_completed_legacy_summary_is_not_automatically_reanalyzed_but_explicit_refresh_is_bound(self):
        client = Client(uploaded=True)
        client.rows["source_media_understanding"][0]["transcript_status"] = "UNAVAILABLE"
        default = self.ingest(client)
        self.assertEqual(default["status"], "ALREADY_INGESTED", default)
        self.analysis.assert_not_called()
        self.save.assert_not_called()
        self.upsert.assert_not_called()
        forced = self.ingest(client, force_visual_refresh=True)
        self.assertEqual(forced["status"], "UNDERSTANDING_REFRESHED", forced)
        self.assertEqual(self.analysis.call_args.kwargs["media_asset_id"], "legacy_custom_asset")
        self.stored_download.assert_called_once()
        self.source_download.assert_not_called()
        self.upload.assert_not_called()
        self.assertEqual(json.loads(self.receipt().read_text())["media_asset_id"], "legacy_custom_asset")

    def test_explicit_visual_refresh_rejects_missing_root_unmanaged_account_and_unuploaded_media(self):
        client = Client(uploaded=True)
        with patch.dict(os.environ, {"BUFFERED_RUNTIME_ROOT": ""}):
            missing_root = self.ingest(client, force_visual_refresh=True)
        self.assertEqual(missing_root["status"], "BLOCKED", missing_root)
        foreign = Client(uploaded=True)
        foreign.rows["source_posts"][0]["target_account_id"] = "beauty_account"
        unknown = self.ingest(foreign, force_visual_refresh=True)
        self.assertEqual(unknown["status"], "BLOCKED", unknown)
        fresh = self.ingest(Client(uploaded=False), force_visual_refresh=True)
        self.assertEqual(fresh["status"], "BLOCKED", fresh)
        self.analysis.assert_not_called()
        self.stored_download.assert_not_called()
        self.source_download.assert_not_called()
        self.upsert.assert_not_called()
        self.save.assert_not_called()
        self.upload.assert_not_called()

    def test_forced_refresh_reuses_complete_bound_proof_without_another_provider_call(self):
        client = Client(uploaded=True)
        first = self.ingest(client, force_visual_refresh=True)
        self.assertEqual(first["status"], "UNDERSTANDING_REFRESHED", first)
        before = self.receipt().read_bytes()
        for mock in (self.analysis, self.stored_download, self.source_download, self.upsert, self.save, self.upload):
            mock.reset_mock()
        repeated = self.ingest(client, force_visual_refresh=True)
        self.assertEqual(repeated["status"], "ALREADY_INGESTED", repeated)
        self.assertTrue(repeated["visual_evidence_retained"])
        self.assertEqual(self.receipt().read_bytes(), before)
        for mock in (self.analysis, self.stored_download, self.source_download, self.upsert, self.save, self.upload):
            mock.assert_not_called()

    def test_forced_refresh_rejects_relative_or_unprotected_root_before_download_or_analysis(self):
        client = Client(uploaded=True)
        with patch.dict(os.environ, {"BUFFERED_RUNTIME_ROOT": "relative-runtime"}):
            relative = self.ingest(client, force_visual_refresh=True)
        self.assertEqual(relative["status"], "BLOCKED", relative)
        (self.runtime / "shared").chmod(0o777)
        unprotected = self.ingest(client, force_visual_refresh=True)
        self.assertEqual(unprotected["status"], "BLOCKED", unprotected)
        for mock in (self.analysis, self.stored_download, self.source_download, self.upsert, self.save, self.upload):
            mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
