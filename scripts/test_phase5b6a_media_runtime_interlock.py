#!/usr/bin/env python3
"""Phase 5B-6A no-network interlock and old READY writer negative tests."""
from __future__ import annotations

import copy
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

from publishers.media_publish_interlock import (  # noqa: E402
    block_legacy_ready_transition,
    media_publish_interlock_reason,
)
from publishers.threads_publisher import ThreadsPublisher  # noqa: E402
from publishers.x_publisher import XPublisher  # noqa: E402
from sheets_client import SheetsClient, MockSheetsClient  # noqa: E402
from media_review_legacy_guard import requires_strict_review_block  # noqa: E402
from publication_review_board import decision_for_row  # noqa: E402
from auto_approve_queue import apply_ready, evaluate_item  # noqa: E402


def text_row():
    return {
        "queue_id": "q_text_001", "account_id": "night_scout",
        "slot_id": "ns_0900_reference", "platform": "threads",
        "status": "WAITING_REVIEW", "public_post_text": "テキストのみです",
    }


def media_row():
    return {
        "queue_id": "q_media_001", "account_id": "night_scout",
        "slot_id": "ns_1800_direct_media", "platform": "threads",
        "status": "WAITING_REVIEW", "media_required": "false",
        "media_asset_id": "asset_private_001", "media_url": "",
        "media_type": "", "public_post_text": "素材利用のテストです",
        "validator_status": "PASS", "internal_leak_status": "PASS",
    }


class FakeWorksheet:
    def __init__(self, rows):
        self.headers = [
            "queue_id", "account_id", "slot_id", "platform", "status",
            "media_required", "media_asset_id", "media_url", "media_type",
            "public_post_text",
        ]
        self.rows = [dict(item) for item in rows]
        self.writes = []

    def row_values(self, index):
        if index == 1:
            return list(self.headers)
        return [str(self.rows[index - 2].get(h, "")) for h in self.headers]

    def find(self, text, in_column):
        for idx, row in enumerate(self.rows, 2):
            if str(row.get(self.headers[in_column - 1], "")) == str(text):
                return type("Cell", (), {"row": idx})()
        return None

    def get_all_values(self):
        return [list(self.headers)] + [
            [str(row.get(h, "")) for h in self.headers] for row in self.rows
        ]

    def batch_update(self, data, **kwargs):
        # Fake the committed grid as Sheets actually does. A mocked ACK
        # without updated cells can no longer satisfy real write readback.
        from gspread.utils import a1_to_rowcol
        for item in data:
            row, col = a1_to_rowcol(item["range"])
            self.rows[row - 2][self.headers[col - 1]] = str(item["values"][0][0])
        self.writes.append(("batch", data, kwargs))

    def append_row(self, data, **kwargs):
        self.writes.append(("append", data, kwargs))


class FakeAutoClient:
    def __init__(self, rows):
        self._queue = [dict(r) for r in rows]
        self._drafts = []
        self._derivatives = []
        self.bulk_calls = []
        self.updated = []
        self.logs = []

    def bulk_update_queue_items(self, updates):
        self.bulk_calls.append(copy.deepcopy(updates))
        return len(updates)

    def update_queue_item(self, queue_id, **fields):
        self.updated.append((queue_id, fields))

    def log(self, **fields):
        self.logs.append(fields)


def auto_plan(qid, account="night_scout"):
    return {"results": [{
        "status": "APPROVABLE", "queue_id": qid, "account_id": account,
        "quality_score": 95, "safety_score": 99, "risk_score": 0,
        "score_total": 194,
    }]}


class TestPhase5B6AMediaRuntimeInterlock(unittest.TestCase):
    def test_media_url_denied_before_credential_or_network_even_with_all_flags(self):
        flags = {
            "PUBLISH_ENABLED": "true", "ALLOW_REAL_THREADS_POST": "true",
            "ALLOW_MEDIA_POSTS": "true", "ALLOW_REAL_THREADS_VIDEO_POST": "true",
            "ALLOW_THREADS_CAROUSEL": "true",
            "ALLOW_THREADS_MIXED_CAROUSEL": "true",
        }
        cases = [
            {"media_url": "https://cdn.example/private.jpg", "media_type": "IMAGE"},
            {"media_url": "https://cdn.example/private.mp4", "media_type": "VIDEO"},
            {"media_urls": ["https://cdn.example/1.jpg", "https://cdn.example/2.jpg"],
             "media_types": ["IMAGE", "IMAGE"]},
            {"media_urls": ["https://cdn.example/1.jpg", "https://cdn.example/2.mp4"],
             "media_types": ["IMAGE", "VIDEO"]},
        ]
        with patch.dict(os.environ, flags, clear=False), patch(
            "publishers.threads_publisher._get_credentials",
            side_effect=AssertionError("credentials must not be read"),
        ), patch(
            "publishers.threads_publisher._create_container",
            side_effect=AssertionError("network called"),
        ), patch(
            "publishers.threads_publisher._create_carousel_container",
            side_effect=AssertionError("network called"),
        ), patch(
            "publishers.threads_publisher._publish_container",
            side_effect=AssertionError("network called"),
        ):
            for item in cases:
                with self.subTest(item=item):
                    result = ThreadsPublisher().publish(
                        "テスト本文", account={"account_id": "night_scout"},
                        derivative={}, queue_item={"queue_id": "q"},
                        dry_run=False, **item,
                    )
                    self.assertFalse(result.success)
                    self.assertIn("MEDIA_AUTHORITY_NOT_CONNECTED", result.message)
                    self.assertIsNone(result.external_post_id)

    def test_forged_approval_media_markers_and_missing_media_flags_never_publish(self):
        flags = {"PUBLISH_ENABLED": "true", "ALLOW_REAL_THREADS_POST": "true",
                 "ALLOW_MEDIA_POSTS": "true", "ALLOW_REAL_THREADS_VIDEO_POST": "true"}
        cases = [
            {"media_asset_id": "asset_abc"},
            {"slot_id": "ns_1800_direct_media", "media_required": "false"},
            {"generation_mode": "approved_source_clip"},
            {"media_urls_json": '["https://private.example/a"]'},
            {"media_asset_ids_json": '["asset_ref"]'},
            {"media_type": "CAROUSEL"},
            {"account_id": "liver_manager"},
        ]
        with patch.dict(os.environ, flags, clear=False), patch(
            "publishers.threads_publisher._get_credentials",
            side_effect=AssertionError("credential access is forbidden"),
        ):
            for override in cases:
                with self.subTest(override=override):
                    q = {
                        "queue_id": "q",
                        "account_id": "night_scout",
                        "platform": "threads",
                        "status": "READY",
                        "human_approved": "true",
                        "authenticated_approval_integrated": "true",
                        "publish_authorized": "true",
                    }
                    q.update(override)
                    result = ThreadsPublisher().publish(
                        "テスト本文", account={"account_id": "night_scout"},
                        derivative={}, queue_item=q, dry_run=False,
                    )
                    self.assertFalse(result.success)
                    self.assertIn("MEDIA_AUTHORITY_NOT_CONNECTED", result.message)

    def test_real_text_only_keeps_previous_logic(self):
        with patch.dict(os.environ, {
            "PUBLISH_ENABLED": "false", "ALLOW_REAL_THREADS_POST": "false",
        }, clear=False):
            result = ThreadsPublisher().publish(
                "テキストのみ", account={"account_id": "night_scout"},
                derivative={}, queue_item=text_row(), dry_run=False,
            )
        self.assertFalse(result.success)
        self.assertIn("PUBLISH_ENABLED", result.message)
        self.assertNotIn("MEDIA_AUTHORITY_NOT_CONNECTED", result.message)
        dry = ThreadsPublisher().publish(
            "テキストのみ", account={"account_id": "night_scout"},
            derivative={}, queue_item=text_row(), dry_run=True,
        )
        self.assertTrue(dry.dry_run)
        self.assertTrue(dry.success)

    def test_x_legacy_media_metadata_never_reaches_credential_loader(self):
        flags = {
            "PUBLISH_ENABLED": "true", "ALLOW_REAL_X_POST": "true",
            "X_PUBLISHER_ENABLED": "true",
        }
        with patch.dict(os.environ, flags, clear=False), patch(
            "config_loader.get_x_credentials",
            side_effect=AssertionError("must not access X credentials"),
        ):
            result = XPublisher().publish(
                "投稿テスト",
                account={"account_id": "liver_manager"},
                derivative={},
                queue_item={
                    "queue_id": "q", "slot_id": "lm_1800_clip_media",
                    "account_id": "liver_manager", "platform": "x",
                }, dry_run=False,
            )
            self.assertFalse(result.success)
            self.assertIn("MEDIA_AUTHORITY_NOT_CONNECTED", result.message)

    def test_interlock_does_not_allow_manual_json_to_override(self):
        base = media_row()
        for fields in (
            {"status": "READY", "media_asset_id": ""},
            {"status": "READY", "slot_id": "", "media_required": "false"},
            {"status": "READY", "human_approved": "true",
             "authenticated_approval_integrated": "true"},
        ):
            self.assertTrue(block_legacy_ready_transition(base, fields))
        self.assertFalse(block_legacy_ready_transition(text_row(), {"status": "READY"}))
        self.assertFalse(block_legacy_ready_transition(base, {"status": "REJECTED"}))
        self.assertTrue(block_legacy_ready_transition(None, {"status": "READY"}))
        self.assertIsNone(media_publish_interlock_reason(
            account={"account_id": "night_scout"}, queue_item=text_row(),
            derivative={},
        ))
        # Source provenance alone is not an attached video.
        reference_text = {
            **text_row(), "source_video_url": "https://reference.example/video",
            "media_urls_json": "[]",
        }
        self.assertIsNone(media_publish_interlock_reason(
            account={"account_id": "night_scout"}, queue_item=reference_text,
            derivative={}, has_media=False,
        ))

    def test_old_sheets_ok_flag_never_promotes_media(self):
        row = media_row()
        review = {"review_decision": "OK", "reviewer_id": "admin",
                  "approval_source": "human_review"}
        for strict in (True, False):
            self.assertTrue(requires_strict_review_block(
                row, desired_status="READY",
                strict_trusted_media_review=strict,
            ))
            state, fields = decision_for_row(
                review, row, allow_media_posts=True,
                strict_trusted_media_review=strict,
            )
            self.assertEqual(state, "BLOCKED_TRUSTED_MEDIA_REVIEW_REQUIRED")
            self.assertEqual(fields, {})

    def test_mock_sheets_append_update_media_denied_but_text_allowed(self):
        mock = MockSheetsClient()
        self.assertRaises(PermissionError, mock.append_queue_item, {
            **media_row(), "status": "READY",
        })
        text = text_row()
        qid = mock.append_queue_item(text)
        mock.update_queue_item(qid, status="READY")
        self.assertEqual(mock.get_queue_item(qid)["status"], "READY")
        with self.assertRaises(PermissionError):
            mock.update_queue_item(qid, status="READY", media_asset_id="asset_x")
        self.assertEqual(mock.get_queue_item(qid).get("media_asset_id"), None)

    def test_real_sheets_legacy_batch_denies_all_writes_when_any_media(self):
        ws = FakeWorksheet([text_row(), media_row()])
        client = object.__new__(SheetsClient)
        client.dry_run = False
        client._ws = lambda name: ws
        client._call_with_rate_limit_retry = lambda label, fn: fn()
        with self.assertRaises(PermissionError):
            client.bulk_update_queue_items([
                ("q_text_001", {"status": "READY"}),
                ("q_media_001", {"status": "READY"}),
            ])
        self.assertEqual(ws.writes, [])
        updated = client.bulk_update_queue_items([
            ("q_text_001", {"status": "READY"}),
        ])
        self.assertEqual(updated, 1)
        self.assertEqual(len(ws.writes), 1)

    def test_real_sheets_single_and_append_never_write_protected_ready(self):
        ws = FakeWorksheet([text_row(), media_row()])
        client = object.__new__(SheetsClient)
        client.dry_run = False
        client._ws = lambda name: ws
        client._call_with_rate_limit_retry = lambda label, fn: fn()
        def write_fields(_ws, _headers, index, fields, **kwargs):
            _ws.rows[index - 2].update(fields)
            _ws.writes.append(("fields", fields, kwargs))
        client._batch_update_fields = write_fields
        with self.assertRaises(PermissionError):
            client.update_queue_item("q_media_001", status="READY")
        with self.assertRaises(PermissionError):
            client.append_queue_item({**media_row(), "status": "READY"})
        self.assertEqual(ws.writes, [])
        client.update_queue_item("q_text_001", status="READY")
        self.assertEqual(len(ws.writes), 1)

    def test_auto_ready_rule_file_cannot_override_protected_media(self):
        result = evaluate_item(
            queue=media_row(), draft=None, derivative=None,
            scores_by_ref={}, existing_texts=[],
            rules={
                "require_no_media_for_auto_ready": False,
                "allow_third_party_media": True,
                "min_quality_score": 0, "min_safety_score": 0,
                "max_risk_score": 100,
            },
        )
        self.assertEqual(result["status"], "REJECTED")
        self.assertIn(
            "trusted_media_review_authority_unavailable", result["reasons"],
        )

    def test_forged_auto_ready_plan_is_stopped_by_source_reread(self):
        client = FakeAutoClient([media_row()])
        result = apply_ready(client, auto_plan("q_media_001"))
        self.assertEqual(result["updated_count"], 0)
        self.assertEqual(result["status"], "BLOCKED_TRUSTED_MEDIA_REVIEW_REQUIRED")
        self.assertFalse(client.updated)
        self.assertFalse(client.bulk_calls)
        self.assertFalse(client.logs)

    def test_lost_source_or_media_added_after_auto_plan_fails_closed(self):
        for sources in ([], [media_row()], [
            {**text_row(), "media_url": "https://cdn.example/clip.png"}
        ]):
            with self.subTest(sources=sources):
                client = FakeAutoClient(sources)
                result = apply_ready(
                    client, auto_plan("q_text_001"),
                )
                self.assertEqual(result["updated_count"], 0)
                self.assertFalse(client.bulk_calls)

    def test_raw_sheets_worker_does_not_append_media_ready(self):
        from process_threads_queue import append_row
        with patch(
            "process_threads_queue.get_ws",
            side_effect=AssertionError("must not write media READY"),
        ):
            with self.assertRaises(PermissionError):
                append_row(object(), "queue", {**media_row(), "status": "READY"})

    def test_raw_sheets_worker_does_not_update_media_ready(self):
        from process_threads_queue import update_row
        ws = FakeWorksheet([media_row()])
        fake = object()
        with patch("process_threads_queue.get_ws", return_value=ws):
            with self.assertRaises(PermissionError):
                update_row(fake, "queue", "queue_id", "q_media_001",
                           {"status": "READY"})
        self.assertEqual(ws.writes, [])

    def test_worker_stops_protected_media_before_processing_write(self):
        from process_threads_queue import process_one
        from accounts.managed_accounts import account_status
        self.assertIn(account_status("night_scout"), ("ACTIVE", "CREDENTIAL_PENDING"))
        class ReadOnly:
            _derivatives = []
            _drafts = []
            _posted_results = []
            def _ws(self, name):
                raise AssertionError("must not open a writing worksheet")
        # Current nonproduction account state can be CREDENTIAL_PENDING,
        # which is separately blocked before any other operation.
        fake = ReadOnly()
        row = {**media_row(), "target_account_id": "night_scout",
               "status": "READY"}
        with patch("process_threads_queue.records", return_value=[]), patch(
            "process_threads_queue.update_row",
            side_effect=AssertionError("worker must not write before approval"),
        ):
            result = process_one(fake, row, dry_run=False, confirm_real_post=True)
        self.assertEqual(result["status"], "SAFETY_STOP_TRUSTED_MEDIA_REVIEW_REQUIRED")
        self.assertNotEqual(result.get("publish_attempted"), True)

    def test_no_media_network_bypass_direct_with_false_flags(self):
        result = ThreadsPublisher().publish(
            "text", account={"account_id": "night_scout"},
            derivative={}, queue_item={"queue_id": "direct"},
            dry_run=False, media_url="https://cdn.example/1.jpg",
            media_type="IMAGE",
        )
        self.assertFalse(result.success)
        self.assertIn("SAFETY_STOP", result.message)


if __name__ == "__main__":
    unittest.main()
