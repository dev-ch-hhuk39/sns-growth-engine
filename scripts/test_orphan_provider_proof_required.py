#!/usr/bin/env python3
"""Adversarial proof of unique read-only API matching before orphan repair."""
from __future__ import annotations

import contextlib
import io
import sys
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import recover_orphan_threads_post as legacy

TXT = "合成テストの投稿で、実際には送信しません。"
URL = "https://www.threads.net/@proof_owner/post/ABC_123"
WHEN = "2026-10-17T02:20:00+00:00"


def post(**changes) -> dict:
    result = {"id": "12345678", "text": TXT, "permalink": URL, "timestamp": WHEN}
    return {**result, **changes}


def queue(**changes) -> dict:
    return {
        "queue_id": "q_proof_0001", "draft_id": "d_proof_0001",
        "account_id": "night_scout", "status": "POSTED_SAVE_FAILED",
        "processed_at": "2026-10-17T02:19:00+00:00",
        **changes,
    }


class ProviderProofTests(unittest.TestCase):
    def test_unique_exact_match_only(self):
        self.assertEqual(legacy._match_post_in_api_results([post()], TXT)["id"], "12345678")
        self.assertIsNone(legacy._match_post_in_api_results([post(), post(id="98765432")], TXT))
        self.assertIsNone(legacy._match_post_in_api_results([post(text=TXT + "別の文章")], TXT))
        self.assertIsNone(legacy._match_post_in_api_results([post()], ""))
        self.assertIsNone(legacy._match_post_in_api_results([], TXT))

    def test_bad_provider_url_and_identity_rejected(self):
        bads = [
            {"id": ""}, {"id": "not_numeric"}, {"id": "1"},
            {"permalink": ""}, {"permalink": "http://www.threads.net/@proof_owner/post/ABC"},
            {"permalink": "https://threads.net.evil.example/@proof_owner/post/ABC"},
            {"permalink": "https://www.threads.net.evil/@proof_owner/post/ABC"},
            {"permalink": "https://www.threads.net/@other/profile"},
            {"permalink": "https://user:pass@www.threads.net/@proof_owner/post/ABC"},
            {"permalink": "https://www.threads.net:bad/@proof_owner/post/ABC"},
            {"permalink": "https://www.threads.net/@proof_owner/post/"},
            {"text": "spoofed"},
        ]
        for changed in bads:
            with self.subTest(changed=changed):
                self.assertFalse(legacy._verified_provider_identity(post(**changed), expected_text=TXT))
        self.assertTrue(legacy._verified_provider_identity(post(), expected_text=TXT))
        self.assertFalse(legacy._verified_provider_identity(post(text=""), expected_text=""))

    def test_timestamp_close_to_failed_save_required(self):
        self.assertTrue(legacy._provider_timestamp_corresponds(queue(), post()))
        self.assertFalse(legacy._provider_timestamp_corresponds(queue(processed_at=""), post()))
        self.assertFalse(legacy._provider_timestamp_corresponds(queue(), post(timestamp="")))
        self.assertFalse(legacy._provider_timestamp_corresponds(queue(), post(timestamp="2026-10-16T10:00:00Z")))
        self.assertFalse(legacy._provider_timestamp_corresponds(queue(processed_at="invalid"), post()))
        self.assertFalse(legacy._provider_timestamp_corresponds(queue(processed_at="2026-10-17T02:19:00"), post()))

    def test_direct_apply_requires_proof_and_pending_failed_save(self):
        inputs = dict(client=object(), social_derivative_id="s_proof",
                      text=TXT, external_post_id="12345678",
                      post_url=URL, dry_run=False)
        result = legacy._write_recovery(queue_row=queue(), **inputs)
        self.assertEqual(result, {"status": "BLOCKED", "reason": "LIVE_PROVIDER_PROOF_REQUIRED"})
        result = legacy._write_recovery(queue_row=queue(status="READY"),
                                        provider_verified=True, **inputs)
        self.assertEqual(result["reason"], "AMBIGUOUS_SAVE_FAILURE_STATE_REQUIRED")
        result = legacy._write_recovery(queue_row=queue(),
                                        provider_verified=True, **{**inputs, "post_url": ""})
        self.assertEqual(result["reason"], "LIVE_PROVIDER_IDENTITY_INVALID")

    def _run_cli(self, arguments: list[str], *, api_posts=None, api_error=None,
                 q=None, mock_write=True):
        q = q or queue()
        readsets = {
            "queue": [q], "posted_results": [], "social_derivatives": [],
        }
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(sys, "argv", ["recover_orphan_threads_post.py",
                                                           "--account-id", "night_scout",
                                                           "--queue-id", q["queue_id"],
                                                           *arguments]))
            stack.enter_context(patch.object(legacy, "get_config",
                                             return_value={"sheet_id": "fake", "sa_dict": {}}))
            stack.enter_context(patch.object(legacy, "SheetsClient", return_value=object()))
            stack.enter_context(patch.object(legacy, "_get_records",
                                             side_effect=lambda _cl, sheet: readsets[sheet]))
            stack.enter_context(patch.object(legacy, "_text_for_queue_id", return_value=TXT))
            read = stack.enter_context(patch.object(
                legacy, "_fetch_recent_threads_posts",
                side_effect=api_error if api_error else None,
                return_value=api_posts if api_posts is not None else [post()],
            ))
            writer = stack.enter_context(patch.object(legacy, "_write_recovery",
                                                      return_value={"status": "RECOVERED" if "--apply" in arguments else "DRY_RUN",
                                                                    "would_write": {}},
                                                      )) if mock_write else None
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                status = legacy.main()
            return status, buffer.getvalue(), read.call_count, writer

    def test_skip_api_apply_blocked_without_write(self):
        result, text, reads, writer = self._run_cli(
            ["--apply", "--skip-api-lookup"], mock_write=True,
        )
        self.assertEqual(result, 2)
        self.assertEqual(reads, 0)
        writer.assert_not_called()
        self.assertIn("LIVE_PROVIDER_READBACK_REQUIRED", text)

    def test_supplied_id_requires_live_api_and_conflict_rejected(self):
        result, _, reads, writer = self._run_cli(
            ["--apply", "--external-post-id", "99999999"],
        )
        self.assertEqual(result, 2)
        self.assertEqual(reads, 1)
        writer.assert_not_called()

    def test_supplied_url_requires_live_api_and_conflict_rejected(self):
        result, _, reads, writer = self._run_cli(
            ["--apply", "--post-url", "https://www.threads.net/@other/post/OTHER"],
        )
        self.assertEqual(result, 2)
        self.assertEqual(reads, 1)
        writer.assert_not_called()

    def test_duplicate_matching_provider_posts_blocked(self):
        result, text, _, writer = self._run_cli(
            ["--apply"], api_posts=[post(), post(id="98765432")],
        )
        self.assertEqual(result, 2)
        writer.assert_not_called()
        self.assertIn("UNIQUE_EXACT_PROVIDER_POST_NOT_VERIFIED", text)

    def test_missing_timestamp_or_wrong_queue_status_blocked(self):
        first, _, _, writer = self._run_cli(["--apply"], api_posts=[post(timestamp="")])
        self.assertEqual(first, 2)
        writer.assert_not_called()
        second, _, reads, writer2 = self._run_cli(["--apply"], q=queue(status="READY"))
        self.assertEqual(second, 2)
        self.assertEqual(reads, 0)
        writer2.assert_not_called()

    def test_api_errors_are_redacted(self):
        first, output, _, writer = self._run_cli(
            ["--apply"], api_error=RuntimeError("SECRET_BEARER_TOKEN_EXPOSED"),
        )
        self.assertEqual(first, 2)
        self.assertNotIn("SECRET_BEARER_TOKEN_EXPOSED", output)
        writer.assert_not_called()

    def test_unique_valid_provider_result_is_only_apply_entry(self):
        # Writer is mocked. No real Google mutation or Threads request.
        result, output, reads, writer = self._run_cli(["--apply"])
        self.assertEqual(result, 0)
        self.assertEqual(reads, 1)
        self.assertEqual(writer.call_count, 1)
        kwargs = writer.call_args.kwargs
        self.assertEqual(kwargs["external_post_id"], post()["id"])
        self.assertEqual(kwargs["post_url"], URL)
        self.assertTrue(kwargs["provider_verified"])
        self.assertFalse(kwargs["dry_run"])
        self.assertNotIn(TXT, output)
        self.assertNotIn(URL, output)


# Supplemental direct-readback invariants use no provider/Google credentials.
class RecoveryWriteReadbackTests(unittest.TestCase):
    def setUp(self):
        self.queue_rows = [queue()]
        self.results = []
        self.writes = []

    def fake_append(self, _client, tab, value):
        self.writes.append(tab)
        if tab == "posted_results":
            self.results.append(dict(value))

    def fake_update(self, _client, tab, _key, _id, patch):
        if tab == "queue":
            self.queue_rows[0].update(patch)
        return True

    def actual(self, *, update_function=None, rows_function=None):
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(legacy, "_append_row",
                                             side_effect=self.fake_append))
            stack.enter_context(patch.object(legacy, "_update_row",
                                             side_effect=update_function or self.fake_update))
            stack.enter_context(patch.object(legacy, "_get_records",
                                             side_effect=rows_function or (
                                                 lambda _client, tab: self.results if tab == "posted_results"
                                                 else self.queue_rows
                                             )))
            return legacy._write_recovery(
                object(), queue_row=queue(), social_derivative_id="s1",
                text=TXT, external_post_id="12345678",
                post_url=URL, dry_run=False, provider_verified=True,
            )

    def test_exact_result_and_queue_readback_before_followup_logs(self):
        report = self.actual()
        self.assertEqual(report["status"], "RECOVERED")
        self.assertEqual(self.writes, ["posted_results", "logs", "pdca_runs",
                                       "prompt_improvement_suggestions"])
        self.assertEqual(self.results[0]["verification_status"],
                         "LIVE_PROVIDER_MATCH_PENDING_SHEETS_READBACK")
        self.assertEqual(self.results[0]["metrics_status"], "MANUAL_PENDING")

    def test_missing_posted_results_ack_stops_before_queue_changes(self):
        report = self.actual(rows_function=lambda _client, _tab: [])
        self.assertEqual(report["status"], "PARTIAL_SAVE_UNVERIFIED_NO_RETRY")
        self.assertEqual(report["reason"], "POSTED_RESULT_READBACK_FAILED")
        self.assertEqual(self.writes, ["posted_results"])
        self.assertEqual(self.queue_rows[0]["status"], "POSTED_SAVE_FAILED")

    def test_unknown_queue_patch_stops_before_followup_writes(self):
        report = self.actual(update_function=lambda *_args, **_kwargs: False)
        self.assertEqual(report["status"], "PARTIAL_SAVE_UNVERIFIED_NO_RETRY")
        self.assertEqual(report["reason"], "QUEUE_UPDATE_UNVERIFIED")
        self.assertEqual(self.writes, ["posted_results"])

    def test_queue_readback_failed_stops_without_followup(self):
        def read(_client, tab):
            return self.results if tab == "posted_results" else [queue()]
        report = self.actual(rows_function=read)
        self.assertEqual(report["reason"], "QUEUE_READBACK_FAILED")
        self.assertEqual(self.writes, ["posted_results"])

    def test_unknown_append_outcome_is_not_retried(self):
        from sheets_client import SheetsMutationOutcomeUnknown

        class Worksheet:
            calls = 0
            def row_values(self, index):
                return ["result_id", "queue_id", "status"]
            def append_row(self, values, *, value_input_option):
                self.calls += 1
                raise RuntimeError("ambiguous_provider_acceptance")

        class Client:
            worksheet = Worksheet()
            def _ws(self, _name):
                return self.worksheet

        client = Client()
        with self.assertRaises(SheetsMutationOutcomeUnknown):
            legacy._append_row(client, "posted_results", {"result_id": "r1"})
        self.assertEqual(client.worksheet.calls, 1)


if __name__ == "__main__":
    unittest.main()
