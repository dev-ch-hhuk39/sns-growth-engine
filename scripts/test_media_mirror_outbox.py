#!/usr/bin/env python3
"""Offline checks for Phase 5B-6G's blocked local mirror planning journal."""
from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from media_managed_queue_writer import ManagedQueueBlocked  # noqa: E402
from media_mirror_outbox import (  # noqa: E402
    MirrorOutbox, MirrorOutboxBlocked, initialize_mirror_outbox_schema,
)
import test_media_managed_queue_writer as fixtures  # noqa: E402

KEY, NOW, ISSUER = fixtures.KEY, fixtures.NOW, fixtures.ISSUER


class MirrorOutboxTests(fixtures.ManagedQueueWriterTests):
    """Includes 6F and earlier review/rights regression tests."""

    def setUp(self):
        super().setUp()
        initialize_mirror_outbox_schema(self.db)
        self.outbox = MirrorOutbox(self.db)

    def ident(self):
        return self.writer.inspect(key=KEY)["writer_event_sha256"]

    def claim(self, ident=None, operation="mirror_claim_20261012_00001", **kw):
        ident = ident or self.ident()
        old = self.outbox.inspect(event_sha256=ident)
        args = {
            "event_sha256": ident, "operation_id": operation,
            "expected_outbox_version": old["outbox_version"],
            "expected_head_sha256": old["audit_sha256"],
            "verifier": self.verifier, "bearer": self.bearer,
            "trusted_issuer": ISSUER, "as_of": NOW,
        }
        args.update(kw)
        return self.outbox.claim_preview(**args)

    def stop(self, action, ident=None, **kw):
        ident = ident or self.ident()
        old = self.outbox.inspect(event_sha256=ident)
        args = {
            "event_sha256": ident,
            "operation_id": "mirror_stop_20261012_00001",
            "expected_outbox_version": old["outbox_version"],
            "expected_head_sha256": old["audit_sha256"],
            "action": action, "verifier": self.verifier,
            "bearer": self.bearer, "trusted_issuer": ISSUER, "as_of": NOW,
        }
        args.update(kw)
        return self.outbox.stop(**args)

    def test_missing_schema_is_rejected(self):
        db = sqlite3.connect(":memory:", isolation_level=None)
        try:
            with self.assertRaises(MirrorOutboxBlocked):
                initialize_mirror_outbox_schema(db)
        finally:
            db.close()

    def test_enqueued_in_same_writer_transaction(self):
        self.prepare()
        ident = self.ident()
        self.assertEqual(self.outbox.pending_preview_ids(), [ident])
        self.assertEqual(self.outbox.inspect(event_sha256=ident)["status"], "QUEUED_BLOCKED")
        self.assertEqual(self.count("sns_media_mirror_outbox_heads"), 1)

    def test_claim_is_preview_only_and_never_posts(self):
        self.prepare()
        result = self.claim()
        self.assertEqual(result["status"], "CLAIMED_BLOCKED")
        self.assertTrue(result["mirror_preview"]["view_only"])
        for flag in ("publish_authorized", "dispatch_allowed", "mirror_confirmed",
                     "sync_executed", "sheets_write_allowed"):
            self.assertFalse(result[flag])
        self.assertNotIn("public_post_text", str(result))
        self.assertEqual(self.outbox.pending_preview_ids(), [])

    def test_bad_credential_does_not_claim(self):
        self.prepare()
        with self.assertRaises(MirrorOutboxBlocked):
            self.claim(bearer="Bearer invalid")
        self.assertEqual(self.count("sns_media_mirror_outbox_events"), 1)

    def test_stale_preview_is_permanently_superseded(self):
        self.prepare()
        prior = self.ident()
        self.change("HOLD")
        current = self.ident()
        self.assertNotEqual(prior, current)
        self.assertEqual(self.claim(ident=prior)["status"], "SUPERSEDED_BLOCKED")
        self.assertEqual(
            self.claim(ident=current, operation="mirror_claim_latest_20261012_01")[
                "status"
            ], "CLAIMED_BLOCKED",
        )

    def test_uncertain_outcome_cannot_be_retried_or_acknowledged(self):
        self.prepare()
        self.claim()
        self.assertEqual(self.stop("UNCERTAIN")["status"], "UNCERTAIN_BLOCKED")
        with self.assertRaises(MirrorOutboxBlocked):
            self.claim(operation="mirror_claim_retry_20261012_01")
        with self.assertRaises(MirrorOutboxBlocked):
            self.outbox.acknowledge_external_delivery(success=True)

    def test_cancel_cannot_be_reopened(self):
        self.prepare()
        self.assertEqual(self.stop("CANCEL")["status"], "CANCELLED_BLOCKED")
        with self.assertRaises(MirrorOutboxBlocked):
            self.claim()

    def test_stale_version_fails_closed(self):
        self.prepare()
        with self.assertRaises(MirrorOutboxBlocked):
            self.claim(expected_outbox_version=2)
        self.assertEqual(self.count("sns_media_mirror_outbox_events"), 1)

    def test_outbox_insert_fault_rolls_back_writer(self):
        self.capture()
        self.db.execute(
            """CREATE TRIGGER fail_outbox_insert BEFORE INSERT
               ON sns_media_mirror_outbox_heads
               BEGIN SELECT RAISE(ABORT,'fault'); END""",
        )
        with self.assertRaises(ManagedQueueBlocked):
            self.bind()
        self.assertEqual(self.count("sns_media_managed_queue_heads"), 0)
        self.assertEqual(self.count("sns_media_sheet_mirror_previews"), 0)
        self.assertFalse(self.db.in_transaction)

    def test_event_immutability_and_head_tamper(self):
        self.prepare()
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("DELETE FROM sns_media_mirror_outbox_events")
        self.db.execute(
            "UPDATE sns_media_mirror_outbox_heads SET projection_sha256=?",
            ("f" * 64,),
        )
        with self.assertRaises(MirrorOutboxBlocked):
            self.outbox.inspect(event_sha256=self.ident())


if __name__ == "__main__":
    unittest.main()
