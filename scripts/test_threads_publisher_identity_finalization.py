#!/usr/bin/env python3
"""Offline P0 publisher linkage/final-commit negative tests.

All source data, Sheets rows and publisher results are synthetic.
No credential loading, Google write, Threads API call, or host operation.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

import process_threads_queue as worker  # noqa: E402
from test_legacy_queue_write_safety import (  # noqa: E402
    Worksheet, client_for,
)
import test_pre_publish_sheets_failure as prior_tests  # noqa: E402


Q = {
    "queue_id": "q_synthetic", "draft_id": "d_shared",
    "account_id": "night_scout", "platform": "threads",
    "status": "READY", "public_post_text": "some safe preview body",
}


class FakeSheets:
    def __init__(self, rows):
        self.rows = [dict(item) for item in rows]

    def _ws(self, logical):
        return SimpleNamespace(get_all_records=lambda: [dict(r) for r in self.rows])


class PublisherIsolationTests(unittest.TestCase):
    def test_global_queue_id_collision_is_blocked_before_account_selection(self):
        for other in (
            {**Q, "account_id": "liver_manager"},
            {**Q, "status": "POSTED"},
            dict(Q),
        ):
            with self.subTest(other=other), self.assertRaisesRegex(
                worker.PublisherIdentityBlocked,
                "PUBLISH_GLOBAL_QUEUE_ID_COLLISION",
            ):
                worker.select_candidates(FakeSheets([Q, other]), "night_scout", 1)

    def test_missing_ready_identity_cannot_be_selected(self):
        for replacement in ("queue_id", "account_id"):
            row = {**Q, replacement: ""}
            with self.subTest(replacement=replacement), self.assertRaises(
                worker.PublisherIdentityBlocked,
            ):
                worker.select_candidates(FakeSheets([row]), None, 1)

    def test_unrelated_account_queue_id_does_not_block(self):
        rows = [Q, {**Q, "queue_id": "other", "account_id": "liver_manager"}]
        selected = worker.select_candidates(FakeSheets(rows), "night_scout", 2)
        self.assertEqual([r["queue_id"] for r in selected], ["q_synthetic"])

    def test_duplicate_draft_id_blocked_even_if_preview_text_exists(self):
        drafts = [
            {"draft_id": "d_shared", "account_id": "night_scout"},
            {"draft_id": "d_shared", "account_id": "night_scout"},
        ]
        with patch.object(worker, "records", side_effect=lambda _, logical: (
            drafts if logical == "drafts" else []
        )), patch.object(worker, "ThreadsPublisher",
                      side_effect=AssertionError("cannot initialize publisher")), patch.object(
            worker, "update_row", side_effect=AssertionError("no Sheets writes"),
        ):
            result = worker.process_one(
                SimpleNamespace(), Q, dry_run=False, confirm_real_post=True,
            )
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["reason"], "PUBLISH_DRAFT_IDENTITY_AMBIGUOUS")
        self.assertFalse(result["publish_attempted"])
        self.assertFalse(result["writes_performed"])

    def test_social_linkage_duplicate_or_wrong_account_is_not_reused(self):
        row = {"draft_id": "d_shared", "platform": "threads"}
        cases = (
            ([row, {**row, "account_id": "liver_manager"}],
             "PUBLISH_DERIVATIVE_IDENTITY_AMBIGUOUS"),
            ([{**row, "account_id": "liver_manager"}],
             "PUBLISH_DERIVATIVE_ACCOUNT_MISMATCH"),
        )
        for rows, reason in cases:
            with self.subTest(reason=reason), self.assertRaisesRegex(
                worker.PublisherIdentityBlocked, reason,
            ):
                worker.find_social_for_queue(None, Q, rows)
        self.assertIsNone(worker.find_social_for_queue(None, Q, [
            {"platform": "threads", "draft_id": ""}]))
        self.assertEqual(
            worker.find_social_for_queue(None, Q, [row]), row,
        )

    def test_draft_owner_mismatch_does_not_fall_back_to_other_account_body(self):
        with self.assertRaisesRegex(
            worker.PublisherIdentityBlocked, "PUBLISH_DRAFT_ACCOUNT_MISMATCH",
        ):
            worker.find_draft_for_queue(
                Q, [{"draft_id": "d_shared", "account_id": "liver_manager"}],
            )

    def test_explicit_per_account_draft_ids_can_be_shared_safely(self):
        drafts = [
            {"draft_id": "d_shared", "account_id": "liver_manager", "body_md": "Liver text"},
            {"draft_id": "d_shared", "account_id": "night_scout", "body_md": "Night text"},
        ]
        social = [
            {"draft_id": "d_shared", "platform": "threads",
             "account_id": "liver_manager", "derivative_id": "liver"},
            {"draft_id": "d_shared", "platform": "threads",
             "account_id": "night_scout", "derivative_id": "night"},
        ]
        self.assertEqual(worker.find_draft_for_queue(Q, drafts)["body_md"], "Night text")
        self.assertEqual(worker.find_social_for_queue(None, Q, social)["derivative_id"], "night")
        self.assertEqual(
            worker.find_draft_for_queue({**Q, "account_id": "liver_manager"}, drafts)["body_md"],
            "Liver text",
        )

    def test_ownerless_reference_conflicts_with_account_scoped_record(self):
        candidates = [
            {"draft_id": "d_shared", "account_id": "night_scout"},
            {"draft_id": "d_shared"},
        ]
        with self.assertRaisesRegex(
            worker.PublisherIdentityBlocked, "PUBLISH_DRAFT_IDENTITY_AMBIGUOUS",
        ):
            worker.find_draft_for_queue(Q, candidates)
        # A single legacy ownerless record remains permitted if no
        # other account claims the identity and queue account is fixed.
        self.assertEqual(
            worker.find_draft_for_queue(Q, [candidates[1]]), candidates[1],
        )

    def test_draft_and_derivative_duplicate_checks_are_account_scoped(self):
        posts = [{
            "queue_id": "q_liver", "account_id": "liver_manager",
            "status": "POSTED", "platform": "threads",
            "draft_id": "d_shared", "derivative_id": "shared_derivative",
        }]
        for derivative in (None, {"derivative_id": "shared_derivative"}):
            self.assertEqual(worker.duplicate_reason(
                queue_row=Q, social=derivative, text="Night scoped text",
                posted_rows=posts,
            ), "")
        posts[0]["account_id"] = "night_scout"
        self.assertTrue(worker.duplicate_reason(
            queue_row=Q, social={"derivative_id": "shared_derivative"},
            text="Night scoped text", posted_rows=posts,
        ))

    def test_publisher_update_denies_terminal_regression_and_posted_before_lock(self):
        statuses = (
            "POSTED", "FAILED", "DUPLICATE_BLOCKED",
            "PUBLISH_OUTCOME_UNVERIFIED", "POSTED_SAVE_UNVERIFIED",
            "POSTED_SAVE_FAILED",
        )
        for status in statuses:
            ws = Worksheet(status=status)
            with self.subTest(status=status), self.assertRaisesRegex(
                PermissionError, "legacy_queue_final_state_immutable",
            ):
                worker.update_row(
                    client_for(ws), "queue", "queue_id", "q1",
                    {"status": "FAILED"},
                )
            self.assertEqual(ws.calls, 0)
        ws = Worksheet(status="READY")
        with self.assertRaisesRegex(PermissionError, "queue_posted_requires_processing"):
            worker.update_row(
                client_for(ws), "queue", "queue_id", "q1",
                {"status": "POSTED"},
            )
        self.assertEqual(ws.calls, 0)

    def test_required_publisher_columns_and_duplicate_header_are_fail_closed(self):
        base = Worksheet(status="PROCESSING")
        for fields in (
            {"status": "POSTED", "result_id": "r_missing_from_schema"},
            {"status": "POSTED", "posted_at": "synthetic"},
            {"status": "POSTED", "post_url": "synthetic"},
            {"status": "FAILED", "processed_at": "synthetic"},
        ):
            ws = Worksheet(status="PROCESSING")
            with self.subTest(fields=fields), self.assertRaisesRegex(
                PermissionError, "legacy_publisher_required_column_missing",
            ):
                worker.update_row(
                    client_for(ws), "queue", "queue_id", "q1", fields,
                )
            self.assertEqual(ws.calls, 0)
        base.headers = tuple(base.headers) + ("queue_id",)
        with self.assertRaisesRegex(
            PermissionError, "legacy_sheet_header_identity_ambiguous",
        ):
            worker.update_row(
                client_for(base), "queue", "queue_id", "q1",
                {"status": "POSTED"},
            )
        self.assertEqual(base.calls, 0)

    def test_header_schema_is_fresh_across_mutations_not_cached_by_object_id(self):
        ws = Worksheet(status="READY")
        client = client_for(ws)
        self.assertTrue(worker.update_row(
            client, "queue", "queue_id", "q1",
            {"status": "PROCESSING"},
        ))
        self.assertEqual(ws.calls, 1)
        ws.headers = tuple(ws.headers) + ("queue_id",)
        with self.assertRaisesRegex(
            PermissionError, "legacy_sheet_header_identity_ambiguous",
        ):
            worker.update_row(
                client, "queue", "queue_id", "q1", {"status": "POSTED"},
            )
        self.assertEqual(ws.calls, 1)

    def test_dryrun_cli_constructs_write_disabled_sheets_client(self):
        created = []
        def client_ctor(sheet_id, sa_dict, dry_run):
            created.append(dry_run)
            return SimpleNamespace(dry_run=dry_run)
        with patch.object(sys, "argv", [
            "process_threads_queue.py", "--account-id", "night_scout",
            "--dry-run",
        ]), patch.object(
            worker, "get_config", return_value={"sheet_id": "synthetic", "sa_dict": {}},
        ), patch.object(
            worker, "SheetsClient", side_effect=client_ctor,
        ), patch.object(
            worker, "select_candidates", return_value=[],
        ), patch.object(
            worker, "ThreadsPublisher", side_effect=AssertionError("no publisher"),
        ):
            self.assertEqual(worker.main(), 0)
        self.assertEqual(created, [True])

    def test_prepublish_lock_rejects_media_source_and_slot_changes(self):
        runner = prior_tests.PrePublishTests(methodName="test_missing_lock_and_429_never_publish")
        runner.setUp()
        for field, newval in (
            ("media_asset_id", "unreviewed_asset"),
            ("source_post_id", "other_source"),
            ("generation_mode", "unauthorized_repost"),
            ("slot_id", "other_slot"),
            ("media_url", "https://media.example/new"),
            ("media_urls_json", '["https://media.example/new"]'),
        ):
            locked = [{**runner.row, "status": "PROCESSING", field: newval}]
            result, publish_calls = runner.process(locked_rows=locked)
            with self.subTest(field=field):
                self.assertEqual(
                    result["reason"], "QUEUE_PROCESSING_LOCK_READBACK_FAILED",
                )
                self.assertFalse(result["publish_attempted"])
                self.assertEqual(publish_calls, [True])

    def test_successful_provider_flag_without_post_identity_is_uncertain(self):
        runner = prior_tests.PrePublishTests(
            methodName="test_missing_lock_and_429_never_publish",
        )
        runner.setUp()
        locked = {**runner.row, "status": "PROCESSING"}
        for missing in ("external_post_id", "posted_url"):
            def synthetic_provider(text, **kwargs):
                return SimpleNamespace(
                    success=True, message="synthetic accepted",
                    delivery_state="PUBLISHED",
                    external_post_id=("" if missing == "external_post_id" else "synthetic_id"),
                    posted_url=("" if missing == "posted_url" else "https://example.invalid/post"),
                )
            status_updates = []
            def patch_status(_client, logical, _key, _id, fields):
                status_updates.append((logical, fields.get("status")))
                return True
            with self.subTest(missing=missing), patch.dict(
                worker.os.environ,
                {"PUBLISH_ENABLED": "true", "ALLOW_REAL_THREADS_POST": "true",
                 "SNS_P0_ONCE_GATE_ENABLED": "true"},
            ), prior_tests.mocked_real_once_ledger(), patch(
                "p0_exact_canary_approval.verify_current",
                return_value={"status": "PASS_ONE_APPROVED_CANARY_SCOPE_ONLY"},
            ), patch.object(
                worker, "records",
                side_effect=lambda _client, logical: (
                    [locked] if logical == "queue" else []
                ),
            ), patch.object(
                worker, "ThreadsPublisher",
                return_value=SimpleNamespace(publish=synthetic_provider),
            ), patch.object(worker, "update_row", side_effect=patch_status), patch.object(
                worker, "log_event",
            ), patch.object(
                worker, "save_posted_result",
                side_effect=AssertionError("must not record unverifiable POSTED"),
            ), patch.object(
                worker, "schedule_metrics_after_post",
                side_effect=AssertionError("must not schedule unverifiable metrics"),
            ):
                result = worker.process_one(
                    SimpleNamespace(), runner.row,
                    dry_run=False, confirm_real_post=True,
                )
            # Missing post identity cannot be ACKed; a missing permalink
            # AFTER a valid provider ACK stays a separate reconciliation state.
            expected = ("P0_ONCE_PROVIDER_OUTCOME_UNVERIFIED"
                        if missing == "external_post_id"
                        else "PUBLISH_OUTCOME_UNVERIFIED")
            self.assertEqual(result["status"], expected)
            self.assertTrue(result["publish_attempted"])
            expected_updates = [("queue", "PROCESSING")]
            if missing == "posted_url":
                expected_updates.append(("queue", "PUBLISH_OUTCOME_UNVERIFIED"))
            self.assertEqual(status_updates, expected_updates)

    def test_verified_external_publish_but_final_queue_not_saved_never_success(self):
        runner = prior_tests.PrePublishTests(methodName="test_missing_lock_and_429_never_publish")
        runner.setUp()
        queue = dict(runner.row)
        locked = {**queue, "status": "PROCESSING"}
        calls = []
        flags = {"persisted": False}
        def provider(text, **kwargs):
            calls.append(kwargs["dry_run"])
            return SimpleNamespace(
                success=True, message="synthetic_only",
                external_post_id="p_synthetic", posted_url="https://example.invalid/p",
                delivery_state="PUBLISHED",
            )

        def records(_, name):
            if name == "queue":
                return [locked]
            if name == "posted_results":
                if not flags["persisted"]:
                    return []
                return [{
                    "result_id": "r_synthetic",
                    "status": "POSTED",
                    "external_post_id": "p_synthetic",
                    "queue_id": queue["queue_id"],
                    "account_id": queue["account_id"],
                    "verification_status": "READ_AFTER_WRITE_PASS",
                }]
            return []

        for final_result in (False, TimeoutError("private provider response")):
            flags["persisted"] = False
            updates = []
            def save_update(_client, logical, _key, _value, fields):
                updates.append((logical, fields))
                if logical == "queue" and fields.get("status") == "POSTED":
                    if isinstance(final_result, Exception):
                        raise final_result
                    return final_result
                return True
            with self.subTest(final_result=str(final_result)), patch.dict(
                worker.os.environ,
                {"PUBLISH_ENABLED": "true", "ALLOW_REAL_THREADS_POST": "true",
                 "SNS_P0_ONCE_GATE_ENABLED": "true"},
            ), prior_tests.mocked_real_once_ledger(), patch(
                "p0_exact_canary_approval.verify_current",
                return_value={"status": "PASS_ONE_APPROVED_CANARY_SCOPE_ONLY"},
            ), patch.object(worker, "records", side_effect=records), patch.object(
                worker, "update_row", side_effect=save_update,
            ), patch.object(worker, "log_event"), patch.object(
                worker, "ThreadsPublisher",
                return_value=SimpleNamespace(publish=provider),
            ), patch.object(
                worker, "save_posted_result",
                side_effect=lambda *_args, **_kwargs: (
                    flags.__setitem__("persisted", True) or "r_synthetic"
                ),
            ), patch.object(
                worker, "verify_posted_result_persistence",
                return_value={"status": "PASS"},
            ), patch.object(
                worker, "schedule_metrics_after_post",
                side_effect=AssertionError("cannot schedule metrics after unconfirmed queue finalization"),
            ):
                result = worker.process_one(
                    SimpleNamespace(), queue, dry_run=False, confirm_real_post=True,
                )
            self.assertEqual(result["status"], "POSTED_SAVE_UNVERIFIED")
            self.assertTrue(result["publish_attempted"])
            self.assertIn("QUEUE_POSTED_FINALIZATION", result["reason"])
            self.assertEqual(len([p for _, p in updates if p.get("status") == "POSTED"]), 1)
        self.assertEqual(calls, [True, False, True, False])


if __name__ == "__main__":
    unittest.main()
