#!/usr/bin/env python3
"""One-item visual-refresh plans remain offline; blocked items are failures."""
from __future__ import annotations

from contextlib import ExitStack, redirect_stdout
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import ingest_direct_reference_media as ingest


class RefreshCliTests(unittest.TestCase):
    def call(self, args):
        stream = io.StringIO()
        with patch.object(sys, "argv", ["ingest", *args]), redirect_stdout(stream):
            status = ingest.main()
        return status, json.loads(stream.getvalue())

    def test_invalid_refresh_scope_is_rejected_before_credential_lookup(self):
        for args in ([], ["--source-post-media-id", "media"], ["--source-post-id", "post", "--account-id", "night_scout"],
                     ["--source-post-media-id", "media", "--account-id", "beauty_account"],
                     ["--source-post-id", "post", "--source-post-media-id", "media", "--account-id", "night_scout"]):
            with self.subTest(args=args), patch.object(ingest, "get_config", side_effect=AssertionError("no credentials")):
                code, row = self.call(["--refresh-visual-evidence", *args])
            self.assertEqual(code, 1)
            self.assertEqual(row["status"], "BLOCKED")

    def test_valid_plan_never_reads_sheets_or_invokes_provider(self):
        with patch.object(ingest, "get_config", side_effect=AssertionError("offline plan")), \
                patch.object(ingest, "analyze_local_media", side_effect=AssertionError("no provider")):
            code, row = self.call(["--refresh-visual-evidence", "--source-post-media-id", "media", "--account-id", "liver_manager"])
        self.assertEqual(code, 0)
        self.assertEqual(row["status"], "PLAN_ONLY")
        self.assertTrue(row["would_refresh_visual_evidence"])
        self.assertFalse(row["would_upload"])
        self.assertFalse(row["network_fetch"])

    def test_existing_apply_confirmation_and_operation_gates_remain_required(self):
        args = ["--refresh-visual-evidence", "--source-post-media-id", "media", "--account-id", "liver_manager", "--apply"]
        with patch.object(ingest, "get_config", side_effect=AssertionError("no credentials")):
            self.assertEqual(self.call(args)[0], 1)
            with patch.dict("os.environ", {"ALLOW_VIDEO_DOWNLOAD": "false", "ALLOW_CLOUDINARY_UPLOAD": "false"}):
                self.assertEqual(self.call([*args, "--confirm-ingest"])[0], 1)

    def run_applied(self, *, refresh=False, post_account="liver_manager", outcome="BLOCKED"):
        media = {"source_post_media_id": "media", "source_post_id": "post"}
        post = {"source_post_id": "post", "target_account_id": post_account, "source_id": "source"}
        client = SimpleNamespace(_ensure_tab=lambda *_: None)
        with ExitStack() as stack:
            stack.enter_context(patch.dict("os.environ", {"ALLOW_VIDEO_DOWNLOAD": "true", "ALLOW_CLOUDINARY_UPLOAD": "true"}))
            stack.enter_context(patch.object(ingest, "get_config", return_value={"sheet_id": "offline", "sa_dict": {}}))
            stack.enter_context(patch.object(ingest, "SheetsClient", return_value=client))
            stack.enter_context(patch.object(ingest, "permission_rows", return_value=[]))
            stack.enter_context(patch.object(ingest, "permission_ok_from_rows", return_value=True))
            stack.enter_context(patch.object(ingest, "record", side_effect=lambda _c, logical, *_: media if logical == "source_post_media" else post))
            worker = stack.enter_context(patch.object(ingest, "ingest_one", return_value={"status": outcome}))
            args = ["--source-post-media-id", "media", "--account-id", "liver_manager", "--apply", "--confirm-ingest"]
            if refresh:
                args.append("--refresh-visual-evidence")
            result = self.call(args)
        return result, worker, client, post, media

    def test_blocked_ingest_is_not_counted_as_success(self):
        (code, row), _, _, _, _ = self.run_applied()
        self.assertEqual(code, 1)
        self.assertEqual(row["status"], "FAILED")
        self.assertEqual(row["ingested_count"], 0)
        self.assertEqual(row["failed_count"], 1)

    def test_explicit_refresh_binds_one_account_and_passes_force_only_for_that_item(self):
        (code, row), worker, client, post, media = self.run_applied(refresh=True, outcome="UNDERSTANDING_REFRESHED")
        self.assertEqual(code, 0)
        self.assertEqual(row["asset_count"], 1)
        worker.assert_called_once_with(client, post, media, force_visual_refresh=True)
        (code, row), worker, *_ = self.run_applied(refresh=True, post_account="night_scout")
        self.assertEqual(code, 1)
        self.assertEqual(row["reason"], "visual_refresh_account_mismatch")
        worker.assert_not_called()


if __name__ == "__main__":
    unittest.main()
