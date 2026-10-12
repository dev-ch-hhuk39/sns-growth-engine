#!/usr/bin/env python3
"""6P synthetic independent IdP proof and MFA session binding tests.

Temporary SQLite + ephemeral RS256 keys + fake gspread/Drive only. No
actual identity provider, OAuth login, Google API or SNS posting is invoked.
"""
from __future__ import annotations

import hashlib
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from media_mirror_delivery_identity import MirrorDeliveryBlocked  # noqa: E402
from media_mirror_operator_idp import (  # noqa: E402
    OperatorIdentityBlocked, PinnedOperatorIdpSessionVerifier,
    initialize_operator_idp_schema, ACR, AUDIENCE,
)
from media_mirror_reporting_delivery import (  # noqa: E402
    IsolatedSheetsMirrorDelivery,
)
import test_media_mirror_operator_grants as prior  # noqa: E402
from test_media_mirror_reporting_delivery import (  # noqa: E402
    DEST, IDP_ISSUER, IDP_KID, ISSUER, NOW, T,
)


class OperatorIdpProofTests(prior.ScopedOperatorGrantTests):
    """All earlier canary tests plus independent session/IdP regressions."""

    def idp_check(self, slot=0, token=None, **changes):
        token = self.idp_tokens[slot] if token is None else token
        kwargs = {
            "token": token, "subject": self.operator_subjects[slot],
            "expected_session_id": f"canary_idp_session_{slot}_20261012",
            "expected_sha256": hashlib.sha256(
                token.encode("ascii"),
            ).hexdigest(),
            "now": NOW,
        }
        kwargs.update(changes)
        self.db.execute("BEGIN")
        try:
            self.identity_verifier.verify_active(**kwargs)
        finally:
            self.db.rollback()

    def sign_with_identity(self, slot, token):
        all_tokens = list(self.idp_tokens)
        all_tokens[slot] = token
        approvals = self.operator_signoffs(identity_tokens=tuple(all_tokens))
        return tuple(all_tokens),approvals

    def test_independent_idp_session_requires_prior_migrations(self):
        empty = sqlite3.connect(":memory:", isolation_level=None)
        try:
            with self.assertRaises(OperatorIdentityBlocked):
                initialize_operator_idp_schema(empty)
        finally:
            empty.close()

    def test_two_independently_bound_idp_sessions_allow_one_blocked_report(self):
        event = self.claimed()
        result = self.deliver(event)
        self.assertEqual(result["status"], "READBACK_VERIFIED_BLOCKED")
        self.assertEqual(self.ws.writes, 1)
        self.assertEqual(self.count("sns_mirror_canary_idp_sessions"), 2)
        self.assertFalse(result["publish_authorized"])
        self.assertFalse(result["operational_queue_modified"])

    def test_idp_verifier_refuses_missing_protected_transaction(self):
        with self.assertRaisesRegex(
            OperatorIdentityBlocked, "canary_idp_atomic_check_required",
        ):
            self.identity_verifier.verify_active(
                token=self.idp_tokens[0],
                subject=self.operator_subjects[0],
                expected_session_id="canary_idp_session_0_20261012",
                expected_sha256=hashlib.sha256(
                    self.idp_tokens[0].encode("ascii"),
                ).hexdigest(),
                now=NOW,
            )

    def test_missing_identity_proof_pair_blocks_before_google(self):
        event = self.claimed()
        with self.assertRaisesRegex(
            MirrorDeliveryBlocked, "mirror_canary_independent_identity_required",
        ):
            self.engine.deliver_once(
                event_sha256=event,destination_id=DEST,
                service_token=self.token_live,
                operation_id="delivery_idp_proof_missing_20261012",
                as_of=NOW,
                canary_approval_tokens=self.operator_signoffs(
                    operation_id="delivery_idp_proof_missing_20261012",
                ),
            )
        self.assertEqual(self.count("sns_mirror_delivery_heads"),0)
        self.assertEqual(self.acl_session.calls,[])
        self.assertEqual(self.ws.writes,0)

    def test_only_one_identity_proof_is_denied(self):
        event = self.claimed()
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(
                event,identity_assertion_tokens=(self.idp_tokens[0],),
            )
        self.assertEqual(self.ws.writes,0)

    def test_same_proof_for_two_distinct_people_is_denied(self):
        event = self.claimed()
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(
                event,identity_assertion_tokens=(
                    self.idp_tokens[0],self.idp_tokens[0],
                ),
            )
        self.assertEqual(self.ws.writes,0)

    def test_cross_operator_swap_cannot_prove_mfa(self):
        event = self.claimed()
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(
                event,identity_assertion_tokens=(
                    self.idp_tokens[1],self.idp_tokens[0],
                ),
            )
        self.assertEqual(self.acl_session.calls,[])

    def test_approval_hash_binds_externally_authenticated_identity_proof(self):
        event = self.claimed()
        alternate = self.idp_token(0,overrides={"jti":"new_unprovisioned_jti"})
        token_pair,approvals = self.sign_with_identity(0,alternate)
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(
                event,identity_assertion_tokens=token_pair,
                canary_approval_tokens=approvals,
            )
        self.assertEqual(self.ws.writes,0)
        self.assertEqual(self.count("sns_mirror_canary_signoff_uses"),0)

    def test_forged_idp_signed_proof_is_denied(self):
        event = self.claimed()
        forged = self.idp_tokens[0][:-10] + (
            "A" if self.idp_tokens[0][-10] != "A" else "B"
        ) + self.idp_tokens[0][-9:]
        pair,approvals = self.sign_with_identity(0,forged)
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(
                event,identity_assertion_tokens=pair,
                canary_approval_tokens=approvals,
            )
        self.assertEqual(self.ws.writes,0)

    def test_idp_issuer_mismatch_is_denied(self):
        bad = self.idp_token(
            0,overrides={"iss":"https://untrusted-identity.example.test"},
        )
        with self.assertRaisesRegex(
            OperatorIdentityBlocked, "canary_idp_claims_invalid",
        ):
            self.idp_check(token=bad)

    def test_idp_audience_mismatch_is_denied(self):
        bad = self.idp_token(0,overrides={"aud":"sns-growth-mirror-reporting-write"})
        with self.assertRaises(OperatorIdentityBlocked):
            self.idp_check(token=bad)

    def test_idp_operator_role_scope_is_not_reviewer_role(self):
        bad = self.idp_token(0,overrides={"scope":"mirror:reporting:canary:approve"})
        with self.assertRaises(OperatorIdentityBlocked):
            self.idp_check(token=bad)

    def test_idp_must_use_distinct_key_id(self):
        bad = self.idp_token(0,header_overrides={"kid":"untrusted_key_00001"})
        with self.assertRaisesRegex(
            OperatorIdentityBlocked, "canary_idp_signature_invalid",
        ):
            self.idp_check(token=bad)

    def test_none_algorithm_is_never_allowed(self):
        bad = self.idp_token(0,header_overrides={"alg":"none"})
        with self.assertRaises(OperatorIdentityBlocked):
            self.idp_check(token=bad)

    def test_mfa_claim_requires_phishing_resistant_method(self):
        for amr in (
            ["mfa"],["otp","mfa"],["pwd"],[],None,["webauthn"],["mfa","webauthn",3],
        ):
            with self.subTest(amr=amr):
                bad = self.idp_token(0,overrides={"amr":amr})
                with self.assertRaisesRegex(
                    OperatorIdentityBlocked,
                    "canary_idp_phishing_resistant_mfa_required",
                ):
                    self.idp_check(token=bad)

    def test_idp_acr_requires_custom_signed_mfa_profile(self):
        bad = self.idp_token(0,overrides={"acr":"urn:example:password-only"})
        with self.assertRaisesRegex(
            OperatorIdentityBlocked,"canary_idp_claims_invalid",
        ):
            self.idp_check(token=bad)

    def test_idp_mfa_timestamp_must_be_fresh(self):
        bad = self.idp_token(0,overrides={"mfa_at":T-500})
        with self.assertRaisesRegex(
            OperatorIdentityBlocked,"canary_idp_time_invalid",
        ):
            self.idp_check(token=bad)

    def test_future_mfa_time_is_denied(self):
        bad = self.idp_token(0,overrides={"mfa_at":T+200})
        with self.assertRaisesRegex(
            OperatorIdentityBlocked,"canary_idp_time_invalid",
        ):
            self.idp_check(token=bad)

    def test_idp_token_cannot_be_long_lived(self):
        bad = self.idp_token(0,overrides={"exp":T+1800})
        with self.assertRaises(OperatorIdentityBlocked):
            self.idp_check(token=bad)

    def test_session_inactive_denies_valid_signed_proof(self):
        event = self.claimed()
        self.db.execute(
            "UPDATE sns_mirror_canary_idp_sessions SET enabled=0 WHERE subject=?",
            (self.operator_subjects[0],),
        )
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(event)
        self.assertEqual(self.ws.writes,0)
        self.assertEqual(self.acl_session.calls,[])

    def test_session_revoked_denies_valid_signed_proof(self):
        event = self.claimed()
        self.db.execute(
            "UPDATE sns_mirror_canary_idp_sessions SET revoked_at=? WHERE subject=?",
            (T,self.operator_subjects[1]),
        )
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(event)
        self.assertEqual(self.count("sns_mirror_canary_signoff_uses"),0)
        self.assertEqual(self.ws.writes,0)

    def test_session_removed_denies_valid_signed_proof(self):
        event = self.claimed()
        self.db.execute("DROP TABLE sns_mirror_canary_idp_sessions")
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(event)
        self.assertEqual(self.ws.writes,0)
        self.assertEqual(self.acl_session.calls,[])

    def test_idp_session_signatures_are_exactly_fingerprint_bound(self):
        with self.assertRaisesRegex(
            OperatorIdentityBlocked,"canary_idp_assertion_unbound",
        ):
            self.idp_check(expected_sha256="f"*64)

    def test_session_profile_and_hash_cannot_be_rewritten(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "UPDATE sns_mirror_canary_idp_sessions SET assertion_sha256=?",
                ("f"*64,),
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "UPDATE sns_mirror_canary_idp_sessions SET authentication_profile=?",
                ("SIMPLE_PASSWORD",),
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("DELETE FROM sns_mirror_canary_idp_sessions")

    def test_revocation_is_terminal_not_an_editable_reset(self):
        self.db.execute(
            "UPDATE sns_mirror_canary_idp_sessions SET enabled=0,revoked_at=? "
            "WHERE subject=?", (T,self.operator_subjects[0]),
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "UPDATE sns_mirror_canary_idp_sessions "
                "SET enabled=1,revoked_at=NULL WHERE subject=?",
                (self.operator_subjects[0],),
            )

    def test_idp_key_must_not_overlap_reporting_service_key(self):
        bad=PinnedOperatorIdpSessionVerifier(
            db=self.db,issuer=IDP_ISSUER,
            public_keys_by_kid={IDP_KID:self.live_public},
        )
        original=self.operator_gate.identity_verifier
        self.operator_gate.identity_verifier=bad
        try:
            with self.assertRaisesRegex(
                MirrorDeliveryBlocked,"mirror_canary_idp_signing_key_reused",
            ):
                IsolatedSheetsMirrorDelivery(
                    db=self.db,verifier=self.live_verifier,
                    adapter=self.sheet_adapter,allow_reporting_write=True,
                    acl_metadata=self.acl_metadata,
                    expected_principal_email=self.acl_credentials.service_account_email,
                    canary_approver=self.operator_gate,
                )
        finally:
            self.operator_gate.identity_verifier=original

    def test_idp_issuer_must_not_be_approval_issuer(self):
        bad=PinnedOperatorIdpSessionVerifier(
            db=self.db,issuer=ISSUER,
            public_keys_by_kid={IDP_KID:self.idp_public},
        )
        original=self.operator_gate.identity_verifier
        self.operator_gate.identity_verifier=bad
        try:
            with self.assertRaisesRegex(
                MirrorDeliveryBlocked,"mirror_canary_independent_idp_required",
            ):
                IsolatedSheetsMirrorDelivery(
                    db=self.db,verifier=self.live_verifier,
                    adapter=self.sheet_adapter,allow_reporting_write=True,
                    acl_metadata=self.acl_metadata,
                    expected_principal_email=self.acl_credentials.service_account_email,
                    canary_approver=self.operator_gate,
                )
        finally:
            self.operator_gate.identity_verifier=original

    def test_idp_session_revoked_after_prepare_blocks_final_put(self):
        event=self.claimed()
        def revoke_before_second_acl(url):
            if len(self.acl_session.calls)==4:
                self.db.execute(
                    "UPDATE sns_mirror_canary_idp_sessions SET revoked_at=? "
                    "WHERE subject=?", (T,self.operator_subjects[0]),
                )
        self.acl_session.before_return=revoke_before_second_acl
        result=self.deliver(event)
        self.assertEqual(result["status"],"OUTCOME_UNKNOWN_BLOCKED")
        self.assertFalse(result["reporting_write_attempted"])
        self.assertEqual(self.ws.writes,0)
        self.assertEqual(self.count("sns_mirror_canary_signoff_uses"),2)
        self.assertEqual(len(self.acl_session.calls),6)

    def test_idp_session_disabled_after_prepare_blocks_put(self):
        self.claimed()
        def disable_before_second_acl(url):
            if len(self.acl_session.calls)==4:
                self.db.execute(
                    "UPDATE sns_mirror_canary_idp_sessions SET enabled=0 "
                    "WHERE subject=?", (self.operator_subjects[1],),
                )
        self.acl_session.before_return=disable_before_second_acl
        result=self.deliver()
        self.assertEqual(result["status"],"OUTCOME_UNKNOWN_BLOCKED")
        self.assertEqual(self.ws.writes,0)

    def test_unknown_provider_write_can_be_reconciled_without_reenabling_idp(self):
        event=self.claimed()
        self.ws.fail_after_write=True
        outcome=self.deliver(event)
        self.assertEqual(outcome["status"],"OUTCOME_UNKNOWN_BLOCKED")
        self.assertEqual(self.ws.writes,1)
        self.ws.fail_after_write=False
        self.db.execute(
            "UPDATE sns_mirror_canary_idp_sessions SET revoked_at=? WHERE subject=?",
            (T,self.operator_subjects[0]),
        )
        recovered=self.recover(event)
        self.assertEqual(recovered["status"],"RECONCILED_BLOCKED")
        self.assertEqual(self.ws.writes,1)

    def test_replay_after_idp_revocation_must_never_retry_put(self):
        event=self.claimed()
        self.ws.fail_after_write=True
        self.deliver(event)
        self.ws.fail_after_write=False
        self.db.execute(
            "UPDATE sns_mirror_canary_idp_sessions SET enabled=0 WHERE subject=?",
            (self.operator_subjects[0],),
        )
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(event,operation_id="delivery_idp_retry_blocked_20261012")
        self.assertEqual(self.ws.writes,1)

    def test_no_real_idp_or_google_session_is_auto_provisioned(self):
        self.assertEqual(self.acl_session.calls,[])
        self.assertEqual(self.ws.get_calls,[])
        self.assertEqual(self.ws.writes,0)
        self.assertTrue(IDP_ISSUER.startswith("https://"))
        self.assertTrue(ACR.endswith("phishing-resistant"))
        self.assertEqual(AUDIENCE,"sns-growth-canary-human-identity")


if __name__ == "__main__":
    unittest.main()
