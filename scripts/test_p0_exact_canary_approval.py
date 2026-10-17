#!/usr/bin/env python3
"""Adversarial no-network tests of independent exact-owner canary activation."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from p0_exact_canary_approval import (
    ATTESTATIONS, DOC_FIELDS, TOKEN, CanaryBlocked,
    _decode, _read_private, _write_new, signed_manifest, verify_current,
)
from p0_real_delivery_once import source_fingerprint

KEY = bytes.fromhex("17" * 32)
RELEASE = "a45ed15f05095b283728be94b84d72957237a44f"
ACCOUNT = "night_scout"
QUEUE = "night_exact_queue_123"
SLOT = "night_0800_slot"
SOURCE = source_fingerprint(
    account_id=ACCOUNT, queue_id=QUEUE, text="実投稿しない合成テスト文章です。",
)
NOW = datetime(2026, 10, 17, 5, 0, tzinfo=timezone.utc)


class CanaryApprovalTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory(prefix="sns-p0-owner-proof-")
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name).resolve()
        self.folder.chmod(0o700)
        self.db = self.folder / "once.sqlite3"
        self.path = self.folder / f"approved_text_canary_{ACCOUNT}.json"
        self.clean_env = patch.dict(os.environ, {
            "SNS_P0_ONCE_DB_PATH": str(self.db),
            "SNS_P0_ONCE_HMAC_KEY_HEX": KEY.hex(),
        })
        self.clean_env.start()
        self.addCleanup(self.clean_env.stop)

    def request(self, **kwargs) -> dict:
        raw = {
            "schema": "sns_p0_exact_text_canary_approval_v1",
            "account_id": ACCOUNT,
            "slot_id": SLOT,
            "queue_id": QUEUE,
            "source_sha256": SOURCE,
            "release_sha": RELEASE,
            "approved_at_utc": "2026-10-17T04:57:00Z",
            "expires_at_utc": "2026-10-17T05:17:00Z",
            "approval_mode": TOKEN,
            "attestations": {key: True for key in ATTESTATIONS},
        }
        return {**raw, **kwargs}

    def save(self, **kwargs) -> dict:
        document = signed_manifest(self.request(**kwargs), key=KEY, now=NOW)
        _write_new(self.path, document)
        self.path.chmod(0o600)
        return document

    def check(self, **kwargs):
        return verify_current(
            account_id=ACCOUNT, release_sha=RELEASE,
            allow_test_path=True, now=NOW, **kwargs,
        )

    def test_two_accounts_have_independent_immutable_canary_approvals(self) -> None:
        from p0_exact_canary_approval import _filename
        other = "liver_manager"
        other_doc = self.request(account_id=other, queue_id="liver_other_queue_456")
        signed = signed_manifest(other_doc, key=KEY, now=NOW)
        other_path = _filename(allow_test_path=True, account_id=other)
        _write_new(other_path, signed)
        self.assertNotEqual(other_path, self.path)
        self.assertFalse(self.path.exists())
        with self.assertRaises(CanaryBlocked):
            self.check()
        result = verify_current(account_id=other, release_sha=RELEASE,
                                allow_test_path=True, now=NOW)
        self.assertEqual(result["status"], "PASS_ONE_APPROVED_CANARY_SCOPE_ONLY")
        self.save()
        self.assertEqual(self.check()["status"], "PASS_ONE_APPROVED_CANARY_SCOPE_ONLY")
        self.assertEqual(other_path.read_bytes(), (
            json.dumps(signed, ensure_ascii=True,
                       sort_keys=True, separators=(",", ":")) + "\n").encode("ascii"))

    def test_two_switches_without_manifest_cannot_publish(self) -> None:
        with self.assertRaisesRegex(CanaryBlocked, "UNAVAILABLE"):
            self.check()
        with patch.dict(os.environ, {
            "BUFFERED_POSTING_ENABLED": "true",
            "SNS_P0_ONCE_GATE_ENABLED": "true",
            "PUBLISH_ENABLED": "true",
            "ALLOW_REAL_THREADS_POST": "true",
        }):
            with self.assertRaises(CanaryBlocked):
                self.check()

    def test_valid_private_signature_allows_exact_scope_only(self) -> None:
        self.save()
        report = self.check(slot_id=SLOT, queue_id=QUEUE, source_sha256=SOURCE)
        self.assertEqual(report["status"], "PASS_ONE_APPROVED_CANARY_SCOPE_ONLY")
        self.assertFalse(report["automated_publish_authorized"])
        self.assertFalse(report["production_cutover_authorized"])
        self.assertFalse(report["independent_provider_evidence_verified"])
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_wrong_account_release_queue_slot_and_text_block(self) -> None:
        self.save()
        for changes in (
            dict(account_id="liver_manager", release_sha=RELEASE),
            dict(account_id=ACCOUNT, release_sha="e" * 40),
            dict(slot_id="different_slot"),
            dict(queue_id="different_queue"),
            dict(source_sha256="b" * 64),
        ):
            with self.subTest(changes=changes):
                args = dict(account_id=ACCOUNT, release_sha=RELEASE,
                            allow_test_path=True, now=NOW,
                            slot_id=SLOT, queue_id=QUEUE,
                            source_sha256=SOURCE)
                args.update(changes)
                with self.assertRaises(CanaryBlocked):
                    verify_current(**args)

    def test_reissue_expired_or_future_timestamp_block(self) -> None:
        self.save()
        for moment in (
            NOW - timedelta(minutes=5),
            NOW + timedelta(minutes=25),
            NOW + timedelta(days=1),
        ):
            with self.subTest(moment=moment), self.assertRaises(CanaryBlocked):
                verify_current(account_id=ACCOUNT, release_sha=RELEASE,
                               allow_test_path=True, now=moment)

    def test_attestation_false_or_missing_is_rejected(self) -> None:
        for bad in (
            {**{k: True for k in ATTESTATIONS}, "durable_backup_restored": False},
            {k: True for k in ATTESTATIONS if k != "historic_outcomes_reconciled"},
            {**{k: True for k in ATTESTATIONS}, "made_up_approval": True},
        ):
            with self.subTest(bad=bad), self.assertRaises(CanaryBlocked):
                signed_manifest(self.request(attestations=bad), key=KEY, now=NOW)

    def test_no_signer_writes_to_existing_file(self) -> None:
        self.save()
        old = self.path.read_bytes()
        with self.assertRaisesRegex(CanaryBlocked, "ALREADY_EXISTS"):
            _write_new(self.path, self.request())
        self.assertEqual(old, self.path.read_bytes())

    def test_tampered_fields_and_signature_block(self) -> None:
        original = self.save()
        for modified in (
            {**original, "queue_id": "other_queue_01"},
            {**original, "signature": "f" * 64},
            {**original, "attestations": {
                **original["attestations"], "durable_backup_restored": False,
            }},
        ):
            self.path.write_text(json.dumps(modified))
            with self.subTest(modified=modified), self.assertRaises(CanaryBlocked):
                self.check()

    def test_duplicate_json_keys_and_extra_field_block(self) -> None:
        self.path.write_text('{"account_id":"night_scout","account_id":"liver_manager"}')
        self.path.chmod(0o600)
        with self.assertRaisesRegex(CanaryBlocked, "DUPLICATE_KEYS"):
            self.check()
        self.path.unlink()
        doc = self.save()
        self.path.write_text(json.dumps({**doc, "unknown": True}))
        with self.assertRaises(CanaryBlocked):
            self.check()

    def test_nonprivate_and_symlink_file_are_rejected(self) -> None:
        self.save()
        self.path.chmod(0o644)
        with self.assertRaisesRegex(CanaryBlocked, "UNSAFE"):
            self.check()
        self.path.chmod(0o600)
        moved = self.folder / "other_manifest.json"
        self.path.rename(moved)
        self.path.symlink_to(moved)
        with self.assertRaises(CanaryBlocked):
            self.check()

    def test_source_tree_or_arbitrary_symlink_parent_block(self) -> None:
        outside = self.folder / "other"
        outside.mkdir()
        alias = self.folder / "alias"
        alias.symlink_to(outside, target_is_directory=True)
        with patch.dict(os.environ, {
            "SNS_P0_ONCE_DB_PATH": str(alias / "once.sqlite3"),
        }):
            with self.assertRaises(CanaryBlocked):
                self.check()

    def test_invalid_untrusted_account_type_fails_without_exception_leak(self) -> None:
        doc = self.request(account_id=["night_scout"])
        with self.assertRaises(CanaryBlocked):
            signed_manifest(doc, key=KEY, now=NOW)

    def test_file_size_and_signature_key_block(self) -> None:
        self.save()
        self.path.write_bytes(b"x" * 10000)
        with self.assertRaises(CanaryBlocked):
            self.check()
        self.path.unlink()
        self.save()
        with patch.dict(os.environ, {"SNS_P0_ONCE_HMAC_KEY_HEX": "weak"}):
            with self.assertRaises(CanaryBlocked):
                self.check()

    def test_rejection_never_calls_any_provider_or_mutates_ledger(self) -> None:
        with patch("socket.socket", side_effect=AssertionError("NO_NETWORK")):
            with self.assertRaises(CanaryBlocked):
                self.check()
        self.assertFalse(self.db.exists())

    def test_no_sensitive_information_in_success_report(self) -> None:
        self.save()
        output = json.dumps(self.check())
        self.assertNotIn(QUEUE, output)
        self.assertNotIn(SLOT, output)
        self.assertNotIn(SOURCE, output)
        self.assertNotIn(KEY.hex(), output)
        self.assertNotIn(str(self.db), output)


if __name__ == "__main__":
    unittest.main()
