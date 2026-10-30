#!/usr/bin/env python3
"""Owner downloads and analysis independently require a fresh permission row."""
from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

import ingest_direct_reference_media as ingest  # noqa: E402
from media import understanding_evidence_store as store  # noqa: E402
from test_durable_understanding_pipeline import (  # noqa: E402
    ACCOUNT, DATA, SOURCE, Client, analysis_for,
)


class PermissionClient(Client):
    def __init__(self, *, uploaded=False):
        super().__init__(uploaded=uploaded)
        self.permission_reads = 0
        self.permission_read_error_at = 0
        self.rows["media_permissions"][0]["allow_analysis"] = True

    def _call_with_rate_limit_retry(self, label, callback):
        if label == "get_all_records:media_permissions":
            self.permission_reads += 1
            if self.permission_reads == self.permission_read_error_at:
                raise RuntimeError("private diagnostic must not leave the permission reader")
        return callback()

    def _ensure_tab(self, logical, headers):
        if logical == "media_permissions":
            raise AssertionError("latest permission checks must not initialize a tab")
        return super()._ensure_tab(logical, headers)


class IngestPermissionRecheckTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name).resolve()
        self.runtime = self.directory / "runtime"
        self.runtime.mkdir(mode=0o700)
        (self.runtime / "shared").mkdir(mode=0o700)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ, {
            "BUFFERED_RUNTIME_ROOT": str(self.runtime),
            "SNS_MEDIA_PREP_WORKSPACE": str(self.directory / "workspace"),
            "ALLOW_LOCAL_TRANSCRIPTION": "true",
        }))
        self.stack.enter_context(patch.object(store, "load_registry", return_value=[deepcopy(SOURCE)]))
        self.stack.enter_context(patch.object(ingest, "safe_https_url", return_value=True))
        self.stack.enter_context(patch("socket.getaddrinfo", side_effect=AssertionError("no network")))
        self.stack.enter_context(patch("subprocess.run", side_effect=AssertionError("no external process")))
        self.download = self.stack.enter_context(patch.object(ingest, "download_source_media", side_effect=self.download_bytes))
        self.stored_download = self.stack.enter_context(patch.object(ingest, "download_direct_https_media", side_effect=self.stored_bytes))
        self.stack.enter_context(patch.object(ingest, "probe_video", return_value={
            "duration_seconds": "20", "width": "1280", "height": "720", "aspect_ratio": "16:9"}))
        self.analysis = self.stack.enter_context(patch.object(ingest, "analyze_local_media", side_effect=analysis_for))
        self.save = self.stack.enter_context(patch.object(ingest, "save_understanding_evidence", wraps=store.save_understanding_evidence))
        self.upsert = self.stack.enter_context(patch.object(ingest, "upsert_media_understanding", wraps=ingest.upsert_media_understanding))
        cloudinary = ModuleType("cloudinary")
        cloudinary.__path__ = []
        cloudinary.config = Mock()
        uploader = ModuleType("cloudinary.uploader")
        uploader.upload = Mock(return_value={
            "secure_url": "https://res.cloudinary.com/offline/video/upload/new.mp4", "public_id": "offline/new"})
        cloudinary.uploader = uploader
        self.upload = uploader.upload
        self.stack.enter_context(patch.dict(sys.modules, {"cloudinary": cloudinary, "cloudinary.uploader": uploader}))

    @staticmethod
    def download_bytes(*, path, **_kwargs):
        path.write_bytes(DATA)
        return "offline_fixture"

    @staticmethod
    def stored_bytes(_url, path, **_kwargs):
        path.write_bytes(DATA)

    def run_ingest(self, client, **kwargs):
        return ingest.ingest_one(client, client.rows["source_posts"][0], client.rows["source_post_media"][0], **kwargs)

    def assert_no_understanding_side_effects(self, client):
        self.analysis.assert_not_called()
        self.save.assert_not_called()
        self.upsert.assert_not_called()
        self.upload.assert_not_called()
        self.assertFalse(any(logical in {"source_media_understanding", "media_assets"}
                             for kind, logical in client.events if kind == "write"))

    def test_valid_two_snapshots_allow_existing_ingest_and_full_proof(self):
        client = PermissionClient()
        result = self.run_ingest(client)
        self.assertEqual(result["status"], "INGESTED", result)
        self.assertEqual(client.permission_reads, 2)
        self.download.assert_called_once()
        self.analysis.assert_called_once()
        self.save.assert_called_once()
        self.upsert.assert_called_once()
        self.upload.assert_called_once()
        receipts = list((self.runtime / "shared" / store.STORE_DIRECTORY).glob("*.json"))
        self.assertEqual(len(receipts), 1)

    def test_rejected_current_scope_or_author_prevents_download(self):
        changes = ({"revoked": True}, {"account_id": "", "allowed_accounts": ""},
                   {"account_id": "night_scout", "allowed_accounts": [ACCOUNT]},
                   {"allowed_accounts": ["night_scout"]}, {"source_handle": "another_author"},
                   {"source_handle": ""}, {"allow_download": False})
        for change in changes:
            with self.subTest(change=change):
                client = PermissionClient()
                client.rows["media_permissions"][0].update(change)
                result = self.run_ingest(client)
                self.assertEqual(result["status"], "FAILED", result)
                self.assertEqual(result["reason"], "ingest_failed:current_direct_media_permission_unverified")
                self.download.assert_not_called()
                self.stored_download.assert_not_called()
                self.assert_no_understanding_side_effects(client)

    def test_missing_ledger_or_actual_post_author_does_not_infer_permission(self):
        for missing in ("ledger", "author"):
            with self.subTest(missing=missing):
                client = PermissionClient()
                if missing == "ledger":
                    client.rows["media_permissions"] = []
                else:
                    client.rows["source_posts"][0].pop("author_handle")
                result = self.run_ingest(client)
                self.assertEqual(result["reason"], "ingest_failed:current_direct_media_permission_unverified")
                self.download.assert_not_called()
                self.assert_no_understanding_side_effects(client)

    def test_analysis_permission_must_be_explicit_at_second_snapshot(self):
        for value in (False, None):
            with self.subTest(value=value):
                client = PermissionClient()
                if value is None:
                    client.rows["media_permissions"][0].pop("allow_analysis")
                else:
                    client.rows["media_permissions"][0]["allow_analysis"] = value
                self.download.reset_mock(side_effect=True)
                self.download.side_effect = self.download_bytes
                result = self.run_ingest(client)
                self.assertEqual(result["reason"], "ingest_failed:current_media_analysis_permission_unverified")
                self.assertEqual(client.permission_reads, 2)
                self.download.assert_called_once()
                self.assert_no_understanding_side_effects(client)

    def test_revocation_during_download_prevents_analysis_of_stale_permission(self):
        client = PermissionClient()
        def download_then_revoke(**kwargs):
            backend = self.download_bytes(**kwargs)
            previous = client.rows["media_permissions"][0]
            client.rows["media_permissions"].append({**previous, "revoked": True,
                "updated_at": "2026-10-30T01:00:00+09:00"})
            return backend
        self.download.side_effect = download_then_revoke
        result = self.run_ingest(client)
        self.assertEqual(result["reason"], "ingest_failed:current_media_analysis_permission_unverified")
        self.assertEqual(client.permission_reads, 2)
        self.download.assert_called_once()
        self.assert_no_understanding_side_effects(client)

    def test_second_snapshot_rechecks_author_and_existing_operation_flags(self):
        for change in ({"source_handle": "different_author"}, {"allow_new_caption": False},
                       {"account_id": "night_scout", "allowed_accounts": [ACCOUNT]}):
            with self.subTest(change=change):
                client = PermissionClient()
                def download_then_change(**kwargs):
                    backend = self.download_bytes(**kwargs)
                    client.rows["media_permissions"][0].update(change)
                    return backend
                self.download.reset_mock(side_effect=True)
                self.download.side_effect = download_then_change
                result = self.run_ingest(client)
                self.assertEqual(result["reason"], "ingest_failed:current_media_analysis_permission_unverified")
                self.assert_no_understanding_side_effects(client)

    def test_permission_read_failure_emits_only_a_fixed_error(self):
        for ordinal in (1, 2):
            with self.subTest(ordinal=ordinal):
                client = PermissionClient()
                client.permission_read_error_at = ordinal
                self.download.reset_mock(side_effect=True)
                self.download.side_effect = self.download_bytes
                result = self.run_ingest(client)
                expected = "current_direct_media_permission_unverified" if ordinal == 1 else "current_media_analysis_permission_unverified"
                self.assertEqual(result["reason"], "ingest_failed:" + expected)
                self.assertNotIn("private diagnostic", str(result))
                self.assert_no_understanding_side_effects(client)

    def test_already_ingested_path_does_not_read_permissions_or_reanalyze(self):
        client = PermissionClient(uploaded=True)
        client.rows["source_media_understanding"][0]["transcript_status"] = "UNAVAILABLE"
        client.permission_read_error_at = 1
        result = self.run_ingest(client)
        self.assertEqual(result["status"], "ALREADY_INGESTED", result)
        self.assertEqual(client.permission_reads, 0)
        self.download.assert_not_called()
        self.stored_download.assert_not_called()
        self.assert_no_understanding_side_effects(client)

    def test_cached_proof_refresh_does_not_request_new_analysis_permission(self):
        client = PermissionClient(uploaded=True)
        self.assertEqual(self.run_ingest(client)["status"], "UNDERSTANDING_REFRESHED")
        self.analysis.reset_mock()
        self.save.reset_mock()
        self.upsert.reset_mock()
        self.upload.reset_mock()
        self.stored_download.reset_mock()
        client.rows["media_permissions"][0]["allow_analysis"] = False
        client.permission_reads = 0
        result = self.run_ingest(client, force_visual_refresh=True)
        self.assertEqual(result["status"], "ALREADY_INGESTED", result)
        self.assertTrue(result["visual_evidence_retained"])
        self.assertEqual(client.permission_reads, 0)
        self.stored_download.assert_not_called()
        self.analysis.assert_not_called()

    def test_optional_analysis_flag_keeps_permission_snapshot_api_compatible(self):
        client = PermissionClient()
        row = client.rows["media_permissions"][0]
        row["allow_analysis"] = False
        self.assertTrue(ingest.permission_ok_from_rows([row], SOURCE["source_id"], ACCOUNT, "registered_owner"))
        self.assertFalse(ingest.permission_ok_from_rows([row], SOURCE["source_id"], ACCOUNT,
                                                     "registered_owner", require_analysis=True))

    def test_analysis_gate_applies_to_both_owners_and_normalized_youtube_routes(self):
        platforms = (("x", "https://x.com/registered_owner/status/123456789"),
                     ("youtube", "https://www.youtube.com/watch?v=abcdefghijk"),
                     ("youtube_shorts", "https://www.youtube.com/shorts/abcdefghijk"))
        for account in ("night_scout", "liver_manager"):
            for platform, url in platforms:
                with self.subTest(account=account, platform=platform):
                    client = PermissionClient()
                    post, media = client.rows["source_posts"][0], client.rows["source_post_media"][0]
                    post.update(target_account_id=account, platform=platform, canonical_post_url=url)
                    media.update(canonical_post_url=url, original_media_url=url)
                    client.rows["media_permissions"][0].update(account_id=account,
                        allowed_accounts=[account], allow_analysis=False)
                    self.download.reset_mock(side_effect=True)
                    self.download.side_effect = self.download_bytes
                    result = self.run_ingest(client)
                    self.assertEqual(result["reason"], "ingest_failed:current_media_analysis_permission_unverified")
                    self.assertEqual(client.permission_reads, 2)
                    self.download.assert_called_once()
                    self.assert_no_understanding_side_effects(client)

    def test_nonowner_analysis_path_keeps_its_existing_permission_behavior(self):
        client = PermissionClient()
        client.rows["source_posts"][0]["target_account_id"] = "beauty_account"
        client.permission_read_error_at = 1
        result = self.run_ingest(client)
        self.assertEqual(result["status"], "INGESTED", result)
        self.assertEqual(client.permission_reads, 0)
        self.analysis.assert_called_once()


if __name__ == "__main__":
    unittest.main()
