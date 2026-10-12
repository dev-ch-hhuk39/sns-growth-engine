#!/usr/bin/env python3
"""6O local-only operator grant ACL, revocation, rotation and pre-PUT checks.

Never uses live Google credentials, provider sessions or a production DB.
All inherited review/rights/canary tests run against temporary SQLite.
"""
from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from media_mirror_delivery_identity import MirrorDeliveryBlocked  # noqa: E402
from media_mirror_operator_grants import (  # noqa: E402
    OperatorGrantBlocked, initialize_operator_grant_schema,
    require_current_operator_grant,
)
import test_media_mirror_canary_approval as prior  # noqa: E402

T, NOW, DEST, KEY = prior.T, prior.NOW, prior.DEST, prior.KEY


class ScopedOperatorGrantTests(prior.CanaryApprovalTests):
    """All 6N focused tests plus operator grant revocation cases."""

    def update_grant(self, slot, **changes):
        assert changes
        columns = ", ".join(f"{k}=?" for k in changes)
        self.db.execute(
            "UPDATE sns_mirror_canary_operator_grants SET " + columns
            + " WHERE signer_kid=?",
            (*changes.values(), self.operator_kids[slot]),
        )

    def test_grant_schema_fails_without_prior_private_tables(self):
        empty = sqlite3.connect(":memory:", isolation_level=None)
        try:
            with self.assertRaises(OperatorGrantBlocked):
                initialize_operator_grant_schema(empty)
        finally:
            empty.close()

    def test_new_grant_is_disabled_by_default(self):
        self.db.execute(
            """INSERT INTO sns_mirror_canary_operator_grants(
                 signer_kid,signer_subject,account_id,destination_id,
                 approval_slot,grant_generation,valid_from,valid_until,
                 provisioned_by
               ) VALUES(?,?,?,?,?,?,?,?,?)""",
            (
                "unused_pin_0001", "unused_human_0001", KEY[0], DEST,
                1, 1, T-120, T+240, "offline_test_operator",
            ),
        )
        row = self.db.execute(
            """SELECT enabled FROM sns_mirror_canary_operator_grants
               WHERE signer_kid='unused_pin_0001'""",
        ).fetchone()
        self.assertEqual(row, (0,))

    def test_no_current_grant_blocks_before_any_external_get(self):
        event = self.claimed()
        self.update_grant(0, enabled=0)
        with self.assertRaisesRegex(
            MirrorDeliveryBlocked, "mirror_canary_operator_approval_denied",
        ):
            self.deliver(event)
        self.assertEqual(self.count("sns_mirror_delivery_heads"), 0)
        self.assertEqual(self.count("sns_mirror_canary_signoff_uses"), 0)
        self.assertEqual(self.acl_session.calls, [])
        self.assertEqual(self.ws.writes, 0)

    def test_revoked_grant_rejects_current_signed_operator(self):
        event = self.claimed()
        signed = self.operator_signoffs()
        self.update_grant(1, revoked_at=T)
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(event, canary_approval_tokens=signed)
        self.assertEqual(self.count("sns_mirror_canary_signoff_uses"), 0)
        self.assertEqual(self.ws.writes, 0)

    def test_grant_expired_even_if_jwt_valid_now(self):
        event = self.claimed()
        self.update_grant(1, valid_until=T)
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(event)
        self.assertEqual(self.ws.writes, 0)

    def test_grant_not_yet_effective_is_denied(self):
        event = self.claimed()
        self.update_grant(0, valid_from=T+60)
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(event)
        self.assertEqual(self.ws.writes, 0)

    def test_signature_issued_before_grant_is_denied(self):
        event = self.claimed()
        self.update_grant(0, valid_from=T-40)
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(event)
        self.assertEqual(self.ws.writes, 0)

    def test_signed_approval_cannot_extend_past_grant_end(self):
        event = self.claimed()
        self.update_grant(0, valid_until=T+90)
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(event)
        self.assertEqual(self.ws.writes, 0)

    def test_wrong_signed_generation_rejected_before_prepare(self):
        event = self.claimed()
        signed = self.operator_signoffs(overrides={"grant_generation":2})
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(event, canary_approval_tokens=signed)
        self.assertEqual(self.count("sns_mirror_delivery_heads"), 0)
        self.assertEqual(self.acl_session.calls, [])

    def test_boolean_generation_not_accepted_as_integer(self):
        event = self.claimed()
        signed = self.operator_signoffs(overrides={"grant_generation":True})
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(event, canary_approval_tokens=signed)
        self.assertEqual(self.ws.writes, 0)

    def test_signer_roles_cannot_be_swapped(self):
        event = self.claimed()
        first, second = self.operator_signoffs()
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(event, canary_approval_tokens=(second,first))
        self.assertEqual(self.ws.writes, 0)

    def test_missing_grant_registry_denies_every_write(self):
        event = self.claimed()
        self.db.execute("DROP TABLE sns_mirror_canary_operator_grants")
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(event)
        self.assertEqual(self.ws.writes, 0)
        self.assertEqual(self.count("sns_mirror_canary_signoff_uses"),0)

    def test_grant_scope_cannot_be_retarged(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.update_grant(0, destination_id="untrusted_destination")
        with self.assertRaises(sqlite3.IntegrityError):
            self.update_grant(0, approval_slot=2)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "DELETE FROM sns_mirror_canary_operator_grants",
            )

    def test_grant_epoch_cannot_decrease(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.update_grant(0, grant_generation=0)
        self.update_grant(0, grant_generation=2)
        with self.assertRaises(sqlite3.IntegrityError):
            self.update_grant(0, grant_generation=1)

    def test_reenable_must_advance_generation(self):
        self.update_grant(0, enabled=0)
        with self.assertRaises(sqlite3.IntegrityError):
            self.update_grant(0, enabled=1)
        self.update_grant(0, enabled=1, grant_generation=2)
        self.assertEqual(
            self.db.execute(
                """SELECT enabled,grant_generation
                   FROM sns_mirror_canary_operator_grants
                   WHERE signer_kid=?""",
                (self.operator_kids[0],),
            ).fetchone(),
            (1,2),
        )

    def test_revocation_reactivation_requires_generation_increment(self):
        self.update_grant(1, enabled=0, revoked_at=T)
        with self.assertRaises(sqlite3.IntegrityError):
            self.update_grant(1, enabled=1, revoked_at=None)
        self.update_grant(1, enabled=1, revoked_at=None, grant_generation=2)
        self.assertEqual(
            self.db.execute(
                "SELECT grant_generation FROM sns_mirror_canary_operator_grants "
                "WHERE signer_kid=?", (self.operator_kids[1],),
            ).fetchone(),
            (2,),
        )

    def test_old_signed_tokens_remain_invalid_after_reactivation(self):
        event = self.claimed()
        signed_old = self.operator_signoffs()
        self.update_grant(0, enabled=0, revoked_at=T)
        self.update_grant(0, enabled=1, revoked_at=None, grant_generation=2)
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(event, canary_approval_tokens=signed_old)
        self.assertEqual(self.ws.writes, 0)
        # A new JWT for *that* operator must state the raised generation.
        first = self.operator_signoffs(
            which=(0,), overrides={"grant_generation":2},
        )[0]
        second = self.operator_signoffs(which=(1,))[0]
        result = self.deliver(event, canary_approval_tokens=(first,second))
        self.assertEqual(result["status"], "READBACK_VERIFIED_BLOCKED")
        self.assertEqual(self.ws.writes,1)

    def test_scope_lookup_refuses_other_destination(self):
        self.db.execute("BEGIN")
        try:
            with self.assertRaises(OperatorGrantBlocked):
                require_current_operator_grant(
                    self.db,kid=self.operator_kids[0],
                    subject=self.operator_subjects[0],
                    account_id=KEY[0],destination_id="another_destination",
                    approval_slot=1,grant_generation=1,
                    issued_at=T-60,expires_at=T+180,now_seconds=T,
                )
        finally:
            self.db.rollback()

    def test_rejected_grant_does_not_consume_any_signoff(self):
        event = self.claimed()
        self.update_grant(0, revoked_at=T)
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(event)
        self.assertFalse(self.db.in_transaction)
        self.assertEqual(self.count("sns_mirror_canary_signoff_uses"),0)
        self.assertEqual(self.count("sns_mirror_delivery_events"),0)

    def test_revocation_after_prepare_before_put_blocks_write(self):
        event = self.claimed()
        def revoke_during_second_acl(_url):
            if len(self.acl_session.calls) == 4:
                self.update_grant(0, revoked_at=T)
        self.acl_session.before_return = revoke_during_second_acl
        result = self.deliver(event)
        self.assertEqual(result["status"],"OUTCOME_UNKNOWN_BLOCKED")
        self.assertEqual(len(self.acl_session.calls),6)
        self.assertFalse(result["reporting_write_attempted"])
        self.assertEqual(self.ws.writes,0)
        self.assertEqual(self.count("sns_mirror_canary_signoff_uses"),2)
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(
                event,operation_id="delivery_revoked_retry_20261012_001",
            )
        self.assertEqual(self.ws.writes,0)

    def test_grant_generation_change_after_prepare_blocks_put(self):
        self.claimed()
        def change_generation(_url):
            if len(self.acl_session.calls) == 4:
                self.update_grant(1, grant_generation=2)
        self.acl_session.before_return = change_generation
        result = self.deliver()
        self.assertEqual(result["status"],"OUTCOME_UNKNOWN_BLOCKED")
        self.assertEqual(self.ws.writes,0)
        self.assertEqual(self.count("sns_mirror_canary_signoff_uses"),2)

    def test_no_prepared_signoffs_unblocks_even_with_valid_grants(self):
        event = self.claimed()
        def tamper_journal(_url):
            if len(self.acl_session.calls) == 4:
                self.db.execute(
                    "DROP TABLE sns_mirror_canary_signoff_uses",
                )
        self.acl_session.before_return = tamper_journal
        result = self.deliver(event)
        self.assertEqual(result["status"],"OUTCOME_UNKNOWN_BLOCKED")
        self.assertFalse(result["reporting_write_attempted"])
        self.assertEqual(self.ws.writes,0)

    def test_readonly_reconcile_after_later_operator_revocation(self):
        event = self.claimed()
        self.ws.fail_after_write=True
        result = self.deliver(event)
        self.assertEqual(result["status"],"OUTCOME_UNKNOWN_BLOCKED")
        self.assertEqual(self.ws.writes,1)
        self.ws.fail_after_write=False
        self.update_grant(0, revoked_at=T)
        recovered = self.recover(event)
        self.assertEqual(recovered["status"],"RECONCILED_BLOCKED")
        self.assertEqual(self.ws.writes,1)

    def test_default_delivery_without_signed_operators_remains_denied(self):
        event = self.claimed()
        with self.assertRaises(MirrorDeliveryBlocked):
            self.engine.deliver_once(
                event_sha256=event,destination_id=DEST,
                service_token=self.token_live,
                operation_id="delivery_no_operators_6o_20261012",
                as_of=NOW,
            )
        self.assertEqual(self.ws.writes,0)


if __name__ == "__main__":
    unittest.main()
