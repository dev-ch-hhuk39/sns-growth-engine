#!/usr/bin/env python3
"""Offline 5B-6I service identity, isolated destination, CAS/readback tests."""
from __future__ import annotations

import base64
import json
import sqlite3
import sys
import unittest
from datetime import timedelta
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from media_mirror_rehearsal import (  # noqa: E402
    InMemoryReportingReplica, MirrorRehearsalBlocked,
    MirrorServiceRehearsal, PinnedMirrorServiceVerifier,
    SERVICE_AUDIENCE, SERVICE_SCOPE, SERVICE_USE,
    initialize_mirror_rehearsal_schema,
)
import test_media_mirror_outbox as fixtures  # noqa: E402

NOW, ISSUER, KEY = fixtures.NOW, fixtures.ISSUER, fixtures.KEY
T = int(NOW.timestamp())
DEST = "destination_reporting_0001"
SUB = "mirror_rehearsal_service_001"
SID = "mirror_rehearsal_session_001"
JTI = "mirror_rehearsal_jti_001"
KID = "mirror_rehearsal_key_20261012"
ORIG = "operational_sheet_00001"
REPORT = "reporting_sheet_00001"


def _b64(data):
    return base64.urlsafe_b64encode(
        json.dumps(data,sort_keys=True,separators=(",",":")).encode("ascii"),
    ).decode("ascii").rstrip("=")


class MirrorRehearsalTests(fixtures.MirrorOutboxTests):
    """Inherited protected review/outbox tests plus separate service tests."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.service_private = rsa.generate_private_key(
            public_exponent=65537, key_size=2048,
        )
        cls.service_public = cls.service_private.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    @classmethod
    def service_token(cls, overrides=None, header_overrides=None):
        claims = {
            "iss": ISSUER, "aud": SERVICE_AUDIENCE,
            "token_use": SERVICE_USE, "scope": SERVICE_SCOPE,
            "sub": SUB, "sid": SID, "jti": JTI,
            "iat": T - 60, "nbf": T - 60, "exp": T + 180,
        }
        claims.update(overrides or {})
        header = {"alg": "RS256", "typ": "JWT", "kid": KID}
        header.update(header_overrides or {})
        message = _b64(header) + "." + _b64(claims)
        signature = cls.service_private.sign(
            message.encode("ascii"), padding.PKCS1v15(), hashes.SHA256(),
        )
        return message + "." + base64.urlsafe_b64encode(signature).decode().rstrip("=")

    def setUp(self):
        super().setUp()
        initialize_mirror_rehearsal_schema(self.db)
        self.service_jwt = self.service_token()
        self.db.execute(
            """INSERT INTO sns_mirror_rehearsal_service_sessions(
               session_id,subject,issuer,token_sha256,token_jti,
               issued_at,expires_at,revoked_at,enabled)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (SID,SUB,ISSUER,__import__("hashlib").sha256(
                self.service_jwt.encode("ascii"),
            ).hexdigest(),JTI,T-60,T+180,None,1),
        )
        self.db.execute(
            """INSERT INTO sns_mirror_rehearsal_destinations(
               destination_id,account_id,service_subject,
               reporting_spreadsheet_id,operational_spreadsheet_id,
               reporting_tab,mode,enabled)
               VALUES(?,?,?,?,?,?,?,?)""",
            (DEST,KEY[0],SUB,REPORT,ORIG,"mirror_preview_internal",
             "ISOLATED_REPORTING_ONLY",1),
        )
        self.verifier_service = PinnedMirrorServiceVerifier(
            db=self.db, issuer=ISSUER, public_keys_by_kid={KID:self.service_public},
        )
        self.replica = InMemoryReportingReplica()
        self.runner = MirrorServiceRehearsal(
            db=self.db, verifier=self.verifier_service, replica=self.replica,
        )

    def claimed(self):
        self.prepare()
        self.claim()
        return self.ident()

    def simulate(self, event=None, **kwargs):
        defaults = {
            "event_sha256": event or self.ident(),
            "destination_id": DEST, "token": self.service_jwt,
            "operation_id": "rehearsal_run_20261012_000001",
            "as_of": NOW,
        }
        defaults.update(kwargs)
        return self.runner.run_once(**defaults)

    def reconcile(self, event=None, **kwargs):
        event = event or self.ident()
        current = self.runner.inspect(event_sha256=event,destination_id=DEST)
        defaults = {
            "event_sha256": event, "destination_id": DEST,
            "token": self.service_jwt,
            "operation_id": "rehearsal_reconcile_20261012_000001",
            "expected_version": current["version"],
            "expected_audit_sha256": current["audit_sha256"],
            "as_of": NOW,
        }
        defaults.update(kwargs)
        return self.runner.readback_only(**defaults)

    def test_migration_requires_prior_outbox_schema(self):
        db=sqlite3.connect(":memory:",isolation_level=None)
        try:
            with self.assertRaises(MirrorRehearsalBlocked):
                initialize_mirror_rehearsal_schema(db)
        finally:
            db.close()

    def test_signed_service_isolated_from_reviewer_jwt(self):
        self.claimed()
        with self.assertRaises(MirrorRehearsalBlocked):
            self.simulate(token=self.bearer)
        self.assertEqual(self.count("sns_mirror_rehearsal_heads"),0)
        self.assertEqual(self.replica.write_calls,0)

    def test_invalid_service_signature_and_claims_denied(self):
        self.claimed()
        invalid = (
            self.service_jwt[:-12]+"corrupt_bytes",
            self.service_token({"aud":"sns-growth-media-review"}),
            self.service_token({"token_use":"media_review"}),
            self.service_token({"scope":"mirror:publish"}),
            self.service_token({"exp":T+1000}),
            self.service_token(header_overrides={"alg":"HS256"}),
        )
        for token in invalid:
            with self.subTest(kind=token[:10]), self.assertRaises(
                MirrorRehearsalBlocked,
            ):
                self.simulate(token=token)
        self.assertEqual(self.replica.write_calls,0)

    def test_disabled_service_or_revoked_session_denied(self):
        self.claimed()
        self.db.execute(
            "UPDATE sns_mirror_rehearsal_service_sessions SET revoked_at=?",
            (T,),
        )
        with self.assertRaises(MirrorRehearsalBlocked):
            self.simulate()
        self.assertEqual(self.count("sns_mirror_rehearsal_events"),0)

    def test_disabled_and_wrong_account_destination_denied(self):
        self.claimed()
        self.db.execute(
            "UPDATE sns_mirror_rehearsal_destinations SET enabled=0",
        )
        with self.assertRaises(MirrorRehearsalBlocked):
            self.simulate()
        self.db.execute(
            "UPDATE sns_mirror_rehearsal_destinations SET enabled=1,account_id='night_scout'",
        )
        with self.assertRaises(MirrorRehearsalBlocked):
            self.simulate()
        self.assertEqual(self.replica.write_calls,0)

    def test_source_and_reporting_spreadsheet_must_be_distinct(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                """UPDATE sns_mirror_rehearsal_destinations
                   SET reporting_spreadsheet_id=operational_spreadsheet_id""",
            )
        self.assertEqual(self.replica.write_calls,0)

    def test_only_provisioned_destination_allowed(self):
        self.claimed()
        with self.assertRaises(MirrorRehearsalBlocked):
            self.simulate(destination_id="unexpected_destination_0001")
        self.assertEqual(self.count("sns_mirror_rehearsal_heads"),0)

    def test_outbox_must_have_signed_review_claim(self):
        self.prepare()
        with self.assertRaises(MirrorRehearsalBlocked):
            self.simulate()
        self.assertEqual(self.replica.write_calls,0)

    def test_successful_offline_readback_is_not_external_confirmation(self):
        event = self.claimed()
        result = self.simulate(event)
        self.assertEqual(result["status"],"SIMULATED_READBACK_BLOCKED")
        self.assertTrue(result["simulated_readback_verified"])
        self.assertFalse(result["external_delivery_confirmed"])
        self.assertFalse(result["real_sheets_write_performed"])
        self.assertFalse(result["publish_authorized"])
        self.assertFalse(result["sheets_write_allowed"])
        self.assertEqual(self.replica.write_calls,1)
        self.assertEqual(self.count("sns_mirror_rehearsal_events"),2)
        self.assertEqual(self.runner.inspect(
            event_sha256=event,destination_id=DEST,
        )["status"],"SIMULATED_READBACK_BLOCKED")

    def test_no_replay_or_duplicate_after_success(self):
        event=self.claimed()
        self.simulate(event)
        with self.assertRaises(MirrorRehearsalBlocked):
            self.simulate(event,operation_id="rehearsal_rerun_20261012_00001")
        self.assertEqual(self.replica.write_calls,1)

    def test_post_write_timeout_is_unknown_and_readback_only_reconciles(self):
        event=self.claimed()
        self.replica.fail_after_write=True
        uncertain=self.simulate(event)
        self.assertEqual(uncertain["status"],"OUTCOME_UNKNOWN_BLOCKED")
        self.assertEqual(self.replica.write_calls,1)
        self.replica.fail_after_write=False
        fixed=self.reconcile(event)
        self.assertEqual(fixed["status"],"SIMULATED_RECONCILED_BLOCKED")
        self.assertEqual(self.replica.write_calls,1)
        with self.assertRaises(MirrorRehearsalBlocked):
            self.simulate(event,operation_id="rehearsal_retry_after_20261012_01")

    def test_unknown_when_write_before_effect_fails_and_no_retry(self):
        event=self.claimed()
        self.replica.fail_before_write=True
        result=self.simulate(event)
        self.assertEqual(result["status"],"OUTCOME_UNKNOWN_BLOCKED")
        self.assertEqual(self.replica.write_calls,0)
        self.replica.fail_before_write=False
        with self.assertRaises(MirrorRehearsalBlocked):
            self.reconcile(event)
        self.assertEqual(self.replica.write_calls,0)

    def test_prepared_survives_unrecorded_result_and_reconciles_without_write(self):
        event=self.claimed()
        self.db.execute(
            """CREATE TRIGGER fail_rehearsal_result BEFORE INSERT
               ON sns_mirror_rehearsal_events
               WHEN NEW.action='SIMULATED_READBACK'
               BEGIN SELECT RAISE(ABORT,'injected_disk_error'); END""",
        )
        with self.assertRaises(MirrorRehearsalBlocked):
            self.simulate(event)
        self.assertEqual(self.runner.inspect(
            event_sha256=event,destination_id=DEST,
        )["status"],"PREPARED_BLOCKED")
        self.assertEqual(self.replica.write_calls,1)
        self.db.execute("DROP TRIGGER fail_rehearsal_result")
        result=self.reconcile(event)
        self.assertEqual(result["status"],"SIMULATED_RECONCILED_BLOCKED")
        self.assertEqual(self.replica.write_calls,1)

    def test_conflicting_existing_replica_record_prevents_write(self):
        event=self.claimed()
        preview=self.writer.mirror_previews()[0]
        forged=dict(preview)
        forged["writer_version"]=preview["writer_version"]+1
        self.replica.rows[self.replica.key(DEST,preview)]=forged
        result=self.simulate(event)
        self.assertEqual(result["status"],"CONFLICT_BLOCKED")
        self.assertEqual(self.replica.write_calls,0)

    def test_expired_review_claim_blocks_new_simulated_write(self):
        event=self.claimed()
        with self.assertRaises(MirrorRehearsalBlocked):
            self.simulate(event,as_of=NOW+timedelta(seconds=60))
        self.assertEqual(self.replica.write_calls,0)

    def test_tamper_audit_log_and_head_detected(self):
        event=self.claimed()
        self.simulate(event)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("DELETE FROM sns_mirror_rehearsal_events")
        self.db.execute(
            "UPDATE sns_mirror_rehearsal_heads SET projection_sha256=?",
            ("f"*64,),
        )
        with self.assertRaises(MirrorRehearsalBlocked):
            self.runner.inspect(event_sha256=event,destination_id=DEST)

    def test_read_only_recovery_allowed_after_claim_expired(self):
        event=self.claimed()
        self.replica.fail_after_write=True
        self.simulate(event)
        self.replica.fail_after_write=False
        recovered=self.reconcile(event,as_of=NOW+timedelta(seconds=65))
        self.assertEqual(recovered["status"],"SIMULATED_RECONCILED_BLOCKED")
        self.assertEqual(self.replica.write_calls,1)

    def test_rehearsal_write_must_reject_superseded_writer(self):
        event=self.claimed()
        self.change("HOLD")
        with self.assertRaises(MirrorRehearsalBlocked):
            self.simulate(event)
        self.assertEqual(self.replica.write_calls,0)

    def test_disabling_service_after_unknown_prevents_readback(self):
        event=self.claimed()
        self.replica.fail_after_write=True
        self.simulate(event)
        self.replica.fail_after_write=False
        self.db.execute("UPDATE sns_mirror_rehearsal_service_sessions SET enabled=0")
        with self.assertRaises(MirrorRehearsalBlocked):
            self.reconcile(event)
        self.assertEqual(self.replica.write_calls,1)

    def test_too_long_operation_does_not_leave_prepared_state(self):
        event=self.claimed()
        with self.assertRaises(MirrorRehearsalBlocked):
            self.simulate(event,operation_id="rehearsal_"+"a"*95)
        self.assertEqual(self.count("sns_mirror_rehearsal_heads"),0)

    def test_replica_can_cas_newer_version_but_not_stale(self):
        self.prepare()
        prior=self.writer.mirror_previews()[0]
        self.change("HOLD")
        current=self.writer.mirror_previews()[0]
        self.replica.rows[self.replica.key(DEST,current)]=prior
        self.claim()
        event=self.ident()
        result=self.simulate(event)
        self.assertEqual(result["status"],"SIMULATED_READBACK_BLOCKED")
        self.assertEqual(self.replica.write_calls,1)
        self.assertEqual(self.replica.read(DEST,current),current)

    def test_only_provisioned_reporting_tab(self):
        event=self.claimed()
        self.db.execute(
            "UPDATE sns_mirror_rehearsal_destinations SET reporting_tab=?",
            ("operational_queue",),
        )
        with self.assertRaises(MirrorRehearsalBlocked):
            self.simulate(event)
        self.assertEqual(self.replica.write_calls,0)

    def test_no_network_adapter_can_be_passed(self):
        with self.assertRaises(MirrorRehearsalBlocked):
            MirrorServiceRehearsal(
                db=self.db,verifier=self.verifier_service,
                replica=object(),
            )

    def test_no_network_path_in_service_module(self):
        text=(ROOT/"scripts"/"media_mirror_rehearsal.py").read_text()
        for forbidden in (
            "requests.post(", "gspread", "googleapiclient",
            "update_queue_item(", "_publish_container(",
            "sheets_write_allowed=True", "publish_authorized=True",
        ):
            self.assertNotIn(forbidden,text)


if __name__ == "__main__":
    unittest.main()
