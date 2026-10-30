#!/usr/bin/env python3
"""Real private-file tests; synthetic Gemini data never proves live acceptance."""
from __future__ import annotations

from copy import deepcopy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from media import understanding_evidence_store as store  # noqa: E402

DIGEST = hashlib.sha256(b"synthetic media bytes, not production evidence").hexdigest()
ASSET = "ma_" + DIGEST[:24]


def fixture(account="liver_manager", platform="x"):
    native = "123456789" if platform == "x" else "abcdefghijk"
    profile = "https://x.com/registered_owner" if platform == "x" else "https://www.youtube.com/@registered_owner"
    canonical = profile + "/status/" + native if platform == "x" else "https://www.youtube.com/watch?v=" + native
    source = {"source_id": "source1", "source_platform": platform, "source_handle": "@registered_owner",
              "source_url": profile, "target_account_ids": [account], "active": True}
    post = {"source_id": "source1", "source_post_id": "post1", "target_account_id": account,
            "platform": platform, "canonical_post_url": canonical, "external_post_id": native,
            "author_handle": "registered_owner", "content_hash": "text-and-URL-hash-is-not-the-media-hash"}
    media = {"source_post_media_id": "media1", "source_post_id": "post1", "reference_post_id": "post1",
             "canonical_post_url": canonical, "media_index": "0", "media_type": "video",
             "media_asset_id": ASSET, "content_hash": DIGEST}
    analysis = {
        "status": "PASS", "provider": "gemini", "vision_status": "PASS", "http_status": 200,
        "response_schema_status": "PASS", "visual_summary": "配信者が初見のコメントへ挨拶を返す。",
        "visible_action": "初見へ挨拶を返す。", "key_moment": "コメントを読み、短い挨拶を返す。",
        "visual_facts": [{"id": "VF1", "type": "visible_action", "text": "初見へ挨拶を返す。"}],
        "visual_evidence": {"status": "UNDERSTOOD", "provider": "gemini", "media_asset_id": ASSET,
                            "content_hash": DIGEST, "frame_hashes": ["a" * 64]},
        "transcript_status": "UNAVAILABLE", "transcript_text": "", "aggregate_status": "PASS_VISION",
    }
    return post, media, analysis, [source]


class UnderstandingEvidenceStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / "runtime"
        self.root.mkdir(mode=0o700)
        (self.root / "shared").mkdir(mode=0o700)
        self.post, self.media, self.analysis, self.registry = fixture()
        self.directory = self.root / "shared" / store.STORE_DIRECTORY

    def save(self, *, root=None, post=None, media=None, analysis=None, digest=DIGEST, registry=None):
        return store.save_understanding_evidence(
            self.root if root is None else root, self.post if post is None else post,
            self.media if media is None else media, self.analysis if analysis is None else analysis,
            content_hash=digest, registry_rows=self.registry if registry is None else registry)

    def load(self, *, root=None, post=None, media=None, digest=DIGEST, registry=None):
        return store.load_understanding_evidence(
            self.root if root is None else root, self.post if post is None else post,
            self.media if media is None else media, content_hash=digest,
            registry_rows=self.registry if registry is None else registry)

    def saved_path(self):
        result = self.save()
        self.assertEqual(result["status"], "PASS", result)
        return self.directory / (result["evidence_key"] + ".json")

    def assert_blocked(self, result):
        self.assertEqual(result["status"], "BLOCKED", result)
        self.assertNotIn("analysis", result)

    def test_complete_raw_proof_round_trips_for_both_managed_accounts_and_platforms(self):
        for account in ("night_scout", "liver_manager"):
            for platform in ("x", "youtube"):
                post, media, analysis, registry = fixture(account, platform)
                with self.subTest(account=account, platform=platform):
                    self.assertEqual(self.save(post=post, media=media, analysis=analysis, registry=registry)["status"], "PASS")
                    loaded = self.load(post=post, media=media, registry=registry)
                    self.assertEqual(loaded["status"], "PASS", loaded)
                    self.assertEqual(loaded["analysis"], analysis)

    def test_blank_or_none_root_never_reads_registry_or_filesystem(self):
        with patch.object(store.os, "open", side_effect=AssertionError("no filesystem")), \
                patch.object(store, "load_registry", side_effect=AssertionError("no registry")):
            for root in (None, "", "  "):
                self.assertEqual(store.save_understanding_evidence(root, {}, {}, {}, content_hash="")["status"], "NOT_CONFIGURED")
                self.assertEqual(store.load_understanding_evidence(root, {}, {}, content_hash="")["status"], "NOT_CONFIGURED")

    def test_out_of_scope_accounts_platforms_and_non_video_are_untouched(self):
        with patch.object(store.os, "open", side_effect=AssertionError("no filesystem")), \
                patch.object(store, "load_registry", side_effect=AssertionError("no registry")):
            for post, media in (({**self.post, "target_account_id": "beauty_account"}, self.media),
                                ({**self.post, "platform": "threads", "canonical_post_url": "https://www.threads.com/@owner/post/ABC"}, self.media),
                                ({**self.post, "platform": "tiktok", "canonical_post_url": "https://www.tiktok.com/@owner/video/123"}, self.media),
                                (self.post, {**self.media, "media_type": "image"})):
                self.assertEqual(self.save(post=post, media=media)["status"], "NOT_APPLICABLE")
                self.assertEqual(self.load(post=post, media=media)["status"], "NOT_APPLICABLE")

    def test_relative_root_is_rejected_without_discovery(self):
        with patch.object(store.os, "open", side_effect=AssertionError("no filesystem")):
            self.assert_blocked(self.save(root="relative-runtime"))

    def test_reader_never_creates_missing_store_or_missing_runtime(self):
        self.assert_blocked(self.load())
        self.assertFalse(self.directory.exists())
        missing = self.root.parent / "missing"
        self.assert_blocked(self.load(root=missing))
        self.assertFalse(missing.exists())

    def test_runtime_and_shared_must_exist_owned_and_not_be_symlinks(self):
        alias = self.root.parent / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        self.assert_blocked(self.save(root=alias))
        shared = self.root / "shared"
        actual = self.root / "real-shared"
        shared.rename(actual)
        shared.symlink_to(actual, target_is_directory=True)
        self.assert_blocked(self.save())

    def test_runtime_and_shared_writable_by_others_are_rejected(self):
        for path in (self.root, self.root / "shared"):
            with self.subTest(path=path.name):
                path.chmod(0o775)
                self.assert_blocked(self.save())
                path.chmod(0o700)
        with patch.object(store.os, "geteuid", return_value=os.geteuid() + 1):
            self.assert_blocked(self.save())

    def test_private_modes_and_single_regular_file_links_are_enforced(self):
        path = self.saved_path()
        self.assertEqual(stat.S_IMODE(self.directory.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(path.stat().st_nlink, 1)
        self.assertEqual(path.stat().st_uid, os.geteuid())
        path.chmod(0o640)
        self.assert_blocked(self.load())
        path.chmod(0o600)
        os.link(path, self.root / "hardlink")
        self.assert_blocked(self.load())

    def test_symlink_store_and_symlink_receipt_are_rejected(self):
        self.directory.symlink_to(self.root / "shared", target_is_directory=True)
        self.assert_blocked(self.save())
        self.directory.unlink()
        path = self.saved_path()
        target = self.root / "actual-proof.json"
        path.rename(target)
        path.symlink_to(target)
        self.assert_blocked(self.load())
        self.assert_blocked(self.save())

    def test_store_mode_must_be_owner_only(self):
        self.saved_path()
        self.directory.chmod(0o750)
        self.assert_blocked(self.load())
        self.assert_blocked(self.save())

    def test_identical_payload_is_idempotent_and_conflicting_payload_never_overwrites(self):
        path = self.saved_path()
        before = path.read_bytes()
        result = self.save()
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["reused"])
        changed = {**self.analysis, "visual_summary": "同じ映像の別の要約。"}
        self.assert_blocked(self.save(analysis=changed))
        self.assertEqual(path.read_bytes(), before)

    def test_corrupt_unknown_or_duplicate_key_receipt_is_never_overwritten(self):
        path = self.saved_path()
        for data in (b"{}", b"not-json", b'{"schema_version":1,"schema_version":1}'):
            with self.subTest(data=data):
                path.write_bytes(data)
                self.assert_blocked(self.load())
                self.assert_blocked(self.save())
                self.assertEqual(path.read_bytes(), data)

    def test_oversized_incoming_or_existing_evidence_is_rejected(self):
        self.assert_blocked(self.save(analysis={**self.analysis, "transcript_text": "x" * store.MAX_EVIDENCE_BYTES}))
        self.assertFalse(self.directory.exists())
        path = self.saved_path()
        path.write_bytes(b"x" * (store.MAX_EVIDENCE_BYTES + 1))
        self.assert_blocked(self.load())
        self.assert_blocked(self.save())

    def test_stale_hash_or_foreign_account_and_native_post_cannot_load_proof(self):
        self.saved_path()
        other_hash = "b" * 64
        self.assert_blocked(self.load(digest=other_hash))
        self.assert_blocked(self.load(media={**self.media, "content_hash": other_hash}, digest=other_hash))
        post, media, _analysis, registry = fixture("night_scout")
        self.assert_blocked(self.load(post=post, media=media, registry=registry))
        other_url = "https://x.com/registered_owner/status/999999999"
        self.assert_blocked(self.load(post={**self.post, "external_post_id": "999999999", "canonical_post_url": other_url},
                                      media={**self.media, "canonical_post_url": other_url}))

    def test_parent_asset_index_canonical_and_all_supplied_hashes_must_match(self):
        changes = ({"source_post_id": "other"}, {"reference_post_id": "other"},
                   {"source_post_media_id": ""}, {"media_index": -1}, {"media_index": True},
                   {"canonical_post_url": "https://x.com/registered_owner/status/999"},
                   {"media_id": "another_asset"}, {"content_hash": "b" * 64},
                   {"resolved_content_hash": "b" * 64}, {"asset_content_hash": "b" * 64},
                   {"understanding_content_hash": "b" * 64},
                   {"media_understanding": {"content_hash": "b" * 64}},
                   {"account_id": "night_scout"}, {"source_id": "other_source"})
        for change in changes:
            with self.subTest(change=change):
                self.assert_blocked(self.save(media={**self.media, **change}))
        self.assertFalse(self.directory.exists())

    def test_new_asset_can_be_derived_but_read_requires_persisted_asset_and_hash(self):
        new_media = {k: v for k, v in self.media.items() if k not in {"media_asset_id", "content_hash"}}
        self.assertEqual(self.save(media=new_media)["status"], "PASS")
        self.assert_blocked(self.load(media=new_media))
        self.assertEqual(self.load()["status"], "PASS")

    def test_independently_bound_legacy_asset_id_is_supported(self):
        media = {**self.media, "media_asset_id": "legacy_asset_1"}
        analysis = deepcopy(self.analysis)
        analysis["visual_evidence"]["media_asset_id"] = "legacy_asset_1"
        self.assertEqual(self.save(media=media, analysis=analysis)["status"], "PASS")
        self.assertEqual(self.load(media=media)["analysis"], analysis)

    def test_missing_duplicate_or_inactive_registered_source_is_rejected(self):
        for registry in ([], self.registry + self.registry, [{**self.registry[0], "active": False}]):
            self.assert_blocked(self.save(registry=registry))
        self.assertFalse(self.directory.exists())

    def test_incomplete_asr_only_or_wrong_gemini_evidence_never_creates_receipt(self):
        for change in ({"status": "BLOCKED"}, {"vision_status": "UNAVAILABLE"}, {"http_status": 429},
                       {"response_schema_status": "BLOCKED"}, {"visual_facts": []},
                       {"provider": "github_models_vision"}, {"visual_evidence": {}},
                       {"visual_evidence": {**self.analysis["visual_evidence"], "content_hash": "b" * 64}}):
            with self.subTest(change=change):
                self.assert_blocked(self.save(analysis={**self.analysis, **change}))
        self.assertFalse(self.directory.exists())

    def test_repeated_raw_analysis_parent_identity_cannot_override_envelope(self):
        for change in ({"source_post_id": "other_parent"}, {"source_post_media_id": "other_media"},
                       {"account_id": "night_scout"}, {"media_index": "1"}):
            with self.subTest(change=change):
                self.assert_blocked(self.save(analysis={**self.analysis, **change}))
        self.assertFalse(self.directory.exists())

    def test_active_youtube_aliases_case_and_url_inference_require_and_reuse_proof(self):
        post, media, analysis, registry = fixture(platform="youtube")
        variants = ({"platform": "youtube_shorts"}, {"platform": "YouTube"},
                    {"platform": "youtube_playlist"}, {"platform": "youtube_streams"},
                    {"platform": "", "source_platform": "youtube_shorts"}, {"platform": ""})
        for change in variants:
            changed_post = {**post, **change}
            changed_media = {**media, "source_platform": "youtube_shorts"}
            with self.subTest(change=change):
                result = self.save(post=changed_post, media=changed_media, analysis=analysis, registry=registry)
                self.assertEqual(result["status"], "PASS", result)
                loaded = self.load(post=changed_post, media=changed_media, registry=registry)
                self.assertEqual(loaded["status"], "PASS", loaded)
        alias_root = self.root.parent / "missing-runtime"
        self.assert_blocked(self.load(root=alias_root, post={**post, "platform": "youtube_shorts"}, media=media, registry=registry))

    def test_owner_metadata_account_platform_and_media_type_conflicts_cannot_skip_validation(self):
        cases = (
            ({**self.post, "account_id": "night_scout"}, self.media),
            ({**self.post, "target_account_id": "beauty_account", "account_id": "night_scout"}, self.media),
            (self.post, {**self.media, "account_id": "night_scout", "media_type": "image"}),
            ({**self.post, "media_type": "video"}, {**self.media, "media_type": "image"}),
            ({**self.post, "platform": "threads"}, self.media),
            ({**self.post, "source_platform": "youtube"}, self.media),
            (self.post, {**self.media, "source_platform": "youtube", "media_type": "image"}),
        )
        for post, media in cases:
            with self.subTest(post=post, media=media):
                self.assert_blocked(self.save(post=post, media=media))
                self.assert_blocked(self.load(post=post, media=media))
        self.assertFalse(self.directory.exists())

    def test_receipt_survives_removal_of_ephemeral_preparation_workspace(self):
        workspace = self.root / "shared" / "media-prep" / "run-fixture"
        workspace.mkdir(parents=True)
        (workspace / "video.mp4").write_bytes(b"synthetic video")
        self.saved_path()
        shutil.rmtree(workspace)
        self.assertEqual(self.load()["status"], "PASS")

    def test_capacity_limits_block_new_proof_without_deleting_existing_proof(self):
        path = self.saved_path()
        before = path.read_bytes()
        next_media = {**self.media, "source_post_media_id": "media2", "media_index": "1"}
        for limits in ({"MAX_STORE_RECEIPTS": 1}, {"MAX_STORE_BYTES": len(before)}):
            with self.subTest(limits=limits), patch.multiple(store, **limits):
                self.assert_blocked(self.save(media=next_media))
                reused = self.save()
                self.assertEqual(reused["status"], "PASS")
                self.assertTrue(reused["reused"])
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(len(list(self.directory.glob("*.json"))), 1)

    def test_unknown_stale_prepared_entry_blocks_growth_without_cleanup(self):
        self.saved_path()
        unknown = self.directory / ".prepared-unverified"
        unknown.write_bytes(b"unknown previous attempt")
        next_media = {**self.media, "source_post_media_id": "media2", "media_index": "1"}
        self.assert_blocked(self.save(media=next_media))
        self.assertEqual(unknown.read_bytes(), b"unknown previous attempt")
        self.assertEqual(self.save()["status"], "PASS")

    def test_busy_lock_blocks_immediately_without_creating_new_receipt(self):
        self.saved_path()
        lock = self.directory / store.LOCK_FILE
        with lock.open("r+b") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.save(media={**self.media, "source_post_media_id": "media2", "media_index": "1"})
        self.assert_blocked(result)
        self.assertIn("evidence_store_busy", result["reasons"])
        self.assertEqual(len(list(self.directory.glob("*.json"))), 1)

    def test_lock_is_owner_only_regular_single_link_and_not_a_symlink(self):
        self.saved_path()
        lock = self.directory / store.LOCK_FILE
        lock.chmod(0o640)
        self.assert_blocked(self.save())
        lock.chmod(0o600)
        replacement = self.root / "lock-target"
        lock.rename(replacement)
        lock.symlink_to(replacement)
        self.assert_blocked(self.save())

    def test_atomic_publication_never_replaces_a_concurrently_created_unknown_file(self):
        original = store.os.link
        created = []
        def concurrent(source, destination, **kwargs):
            target = self.directory / destination
            target.write_bytes(b"unknown concurrent outcome")
            target.chmod(0o600)
            created.append(target)
            return original(source, destination, **kwargs)
        with patch.object(store.os, "link", side_effect=concurrent):
            self.assert_blocked(self.save())
        self.assertEqual(created[0].read_bytes(), b"unknown concurrent outcome")
        self.assertFalse(list(self.directory.glob(".prepared-*")))


if __name__ == "__main__":
    unittest.main()
