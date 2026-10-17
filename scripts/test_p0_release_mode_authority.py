#!/usr/bin/env python3
"""Offline adversarial authorization tests. No Google, Threads or SNS network."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from metrics_collection_schedule import build_metric_collection_jobs
from p0_exact_canary_approval import (
    TOKEN as CANARY_TOKEN, signed_manifest, _write_new,
)
from p0_real_delivery_once import P0OnceGuard, initialize_local_db, source_fingerprint
from p0_release_mode_authority import (
    CONT_ATTESTATIONS, CONT_SCHEMA, CONFIRM_CONTINUOUS,
    CanaryBlocked, _approval_name, signed_continuous, verify_release,
)

KEY = bytes.fromhex("67" * 32)
RELEASE = "c" * 40
NOW = datetime(2026, 10, 17, 5, 0, tzinfo=timezone.utc)
ACCOUNT = "night_scout"
QUEUE = "night_canary_valid_123"
TEXT = "これは実際には送信しない合成投稿文章です。"
FINGERPRINT = source_fingerprint(account_id=ACCOUNT, queue_id=QUEUE, text=TEXT)
POST_ID = "1234567890"
RESULT_ID = "result_synthetic_123"


class FakeClient:
    def __init__(self, rows):
        self.rows = rows

    def _ws(self, name):
        rows = self.rows[name]
        headers = list(rows[0]) if rows else (
            ["result_id", "account_id", "queue_id", "external_post_id",
             "status", "platform", "verification_status", "real_post",
             "posted_text", "post_url", "posted_at"]
            if name == "posted_results" else
            ["job_id", "result_id", "account_id", "platform", "post_url",
             "window_hours", "scheduled_for", "status"]
        )

        class WS:
            def get_all_values(self):
                return [headers] + [
                    [str(r.get(k, "")) for k in headers] for r in rows
                ]

        return WS()


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="p0-continuity-test-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.root.chmod(0o700)
        self.db_path = self.root / "once.sqlite3"
        initialize_local_db(str(self.db_path), explicit_operator_init=True,
                            allow_test_path=True)
        self.env = patch.dict(os.environ, {
            "SNS_P0_ONCE_DB_PATH": str(self.db_path),
            "SNS_P0_ONCE_HMAC_KEY_HEX": KEY.hex(),
            "SNS_P0_AUTONOMY_MODE": "continuous",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.canary_result = {
            "result_id": RESULT_ID, "queue_id": QUEUE, "account_id": ACCOUNT,
            "platform": "threads", "status": "POSTED",
            "external_post_id": POST_ID,
            "post_url": "https://www.threads.com/@synthetic/post/1234",
            "verification_status": "READ_AFTER_WRITE_PASS",
            "real_post": "true", "posted_text": TEXT,
            "posted_at": "2026-10-17T04:55:00+00:00",
        }
        jobs = build_metric_collection_jobs([self.canary_result], [], now=NOW)
        self.client = FakeClient({
            "posted_results": [self.canary_result], "metrics_collection_jobs": jobs,
        })

    def request(self, **changes):
        result = {
            "schema": CONT_SCHEMA,
            "account_id": ACCOUNT,
            "release_sha": RELEASE,
            "approved_at_utc": "2026-10-17T04:59:00Z",
            "expires_at_utc": "2026-10-18T04:59:00Z",
            "approval_mode": CONFIRM_CONTINUOUS,
            "canary_queue_id": QUEUE,
            "canary_source_sha256": FINGERPRINT,
            "canary_external_post_id": POST_ID,
            "canary_result_id": RESULT_ID,
            "attestations": {name: True for name in CONT_ATTESTATIONS},
        }
        return {**result, **changes}

    def authorize(self, **changes):
        payload = signed_continuous(self.request(**changes), key=KEY, now=NOW)
        path = self.root / _approval_name(payload)
        _write_new(path, payload)
        return path

    def confirmed_canary(self, *, queue=QUEUE, account=ACCOUNT):
        ledger = P0OnceGuard(str(self.db_path), KEY, allow_test_path=True)
        text = TEXT
        fingerprint = source_fingerprint(account_id=account, queue_id=queue, text=text)
        receipt = ledger.claim(account_id=account, queue_id=queue, source_sha256=fingerprint)
        ledger.consume_send_receipt(
            account_id=account, queue_id=queue, text=text,
            source_sha256=fingerprint, event_mac=receipt["event_mac"],
        )
        ledger.provider_accepted(
            account_id=account, queue_id=queue,
            source_sha256=fingerprint, provider_post_id=POST_ID,
        )
        ledger.verify_posted(
            account_id=account, queue_id=queue, source_sha256=fingerprint,
            provider_post_id=POST_ID, queue_readback_pass=True,
            result_readback_pass=True,
        )

    def check(self, *, client="LIVE", **kwargs):
        actual = self.client if client == "LIVE" else client
        return verify_release(
            account_id=ACCOUNT, release_sha=RELEASE,
            allow_test_path=True, now=NOW, client=actual,
            **kwargs,
        )

    def test_continuous_without_signed_file_never_authorizes(self):
        with self.assertRaises(CanaryBlocked):
            self.check()
        self.assertFalse((self.root / "approved_text_canary.json").exists())

    def test_signature_alone_cannot_substitute_real_ledger_canary(self):
        self.authorize()
        with self.assertRaises(CanaryBlocked):
            self.check(client=None)
        with self.assertRaises(CanaryBlocked):
            self.check()

    def test_claim_or_ack_without_verified_readback_blocks(self):
        self.authorize()
        ledger = P0OnceGuard(str(self.db_path), KEY, allow_test_path=True)
        ledger.claim(account_id=ACCOUNT, queue_id=QUEUE,
                     source_sha256=FINGERPRINT)
        with self.assertRaises(CanaryBlocked):
            self.check()
        ledger.provider_accepted(account_id=ACCOUNT, queue_id=QUEUE,
                                 source_sha256=FINGERPRINT,
                                 provider_post_id=POST_ID)
        with self.assertRaises(CanaryBlocked):
            self.check()

    def test_valid_signed_ledger_and_exact_three_live_metrics(self):
        self.confirmed_canary()
        self.authorize()
        r = self.check()
        self.assertTrue(r["live_provider_evidence_checked"])
        self.assertFalse(r["publish_authorized"])
        self.assertFalse((self.root / "approved_text_canary.json").exists())
        host = self.check(client=None)
        self.assertEqual(host["status"], "P0_CONTINUOUS_HOST_PREFLIGHT_ONLY")
        self.assertFalse(host["publish_authorized"])
        self.assertFalse(host["live_provider_evidence_checked"])

    def test_changing_source_account_queue_or_deployed_sha_blocks(self):
        self.confirmed_canary()
        self.authorize()
        with self.assertRaises(CanaryBlocked):
            verify_release(account_id="liver_manager", release_sha=RELEASE,
                           allow_test_path=True, now=NOW, client=self.client)
        with self.assertRaises(CanaryBlocked):
            verify_release(account_id=ACCOUNT, release_sha="d" * 40,
                           allow_test_path=True, now=NOW, client=self.client)
        bad = dict(self.canary_result)
        bad["posted_text"] = "different text"
        self.client.rows["posted_results"] = [bad]
        with self.assertRaises(CanaryBlocked):
            self.check()

    def test_live_metric_job_absence_duplicate_or_wrong_account_fails(self):
        self.confirmed_canary()
        self.authorize()
        original = list(self.client.rows["metrics_collection_jobs"])
        variants = (
            original[:2],
            original + [original[0]],
            [{**original[0], "account_id": "liver_manager"}] + original[1:],
            [{**original[0], "scheduled_for": "2026-10-17T03:00:00Z"}] + original[1:],
            [{**original[0], "status": "FAILED"}] + original[1:],
        )
        for jobs in variants:
            self.client.rows["metrics_collection_jobs"] = jobs
            with self.subTest(jobs=jobs), self.assertRaises(CanaryBlocked):
                self.check()
        self.client.rows["metrics_collection_jobs"] = original
        self.assertTrue(self.check()["live_provider_evidence_checked"])

    def test_provider_missing_wrong_real_post_or_cross_account_duplicate_fails(self):
        self.confirmed_canary()
        self.authorize()
        old = self.canary_result
        for posts in (
            [],
            [{**old, "real_post": "false"}],
            [{**old, "verification_status": "NOT_VERIFIED"}],
            [{**old, "post_url": "http://www.threads.com/test"}],
            [{**old, "external_post_id": "other"}],
            [old, {**old, "account_id": "liver_manager", "result_id": "other"}],
        ):
            self.client.rows["posted_results"] = posts
            with self.subTest(posts=posts), self.assertRaises(CanaryBlocked):
                self.check()

    def test_one_unresolved_claim_in_account_blocks_unbounded_future(self):
        self.confirmed_canary()
        self.authorize()
        ledger = P0OnceGuard(str(self.db_path), KEY, allow_test_path=True)
        ledger.claim(account_id=ACCOUNT, queue_id="night_ambiguous_other_123",
                     source_sha256="a" * 64)
        with self.assertRaisesRegex(CanaryBlocked, "UNCERTAIN_LEDGER"):
            self.check()

    def test_wrong_or_expired_approval_or_ambiguous_overlaps_fail(self):
        self.confirmed_canary()
        first = self.authorize()
        with self.assertRaises(CanaryBlocked):
            verify_release(account_id=ACCOUNT, release_sha=RELEASE,
                           allow_test_path=True,
                           now=NOW + timedelta(days=4), client=self.client)
        duplicate = signed_continuous(self.request(
            approved_at_utc="2026-10-17T04:58:00Z",
            expires_at_utc="2026-10-18T04:58:00Z",
        ), key=KEY, now=NOW)
        _write_new(self.root / _approval_name(duplicate), duplicate)
        with self.assertRaisesRegex(CanaryBlocked, "AMBIGUOUS"):
            self.check()
        self.assertTrue(first.exists())

    def test_flags_alone_never_override_missing_release_or_bad_modes(self):
        with patch.dict(os.environ, {
            "SNS_P0_AUTONOMY_MODE": "UNSAFE_OVERRIDE",
            "PUBLISH_ENABLED": "true",
            "SNS_P0_ONCE_GATE_ENABLED": "true",
            "ALLOW_REAL_THREADS_POST": "true",
            "BUFFERED_POSTING_ENABLED": "true",
        }):
            with self.assertRaisesRegex(CanaryBlocked, "UNKNOWN_MODE"):
                self.check()

    def test_canary_mode_still_requires_exact_signed_text(self):
        with patch.dict(os.environ, {"SNS_P0_AUTONOMY_MODE": "canary"}):
            with self.assertRaises(CanaryBlocked):
                self.check()
            request = {
                "schema": "sns_p0_exact_text_canary_approval_v1",
                "account_id": ACCOUNT, "slot_id": "test_slot_123",
                "queue_id": QUEUE, "source_sha256": FINGERPRINT,
                "release_sha": RELEASE, "approved_at_utc": "2026-10-17T04:59:00Z",
                "expires_at_utc": "2026-10-17T05:10:00Z",
                "approval_mode": CANARY_TOKEN,
                "attestations": {
                    "external_legacy_writers_frozen": True,
                    "historic_outcomes_reconciled": True,
                    "durable_backup_restored": True,
                    "account_identity_and_rights_approved": True,
                    "exact_text_and_queue_owner_approved": True,
                    "metrics_alerting_and_rollback_prepared": True,
                    "operator_accepts_one_use_no_retry": True,
                },
            }
            signed = signed_manifest(request, key=KEY, now=NOW)
            _write_new(self.root / f"approved_text_canary_{ACCOUNT}.json", signed)
            self.assertEqual(
                self.check(client=None, slot_id="test_slot_123", queue_id=QUEUE,
                           source_sha256=FINGERPRINT)["status"],
                "PASS_ONE_APPROVED_CANARY_SCOPE_ONLY",
            )
            with self.assertRaises(CanaryBlocked):
                self.check(client=None, slot_id="different_slot_123")

    def test_extra_false_or_missing_owner_attestation_is_rejected(self):
        for bad in (
            {**{x: True for x in CONT_ATTESTATIONS},
             "durable_independent_backup_restored": False},
            {x: True for x in CONT_ATTESTATIONS
             if x != "owner_approved_bounded_continuous_text_only"},
            {**{x: True for x in CONT_ATTESTATIONS}, "random_permission": True},
        ):
            with self.assertRaises(CanaryBlocked):
                signed_continuous(self.request(attestations=bad), key=KEY, now=NOW)

    def test_signature_tamper_world_readable_and_symlink_fail(self):
        self.confirmed_canary()
        approval = self.authorize()
        approval.chmod(0o644)
        with self.assertRaises(CanaryBlocked):
            self.check()
        approval.chmod(0o600)
        payload = json.loads(approval.read_text())
        payload["canary_result_id"] = "other"
        approval.write_text(json.dumps(payload))
        approval.chmod(0o600)
        with self.assertRaises(CanaryBlocked):
            self.check()
        approval.unlink()
        target = self.root / "different_file"
        target.write_text("{}")
        approval.symlink_to(target)
        with self.assertRaises(CanaryBlocked):
            self.check()

    def test_failures_never_call_threads_or_post(self):
        with patch("requests.post", side_effect=AssertionError("NO_THREAD_API")) as net:
            with self.assertRaises(CanaryBlocked):
                self.check()
        net.assert_not_called()

    def test_duplicate_signature_output_never_overwrites_history(self):
        payload = signed_continuous(self.request(), key=KEY, now=NOW)
        path = self.root / _approval_name(payload)
        _write_new(path, payload)
        original = path.read_bytes()
        with self.assertRaises(CanaryBlocked):
            _write_new(path, payload)
        self.assertEqual(path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
