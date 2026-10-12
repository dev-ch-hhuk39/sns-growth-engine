#!/usr/bin/env python3
"""Offline Phase 6N two-operator approval + single-use atomic canary tests."""
from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from media_mirror_canary_approval import (  # noqa: E402
    CanaryApprovalBlocked, PinnedTwoOperatorCanaryVerifier,
    initialize_canary_approval_schema,
)
from media_mirror_delivery_identity import MirrorDeliveryBlocked  # noqa: E402
from media_mirror_reporting_delivery import IsolatedSheetsMirrorDelivery  # noqa: E402
import test_media_mirror_write_acl_gate as prior  # noqa: E402
from test_media_mirror_reporting_delivery import (  # noqa: E402
    DEST, ISSUER, KEY, NOW, ROW, SUB, T,
)


class CanaryApprovalTests(prior.MirrorWriteAclGateTests):
    """Includes all 6M and previous review/rights/safety test regressions."""

    def test_schema_needs_prior_migrations(self):
        empty = sqlite3.connect(":memory:", isolation_level=None)
        try:
            with self.assertRaises(CanaryApprovalBlocked):
                initialize_canary_approval_schema(empty)
        finally:
            empty.close()

    def test_enabled_writer_rejects_missing_operator_verifier(self):
        with self.assertRaisesRegex(
            MirrorDeliveryBlocked, "mirror_canary_operator_gate_required",
        ):
            IsolatedSheetsMirrorDelivery(
                db=self.db, verifier=self.live_verifier,
                adapter=self.sheet_adapter,
                allow_reporting_write=True,
                acl_metadata=self.acl_metadata,
                expected_principal_email=self.acl_credentials.service_account_email,
            )

    def test_operator_verifier_requires_same_private_db(self):
        other = sqlite3.connect(":memory:", isolation_level=None)
        try:
            gate = PinnedTwoOperatorCanaryVerifier(
                db=other, issuer=ISSUER,
                operators_by_kid={
                    self.operator_kids[i]: (
                        self.operator_subjects[i],
                        self.operator_public_keys[i],
                    ) for i in range(2)
                },
            )
            with self.assertRaises(MirrorDeliveryBlocked):
                IsolatedSheetsMirrorDelivery(
                    db=self.db, verifier=self.live_verifier,
                    adapter=self.sheet_adapter,
                    allow_reporting_write=True, acl_metadata=self.acl_metadata,
                    expected_principal_email=self.acl_credentials.service_account_email,
                    canary_approver=gate,
                )
        finally:
            other.close()

    def test_distinct_kid_labels_cannot_share_same_rsa_private_key(self):
        with self.assertRaisesRegex(
            CanaryApprovalBlocked, "canary_operator_key_material_reused",
        ):
            PinnedTwoOperatorCanaryVerifier(
                db=self.db, issuer=ISSUER,
                operators_by_kid={
                    self.operator_kids[0]: (
                        self.operator_subjects[0], self.operator_public_keys[0],
                    ),
                    self.operator_kids[1]: (
                        self.operator_subjects[1], self.operator_public_keys[0],
                    ),
                },
            )

    def test_reporting_service_signing_key_must_not_be_an_operator_key(self):
        # This matches a real class of dangerous misconfiguration: the
        # service operator possesses one of the approval private keys.
        tainted = PinnedTwoOperatorCanaryVerifier(
            db=self.db, issuer=ISSUER,
            operators_by_kid={
                self.operator_kids[0]: (
                    self.operator_subjects[0], self.live_public,
                ),
                self.operator_kids[1]: (
                    self.operator_subjects[1], self.operator_public_keys[1],
                ),
            },
        )
        with self.assertRaisesRegex(
            MirrorDeliveryBlocked, "mirror_canary_service_key_reused",
        ):
            IsolatedSheetsMirrorDelivery(
                db=self.db, verifier=self.live_verifier,
                adapter=self.sheet_adapter, allow_reporting_write=True,
                acl_metadata=self.acl_metadata,
                expected_principal_email=self.acl_credentials.service_account_email,
                canary_approver=tainted,
            )
        self.assertEqual(self.ws.writes, 0)

    def test_no_approval_payload_denied_before_any_state_or_google_get(self):
        event = self.claimed()
        with self.assertRaisesRegex(
            MirrorDeliveryBlocked, "mirror_canary_two_operator_approval_required",
        ):
            self.engine.deliver_once(
                event_sha256=event, destination_id=DEST,
                service_token=self.token_live,
                operation_id="delivery_without_operators_20261012",
                as_of=NOW,
            )
        self.assertEqual(self.count("sns_mirror_canary_signoff_uses"), 0)
        self.assertEqual(self.count("sns_mirror_delivery_heads"), 0)
        self.assertEqual(self.acl_session.calls, [])
        self.assertEqual(self.ws.writes, 0)

    def test_one_operator_only_cannot_approve(self):
        event = self.claimed()
        (one,) = self.operator_signoffs(which=(0,))
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(event, canary_approval_tokens=(one,))
        self.assertEqual(self.count("sns_mirror_canary_signoff_uses"), 0)
        self.assertEqual(self.ws.writes, 0)

    def test_same_token_twice_rejected(self):
        event = self.claimed()
        (one,) = self.operator_signoffs(which=(0,))
        with self.assertRaisesRegex(
            MirrorDeliveryBlocked, "mirror_canary_operator_approval_denied",
        ):
            self.deliver(event, canary_approval_tokens=(one, one))
        self.assertEqual(self.count("sns_mirror_canary_signoff_uses"), 0)
        self.assertEqual(self.count("sns_mirror_delivery_heads"), 0)

    def test_one_key_cannot_approve_twice_even_with_two_jti(self):
        event = self.claimed()
        pair = self.operator_signoffs(which=(0, 0))
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(event, canary_approval_tokens=pair)
        self.assertEqual(self.ws.writes, 0)

    def test_two_operators_approve_one_and_only_one_reporting_put(self):
        event = self.claimed()
        result = self.deliver(event)
        self.assertEqual(result["status"], "READBACK_VERIFIED_BLOCKED")
        self.assertEqual(self.ws.writes, 1)
        self.assertEqual(self.count("sns_mirror_canary_signoff_uses"), 2)
        rows = self.db.execute(
            """SELECT signer_subject,operator_slot,account_id,row_number
               FROM sns_mirror_canary_signoff_uses ORDER BY operator_slot"""
        ).fetchall()
        self.assertEqual(
            rows, [
                (self.operator_subjects[0], 1, KEY[0], ROW),
                (self.operator_subjects[1], 2, KEY[0], ROW),
            ],
        )
        self.assertFalse(result["publish_authorized"])
        self.assertFalse(result["operational_queue_modified"])

    def test_replay_same_approval_cannot_run_again(self):
        event = self.claimed()
        tokens = self.operator_signoffs()
        self.deliver(event, canary_approval_tokens=tokens)
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(
                event, operation_id="delivery_run_20261012_000001",
                canary_approval_tokens=tokens,
            )
        self.assertEqual(self.ws.writes, 1)

    def test_tokens_do_not_approve_different_operation_id(self):
        event = self.claimed()
        tokens = self.operator_signoffs(
            operation_id="delivery_old_approval_20261012_001",
        )
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(event, canary_approval_tokens=tokens)
        self.assertEqual(self.count("sns_mirror_canary_signoff_uses"), 0)

    def test_tokens_do_not_approve_different_event(self):
        event = self.claimed()
        pair = self.operator_signoffs(overrides={"event_sha256": "f"*64})
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(event, canary_approval_tokens=pair)
        self.assertEqual(self.count("sns_mirror_delivery_heads"), 0)

    def test_tokens_do_not_approve_other_reporting_destination(self):
        event = self.claimed()
        pair = self.operator_signoffs(
            overrides={"destination_id": "unapproved_destination"},
        )
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(event, canary_approval_tokens=pair)
        self.assertEqual(self.ws.writes, 0)

    def test_tokens_do_not_approve_other_account(self):
        event = self.claimed()
        pair = self.operator_signoffs(overrides={"account_id": "night_scout"})
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(event, canary_approval_tokens=pair)
        self.assertEqual(self.ws.writes, 0)

    def test_tokens_do_not_approve_different_fixed_row(self):
        event = self.claimed()
        pair = self.operator_signoffs(overrides={"row_number": ROW+1})
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(event, canary_approval_tokens=pair)
        self.assertEqual(self.ws.writes, 0)

    def test_tokens_do_not_approve_modified_queue_version(self):
        event = self.claimed()
        pair = self.operator_signoffs(
            overrides={"projection_sha256": "f"*64},
        )
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(event, canary_approval_tokens=pair)
        self.assertEqual(self.ws.writes, 0)

    def test_wrong_audience_scope_token_use_or_issuer_denied(self):
        event = self.claimed()
        cases = (
            {"aud": "sns-growth-mirror-reporting-write"},
            {"scope": "mirror:reporting:write"},
            {"token_use": "mirror_reporting_live"},
            {"iss": "https://untrusted-approver.example.test"},
        )
        for idx, override in enumerate(cases):
            with self.subTest(idx=idx):
                tokens = self.operator_signoffs(overrides=override)
                with self.assertRaises(MirrorDeliveryBlocked):
                    self.deliver(event, canary_approval_tokens=tokens)
                self.assertEqual(self.count("sns_mirror_delivery_heads"), 0)
        self.assertEqual(self.acl_session.calls, [])

    def test_expired_and_overly_long_lived_approvals_denied(self):
        event = self.claimed()
        for props in (
            {"exp": T-1},
            {"exp": T+3600},
            {"iat": T+500},
            {"nbf": T+500},
        ):
            with self.subTest(props=props):
                tokens = self.operator_signoffs(overrides=props)
                with self.assertRaises(MirrorDeliveryBlocked):
                    self.deliver(event, canary_approval_tokens=tokens)
        self.assertEqual(self.count("sns_mirror_canary_signoff_uses"), 0)

    def test_reporting_service_cannot_be_one_of_two_approvers(self):
        event = self.claimed()
        tokens = self.operator_signoffs(overrides={"sub": SUB})
        # Synthetic helper overwrites sub with pinned operator identity.
        self.assertNotEqual(tokens[0], self.token_live)
        original_operator = self.operator_gate.operators
        try:
            self.operator_gate.operators = {
                **original_operator,
                self.operator_kids[0]: (
                    SUB, original_operator[self.operator_kids[0]][1],
                ),
            }
            with self.assertRaises(MirrorDeliveryBlocked):
                self.deliver(event, canary_approval_tokens=tokens)
        finally:
            self.operator_gate.operators = original_operator
        self.assertEqual(self.ws.writes, 0)

    def test_a_signature_with_wrong_public_key_is_rejected(self):
        event = self.claimed()
        pair = self.operator_signoffs()
        a, b = pair
        # Still well-formed JWT but an invalid signature.
        mangled = b[:-10] + ("b" if b[-10] != "b" else "c") + b[-9:]
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(event, canary_approval_tokens=(a, mangled))
        self.assertEqual(self.ws.writes, 0)

    def test_unknown_signing_key_is_denied(self):
        event = self.claimed()
        old = self.operator_gate.operators
        try:
            self.operator_gate.operators = {
                k: v for k, v in old.items() if k != self.operator_kids[1]
            }
            with self.assertRaises(MirrorDeliveryBlocked):
                self.deliver(event)
        finally:
            self.operator_gate.operators = old
        self.assertEqual(self.ws.writes, 0)

    def test_approval_ledger_is_append_only_and_tamper_detectable(self):
        self.claimed()
        self.deliver()
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("DELETE FROM sns_mirror_canary_signoff_uses")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "UPDATE sns_mirror_canary_signoff_uses SET signer_subject='fake'"
            )

    def test_approval_write_fault_rolls_back_all_and_stops_provider(self):
        event = self.claimed()
        self.db.execute(
            """CREATE TRIGGER fail_second_canary_signoff
               BEFORE INSERT ON sns_mirror_canary_signoff_uses
               WHEN NEW.operator_slot=2
               BEGIN SELECT RAISE(ABORT,'injected_fault'); END"""
        )
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(event)
        self.assertEqual(self.count("sns_mirror_canary_signoff_uses"), 0)
        self.assertEqual(self.count("sns_mirror_delivery_heads"), 0)
        self.assertEqual(self.ws.writes, 0)
        self.assertFalse(self.db.in_transaction)
        self.db.execute("DROP TRIGGER fail_second_canary_signoff")
        self.deliver(event)
        self.assertEqual(self.count("sns_mirror_canary_signoff_uses"), 2)

    def test_prepared_write_fault_rolls_back_both_approvals(self):
        event = self.claimed()
        self.db.execute(
            """CREATE TRIGGER fail_delivery_prepare
               BEFORE INSERT ON sns_mirror_delivery_heads
               BEGIN SELECT RAISE(ABORT,'injected_prepare_fault'); END"""
        )
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(event)
        self.assertEqual(self.count("sns_mirror_canary_signoff_uses"), 0)
        self.assertEqual(self.count("sns_mirror_delivery_events"), 0)
        self.assertEqual(self.ws.writes, 0)

    def test_unknown_reporting_result_still_consumes_operator_approvals(self):
        event = self.claimed()
        self.ws.fail_after_write = True
        result = self.deliver(event)
        self.assertEqual(result["status"], "OUTCOME_UNKNOWN_BLOCKED")
        self.assertEqual(self.count("sns_mirror_canary_signoff_uses"), 2)
        self.assertEqual(self.ws.writes, 1)
        self.ws.fail_after_write = False
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(
                event,
                operation_id="delivery_another_try_20261012_001",
            )
        self.assertEqual(self.ws.writes, 1)

    def test_readonly_recovery_does_not_require_new_operator_tokens(self):
        event = self.claimed()
        self.ws.fail_after_write = True
        self.deliver(event)
        self.ws.fail_after_write = False
        result = self.recover(event)
        self.assertEqual(result["status"], "RECONCILED_BLOCKED")
        self.assertEqual(self.count("sns_mirror_canary_signoff_uses"), 2)
        self.assertEqual(self.ws.writes, 1)

    def test_stale_approved_source_never_consumes_signoff(self):
        event = self.claimed()
        tokens = self.operator_signoffs(event=event)
        self.change("HOLD")
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(event, canary_approval_tokens=tokens)
        self.assertEqual(self.count("sns_mirror_canary_signoff_uses"), 0)
        self.assertEqual(self.ws.writes, 0)

    def test_missing_private_approval_journal_blocks_any_put(self):
        event = self.claimed()
        self.db.execute("DROP TABLE sns_mirror_canary_signoff_uses")
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(event)
        self.assertEqual(self.count("sns_mirror_delivery_heads"), 0)
        self.assertEqual(self.ws.writes, 0)

    def test_deployment_is_still_disabled_without_operator_action(self):
        self.claimed()
        disabled = IsolatedSheetsMirrorDelivery(
            db=self.db, verifier=self.live_verifier,
            adapter=self.sheet_adapter,
        )
        with self.assertRaisesRegex(
            MirrorDeliveryBlocked, "mirror_reporting_write_disabled",
        ):
            disabled.deliver_once(
                event_sha256=self.ident(), destination_id=DEST,
                service_token=self.token_live,
                operation_id="delivery_disabled_6n_20261012_0001",
                as_of=NOW,
            )
        self.assertEqual(self.count("sns_mirror_canary_signoff_uses"), 0)
        self.assertEqual(self.ws.writes, 0)


if __name__ == "__main__":
    unittest.main()
