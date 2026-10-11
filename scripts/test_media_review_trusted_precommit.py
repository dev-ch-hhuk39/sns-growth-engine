#!/usr/bin/env python3
"""Test the Phase 5B-4A trusted-precommit policy without live credentials."""
from __future__ import annotations

import copy
import sys
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_media_review_approval_receipts import _sha256  # noqa: E402
from media_review_trusted_precommit import (  # noqa: E402
    CanonicalReviewContext, PrecommitBlocked, ReviewRequest,
    VerifiedReviewer, evaluate_precommit,
)
from test_build_media_review_approval_receipts import (  # noqa: E402
    NOW, clip_action, sample_plan, validate,
)
from test_build_media_review_workbench import (  # noqa: E402
    evidence_snapshot, queue_snapshot,
)

AUTHORIZATION = "Bearer fake-signed-token-fixture-only"
ISSUER = "https://id.example.test/verified"
QUEUE_REVISION = "rev_0000001"
SUBJECT = "reviewer_0001"


class FakeIdentityVerifier:
    def __init__(self, principal=None, *, error=False):
        self.principal = principal or good_principal()
        self.error = error
        self.calls = 0

    def verify(self, bearer_token, *, now):
        self.calls += 1
        if self.error or bearer_token != AUTHORIZATION.split()[1]:
            raise ValueError("test_provider_unavailable_fake_secret")
        return self.principal


class FakeCanonicalReader:
    def __init__(self, context=None, *, error=False):
        self.context = context or good_context()
        self.error = error
        self.calls = 0

    def load_current(self, account_id, slot_id, queue_id):
        self.calls += 1
        if self.error:
            raise ValueError("private_record_path_example")
        return self.context


def good_principal() -> VerifiedReviewer:
    return VerifiedReviewer(
        subject=SUBJECT, roles=frozenset({"MEDIA_REVIEWER"}),
        account_scopes=frozenset({"liver_manager"}),
        issuer=ISSUER, audience="sns-growth-media-review",
        authenticated_at=NOW - timedelta(minutes=4),
        mfa_at=NOW - timedelta(minutes=2),
        expires_at=NOW + timedelta(hours=1),
    )


def good_context() -> CanonicalReviewContext:
    plan = sample_plan()
    receipts = validate(plan, clip_action())
    row = queue_snapshot()["rows"][0]
    row.update({
        "platform": "threads", "revision": QUEUE_REVISION,
        "source_id": "source_video_001",
    })
    records = {
        record["evidence_id"]: {
            **record,
            "source_id": "source_video_001",
            "original_reference_verified": True,
            "allowed_platforms": ["threads"],
            "allowed_territories": ["JP"],
            "verified_at": (NOW - timedelta(hours=1)).isoformat(),
        }
        for record in evidence_snapshot()["records"]
    }
    return CanonicalReviewContext(
        plan=plan, receipts=receipts, queue=row, evidence_by_id=records,
    )


def good_request(ctx=None) -> ReviewRequest:
    ctx = ctx or good_context()
    return ReviewRequest(
        account_id="liver_manager",
        slot_id="lm_1800_clip_media",
        queue_id="clip_001",
        expected_queue_revision=QUEUE_REVISION,
        expected_plan_sha256=_sha256(ctx.plan),
        expected_receipts_head_sha256=ctx.receipts["last_event_sha256"],
        draft_event_sha256=ctx.receipts["events"][0]["event_sha256"],
        confirm_human_review=True,
    )


def evaluate(
    *,
    request=None, principal=None, context=None, token=AUTHORIZATION,
    verifier=None, canonical=None, issuer=ISSUER,
):
    context = context or good_context()
    return evaluate_precommit(
        request or good_request(context), token,
        verifier=verifier or FakeIdentityVerifier(principal),
        canonical=canonical or FakeCanonicalReader(context),
        trusted_issuer=issuer, as_of=NOW,
    )


class TrustedReviewPrecommitTests(unittest.TestCase):
    def test_matching_trusted_providers_only_prepare_no_approval_or_ready(self):
        context = good_context()
        before = copy.deepcopy(context)
        identity = FakeIdentityVerifier()
        reader = FakeCanonicalReader(context)
        result = evaluate(context=context, verifier=identity, canonical=reader)
        self.assertEqual(result["status"], "PRECOMMIT_CHECKS_PASSED_NO_APPROVAL")
        self.assertEqual(identity.calls, 1)
        self.assertEqual(reader.calls, 1)
        self.assertEqual(result["session_subject"], SUBJECT)
        self.assertEqual(result["queue_revision"], QUEUE_REVISION)
        self.assertTrue(result["session_verified_by_adapter"])
        self.assertTrue(result["trusted_evidence_checked"])
        self.assertTrue(result["requires_atomic_approval_commit"])
        self.assertTrue(result["requires_publish_time_revalidation"])
        for key in ("effective_approval", "ready_transitions_performed",
                    "writes_performed", "publish_authorized"):
            self.assertIs(result[key], False)
        self.assertEqual(context, before)

    def test_missing_backend_adapters_block_before_identity_or_any_write(self):
        with self.assertRaisesRegex(PrecommitBlocked, "trusted_adapters_not_configured"):
            evaluate_precommit(good_request(), AUTHORIZATION,
                               verifier=None, canonical=None,
                               trusted_issuer=ISSUER, as_of=NOW)

    def test_invalid_or_untrusted_session_fails_without_calling_canonical(self):
        reader = FakeCanonicalReader()
        for token in ("", "bearer fake", "Bearer ", "Bearer one two"):
            with self.subTest(token=token), self.assertRaises(PrecommitBlocked):
                evaluate(token=token, canonical=reader)
        self.assertEqual(reader.calls, 0)
        reader = FakeCanonicalReader()
        with self.assertRaisesRegex(PrecommitBlocked, "session_verification_failed") as cm:
            evaluate(verifier=FakeIdentityVerifier(error=True), canonical=reader)
        self.assertNotIn("fake_secret", str(cm.exception))
        self.assertEqual(reader.calls, 0)

    def test_rbac_account_scope_role_expiry_and_mfa_fail_closed(self):
        principal = good_principal()
        modified = [
            replace(principal, roles=frozenset({"VIEWER"})),
            replace(principal, account_scopes=frozenset({"night_scout"})),
            replace(principal, issuer="https://untrusted.test"),
            replace(principal, audience="other-system"),
            replace(principal, disabled=True),
            replace(principal, subject=""),
            replace(principal, authenticated_at=NOW - timedelta(days=1)),
            replace(principal, expires_at=NOW),
            replace(principal, mfa_at=None),
            replace(principal, mfa_at=NOW - timedelta(hours=2)),
        ]
        for index, user in enumerate(modified):
            with self.subTest(index=index), self.assertRaises(PrecommitBlocked):
                evaluate(principal=user)

    def test_submitted_reviewer_identity_claim_is_not_trusted(self):
        ctx = good_context()
        ctx.receipts["events"][0]["reviewer_id"] = "impersonated_user"
        # The tampered hash must be rejected even before the identity mismatch.
        with self.assertRaisesRegex(PrecommitBlocked, "review_draft_chain_invalid"):
            evaluate(context=ctx)

    def test_changed_queue_status_version_account_asset_source_or_rights_blocks(self):
        changes = (
            {"revision": "rev_0000002"},
            {"status": "WAITING_REVIEW"},
            {"status": "POSTED"},
            {"account_id": "night_scout"},
            {"slot_id": "ns_2100_clip_media"},
            {"media_asset_id": ""},
            {"source_id": ""},
            {"rights_status": "DENIED"},
            {"permission_status": "UNKNOWN"},
            {"rights_review_required": True},
            {"platform": "x"},
            {"validator_status": "FAIL"},
            {"hybrid_ai_status": ""},
        )
        for change in changes:
            with self.subTest(change=change):
                ctx = good_context()
                ctx.queue.update(change)
                with self.assertRaises(PrecommitBlocked):
                    evaluate(context=ctx)

    def test_expired_revoked_mismatched_unverified_proof_blocks(self):
        changes = (
            {"verification_status": "PENDING"},
            {"revoked": True},
            {"source_id": "different_source"},
            {"media_asset_id": "different_asset"},
            {"account_id": "night_scout"},
            {"usage_scope": "PAID_ADVERTISING"},
            {"allowed_platforms": ["x"]},
            {"allowed_territories": ["US"]},
            {"original_reference_verified": False},
            {"rights_expires_at": "2026-10-01T00:00:00Z"},
            {"rights_valid_from": "2026-10-12T00:00:00Z"},
            {"verified_at": "2026-09-01T00:00:00Z"},
        )
        for change in changes:
            with self.subTest(change=change):
                ctx = good_context()
                ctx.evidence_by_id[next(iter(ctx.evidence_by_id))].update(change)
                with self.assertRaises(PrecommitBlocked):
                    evaluate(context=ctx)

    def test_missing_proof_and_wrong_plan_or_draft_hash_fail(self):
        ctx = good_context()
        del ctx.evidence_by_id[next(iter(ctx.evidence_by_id))]
        with self.assertRaisesRegex(PrecommitBlocked, "trusted_evidence_missing"):
            evaluate(context=ctx)
        ctx = good_context()
        request = replace(good_request(ctx), expected_plan_sha256="f"*64)
        with self.assertRaisesRegex(PrecommitBlocked, "review_plan_changed"):
            evaluate(context=ctx, request=request)
        ctx = good_context()
        request = replace(good_request(ctx), expected_receipts_head_sha256="f"*64)
        with self.assertRaisesRegex(PrecommitBlocked, "review_draft_changed"):
            evaluate(context=ctx, request=request)
        ctx = good_context()
        request = replace(good_request(ctx), draft_event_sha256="f"*64)
        with self.assertRaisesRegex(PrecommitBlocked, "review_draft_not_authorizable"):
            evaluate(context=ctx, request=request)

    def test_rejected_candidate_or_draft_replay_is_not_authorizable(self):
        ctx = good_context()
        clip = next(item for item in ctx.plan["items"] if item["queue_id"] == "clip_001")
        clip.update(priority="P2", review_state="ACTION_REQUIRED",
                    blockers=["rights_human_verification_required"])
        request = replace(good_request(ctx), expected_plan_sha256=_sha256(ctx.plan))
        with self.assertRaisesRegex(PrecommitBlocked, "review_candidate_not_eligible"):
            evaluate(context=ctx, request=request)
        # Append a non-approval draft; the latest decision must now deny access.
        ctx = good_context()
        from test_build_media_review_approval_receipts import request_for
        from build_media_review_approval_receipts import build_receipts
        from datetime import timezone
        hold = {
            "account_id": "liver_manager",
            "slot_id": "lm_1800_clip_media",
            "queue_id": "clip_001",
            "reviewer_id": SUBJECT,
            "reviewed_at": "2026-10-11T11:59:00+00:00",
            "decision": "REQUEST_EVIDENCE",
            "reason_code": "evidence_missing",
        }
        ctx2 = good_context()
        ctx2 = replace(
            ctx2,
            receipts=build_receipts(ctx2.plan, request_for(ctx2.plan, hold),
                                    as_of=NOW, previous=ctx2.receipts),
        )
        request = good_request(ctx2)
        with self.assertRaisesRegex(PrecommitBlocked, "review_draft_not_authorizable"):
            evaluate(context=ctx2, request=request)

    def test_malformed_inputs_fail_closed_without_raw_data_leaking(self):
        ctx = good_context()
        malformed = [
            replace(good_request(ctx), queue_id=["secret-not-string"]),
            replace(good_request(ctx), account_id=["night_scout"]),
            replace(good_request(ctx), confirm_human_review=False),
            replace(good_request(ctx), expected_queue_revision=""),
        ]
        for request in malformed:
            with self.assertRaises(PrecommitBlocked):
                evaluate(request=request, context=ctx)
        ctx = good_context()
        e = ctx.receipts["events"][0]
        e["evidence_ids"]["rights_grant"] = ["not-a-string"]
        # Explicitly reject malformed evidence even if the receipt's hash would
        # otherwise be inconsistent.
        with self.assertRaises(PrecommitBlocked):
            evaluate(context=ctx)

    def test_no_live_publisher_sheets_service_or_http_endpoint_imports(self):
        path = ROOT / "scripts/media_review_trusted_precommit.py"
        source = path.read_text(encoding="utf-8")
        for forbidden in ("from sheets_client", "from publishers",
                          "requests.", "google.auth", "update_queue_item",
                          "app.route", "Flask(", "FastAPI("):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
