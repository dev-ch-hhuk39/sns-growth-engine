#!/usr/bin/env python3
"""Offline network-sink tests for the durable one-use Threads text authority."""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from p0_real_delivery_once import (  # noqa: E402
    P0OnceBlocked, P0OnceGuard, initialize_local_db, source_fingerprint,
)
from publishers.threads_outbound_scope import claimed_text_delivery  # noqa: E402
from publishers.threads_publisher import (  # noqa: E402
    ThreadsPublisher, _create_container, _publish_container,
)

ACCOUNT = "night_scout"
QUEUE = "night_outbound_test_0001"
TEXT = "体験入店では時給だけでなく、客層や出勤ペースを確認すると店選びの判断がしやすくなります。"
KEY = bytes.fromhex("88" * 32)


class Response:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self.data


class OutboundOnceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="p0-outbound-unit-")
        self.addCleanup(self.tmp.cleanup)
        self.path = str(Path(self.tmp.name) / "once.sqlite3")
        initialize_local_db(self.path, explicit_operator_init=True, allow_test_path=True)
        self.ledger = P0OnceGuard(self.path, KEY, allow_test_path=True)
        self.source = source_fingerprint(
            account_id=ACCOUNT, queue_id=QUEUE, text=TEXT)

    def claimed(self):
        receipt = self.ledger.claim(
            account_id=ACCOUNT, queue_id=QUEUE, source_sha256=self.source)
        return self.scope(receipt)

    def scope(self, receipt, *, account=ACCOUNT, queue=QUEUE,
              text=TEXT, source=None, ledger=None):
        return claimed_text_delivery(
            ledger=ledger or self.ledger, receipt=receipt,
            account_id=account, queue_id=queue, text=text,
            source_sha256=self.source if source is None else source,
        )

    def post(self, user_id="test_user", text=TEXT):
        return _create_container(user_id, "offline_token", text,
                                 account_id=ACCOUNT, queue_id=QUEUE)

    def publish(self, container_id="offline_container", user_id="test_user"):
        return _publish_container(
            user_id, "offline_token", container_id,
            account_id=ACCOUNT, queue_id=QUEUE)

    def test_direct_low_level_http_calls_cannot_send_without_claim(self):
        with patch("requests.post", side_effect=AssertionError("no network")) as network:
            with self.assertRaisesRegex(PermissionError, "SCOPE_REQUIRED"):
                self.post()
            with self.assertRaisesRegex(PermissionError, "SCOPE_REQUIRED"):
                self.publish()
        network.assert_not_called()

    def test_one_claim_allows_exactly_one_container_and_one_publish(self):
        requests = []
        def fake(url, **kwargs):
            requests.append(url)
            return Response({"id": "offline_container" if url.endswith("/threads")
                             else "offline_post"})
        with patch("requests.post", side_effect=fake):
            with self.claimed():
                self.assertEqual(self.post(), "offline_container")
                self.assertEqual(self.publish()["id"], "offline_post")
                with self.assertRaisesRegex(PermissionError, "SCOPE_REQUIRED"):
                    self.post()
                with self.assertRaisesRegex(PermissionError, "SCOPE_REQUIRED"):
                    self.publish()
        self.assertEqual(len(requests), 2)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM sns_p0_once_send_attempts").fetchone()[0],
                1,
            )
        receipt = {
            "status": "CLAIMED_UNCERTAIN",
            "event_mac": self.ledger.inspect(queue_id=QUEUE).get("event_mac", ""),
        }
        with self.assertRaises(P0OnceBlocked):
            with self.scope(receipt):
                self.post()

    def test_post_crash_cannot_reuse_same_claim_even_after_new_guard_instance(self):
        created = []
        def ambiguous(url, **kwargs):
            created.append(url)
            raise TimeoutError("unknown provider result")
        receipt = self.ledger.claim(
            account_id=ACCOUNT, queue_id=QUEUE, source_sha256=self.source)
        with patch("requests.post", side_effect=ambiguous):
            with self.scope(receipt):
                with self.assertRaises(TimeoutError):
                    self.post()
        again = P0OnceGuard(self.path, KEY, allow_test_path=True)
        with patch("requests.post", side_effect=AssertionError("no retry")) as network:
            with self.assertRaises(P0OnceBlocked):
                with self.scope(receipt, ledger=again):
                    self.post()
        self.assertEqual(len(created), 1)
        network.assert_not_called()

    def test_text_account_and_claim_mac_cannot_be_substituted(self):
        receipt = self.ledger.claim(
            account_id=ACCOUNT, queue_id=QUEUE, source_sha256=self.source)
        for kwargs in (
            {"text": TEXT + "changed"},
            {"account": "liver_manager"},
            {"queue": "night_other_123456"},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(P0OnceBlocked):
                with self.scope(receipt, **kwargs):
                    pass
        with self.assertRaises(P0OnceBlocked):
            with self.scope({**receipt, "event_mac": "f" * 64}):
                pass
        with sqlite3.connect(self.path) as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM sns_p0_once_send_attempts").fetchone()[0],
                0,
            )

    def test_wrong_user_or_publish_before_create_never_calls_http(self):
        def fake(url, **kwargs):
            return Response({"id": "offline_container"})
        with patch("requests.post", side_effect=fake) as network:
            with self.claimed():
                with self.assertRaisesRegex(PermissionError, "SCOPE_REQUIRED"):
                    self.publish()
                self.post()
                with self.assertRaisesRegex(PermissionError, "SCOPE_REQUIRED"):
                    self.publish(user_id="different")
        self.assertEqual(network.call_count, 1)

    def test_simultaneous_http_claims_use_single_durable_attempt(self):
        receipt = self.ledger.claim(
            account_id=ACCOUNT, queue_id=QUEUE, source_sha256=self.source)
        barrier = threading.Barrier(2)
        outcome = []
        output_lock = threading.Lock()
        calls = []
        def fake(url, **kwargs):
            with output_lock:
                calls.append(url)
            return Response({"id": "offline_container"})
        def run():
            try:
                barrier.wait(5)
                with self.scope(receipt, ledger=P0OnceGuard(
                    self.path, KEY, allow_test_path=True)):
                    self.post()
                result = "SENT"
            except (P0OnceBlocked, PermissionError):
                result = "BLOCKED"
            with output_lock:
                outcome.append(result)
        with patch("requests.post", side_effect=fake):
            workers = [threading.Thread(target=run) for _ in range(2)]
            for job in workers:
                job.start()
            for job in workers:
                job.join(8)
        self.assertEqual(sorted(outcome), ["BLOCKED", "SENT"])
        self.assertEqual(len(calls), 1)

    def test_direct_public_publisher_with_env_flags_still_cannot_call_http(self):
        with patch.dict(os.environ, {
            "PUBLISH_ENABLED": "true", "ALLOW_REAL_THREADS_POST": "true",
            "SNS_P0_ONCE_GATE_ENABLED": "true",
        }), patch("publishers.threads_publisher._get_credentials",
                 return_value=("offline_token", "test_user")), patch(
            "publishers.threads_publisher._check_threads", return_value=(True, "ok"),
        ), patch("requests.post", side_effect=AssertionError("UNSAFE_HTTP")) as network:
            result = ThreadsPublisher().publish(
                TEXT, account={"account_id": ACCOUNT}, derivative={},
                queue_item={"queue_id": QUEUE}, dry_run=False)
        self.assertFalse(result.success)
        self.assertEqual(result.delivery_state, "NO_PROVIDER_CALL")
        self.assertIn("P0_ONCE_OUTBOUND_SCOPE_REQUIRED", result.message)
        network.assert_not_called()

    def test_public_publisher_with_valid_scope_can_complete_offline(self):
        calls = []
        def fake(url, **kwargs):
            calls.append(url)
            return Response({"id": "offline_container" if url.endswith("/threads")
                             else "offline_post"})
        with patch.dict(os.environ, {
            "PUBLISH_ENABLED": "true", "ALLOW_REAL_THREADS_POST": "true",
        }), patch("publishers.threads_publisher._get_credentials",
                 return_value=("offline_token", "test_user")), patch(
            "publishers.threads_publisher._check_threads", return_value=(True, "ok"),
        ), patch("publishers.threads_publisher._try_fetch_permalink",
                 return_value="https://example.invalid/post"), patch(
            "publishers.threads_publisher.time.sleep", return_value=None,
        ), patch("requests.post", side_effect=fake):
            with self.claimed():
                result = ThreadsPublisher().publish(
                    TEXT, account={"account_id": ACCOUNT}, derivative={},
                    queue_item={"queue_id": QUEUE, "account_id": ACCOUNT,
                                "platform": "threads"}, dry_run=False)
        self.assertTrue(result.success, result.message)
        self.assertEqual(result.external_post_id, "offline_post")
        self.assertEqual(len(calls), 2)

    def test_fake_ledger_cannot_mint_real_network_scope(self):
        with self.assertRaisesRegex(PermissionError, "SCOPE_REQUIRED"):
            with claimed_text_delivery(
                ledger=object(), receipt={
                    "status": "CLAIMED_UNCERTAIN", "event_mac": "a" * 64,
                }, account_id=ACCOUNT, queue_id=QUEUE, text=TEXT,
                source_sha256=self.source,
            ):
                pass

    def test_gate_disabled_blocks_before_any_queue_mutation(self):
        import process_threads_queue as worker
        from test_pre_publish_sheets_failure import PrePublishTests
        from types import SimpleNamespace
        fixture = PrePublishTests("test_missing_lock_and_429_never_publish")
        fixture.setUp()
        attempts = []
        def publisher(text, **kwargs):
            attempts.append(kwargs["dry_run"])
            return SimpleNamespace(success=True, message="synthetic dry-run")
        with patch.dict(os.environ, {
            "PUBLISH_ENABLED": "true", "ALLOW_REAL_THREADS_POST": "true",
            "SNS_P0_ONCE_GATE_ENABLED": "false",
        }), patch.object(
            worker, "records", return_value=[],
        ), patch.object(
            worker, "update_row", side_effect=AssertionError("no Sheets writes"),
        ), patch.object(
            worker, "ThreadsPublisher",
            return_value=SimpleNamespace(publish=publisher),
        ):
            result = worker.process_one(
                SimpleNamespace(), fixture.row, dry_run=False,
                confirm_real_post=True,
            )
        self.assertEqual(result["status"], "P0_ONCE_PREPUBLISH_BLOCKED")
        self.assertFalse(result["publish_attempted"])
        self.assertEqual(attempts, [True])

    def test_real_cli_blocks_before_get_config_or_sheets_client(self):
        import process_threads_queue as worker
        with patch.dict(os.environ, {"SNS_P0_ONCE_GATE_ENABLED": "false"}), patch(
            "sys.argv", ["process_threads_queue.py", "--account-id",
                         ACCOUNT, "--confirm-real-post"],
        ), patch.object(
            worker, "get_config",
            side_effect=AssertionError("must not open production configuration"),
        ), patch.object(
            worker, "SheetsClient",
            side_effect=AssertionError("must not open Google Sheets"),
        ):
            result = worker.main()
        self.assertEqual(result, 1)

    def test_send_attempt_journal_is_immutable(self):
        with patch("requests.post", return_value=Response({"id": "offline_container"})):
            with self.claimed():
                self.post()
        with sqlite3.connect(self.path) as db:
            for command in (
                "UPDATE sns_p0_once_send_attempts SET account_id='liver_manager'",
                "DELETE FROM sns_p0_once_send_attempts",
            ):
                with self.subTest(command=command), self.assertRaises(sqlite3.Error):
                    db.execute(command)


if __name__ == "__main__":
    unittest.main(verbosity=2)
