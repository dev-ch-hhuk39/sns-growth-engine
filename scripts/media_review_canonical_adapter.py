#!/usr/bin/env python3
"""Fail-closed canonical reader: protected rights vault + trusted snapshot provider.

The snapshot provider MUST be an independently authenticated server-side
reader of the operational queue and immutable draft history. It is not a
locally submitted JSON snapshot. Cross-store atomicity is NOT yet available.
"""
from __future__ import annotations

from typing import Any, Protocol

from media_review_trusted_precommit import (
    CanonicalReviewContext, PrecommitBlocked, ReviewRequest, _check_request,
)
from media_review_protected_evidence import ProtectedEvidenceVault
from build_media_review_approval_receipts import (
    _validate_plan, _validate_history, _sha256, ReviewContractError,
)


class TrustedOperationalSnapshot(Protocol):
    def load(self, account_id: str, slot_id: str, queue_id: str) -> tuple[
        dict[str, Any], dict[str, Any], dict[str, Any],
    ]:
        """Read plan, receipt history, and current queue server-side."""


class CanonicalProtectedReviewReader:
    def __init__(
        self, *, source: TrustedOperationalSnapshot | None,
        vault: ProtectedEvidenceVault,
    ) -> None:
        if source is None or not isinstance(vault, ProtectedEvidenceVault):
            raise PrecommitBlocked("canonical_backend_not_configured")
        self.source = source
        self.vault = vault

    def load_current(
        self, account_id: str, slot_id: str, queue_id: str,
    ) -> CanonicalReviewContext:
        _check_request(ReviewRequest(
            account_id, slot_id, queue_id, "revision00000001",
            "0" * 64, "0" * 64, "0" * 64, True,
        ))
        try:
            plan, receipts, queue = self.source.load(account_id, slot_id, queue_id)
            choices = _validate_plan(plan)
            events, _ = _validate_history(
                receipts,
                _sha256(plan),
                choices,
            )
            if not isinstance(queue, dict) or any(
                queue.get(k) != expected for k, expected in (
                    ("account_id", account_id), ("slot_id", slot_id),
                    ("queue_id", queue_id),
                )
            ):
                raise PrecommitBlocked("canonical_queue_changed")
            matches = [
                e for e in events
                if (e["account_id"], e["slot_id"], e["queue_id"]) == (
                    account_id, slot_id, queue_id,
                )
            ]
            if not matches:
                raise PrecommitBlocked("canonical_draft_missing")
            refs = matches[-1].get("evidence_ids")
            if not isinstance(refs, dict):
                raise PrecommitBlocked("canonical_evidence_missing")
            evidence = {ref: self.vault.get_current(ref) for ref in refs.values()}
            return CanonicalReviewContext(
                plan=plan, receipts=receipts, queue=queue, evidence_by_id=evidence,
            )
        except (PrecommitBlocked, ReviewContractError):
            raise PrecommitBlocked("canonical_context_invalid") from None
        except Exception:
            raise PrecommitBlocked("canonical_backend_unavailable") from None
