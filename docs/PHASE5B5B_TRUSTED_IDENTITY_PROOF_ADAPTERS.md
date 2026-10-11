# Phase 5B-5B — Verified identity and protected rights-proof adapters

## Development implementation (not production authorization)

- `media_review_verified_identity.py`: pinned RSA/RS256 JWT signature verification (no network key discovery, HS256 or unsigned JWT); exact issuer, audience, time window, subject, session ID and MFA claims; SHA-256 token binding to **server-provisioned active sessions**, revocation and account-level RBAC loaded from SQLite, not JWT role claims.
- `media_review_protected_evidence.py`: append-only, protected original-proof bytes with digest and chained events, rights metadata, account/asset/source binding, human-attestation entrypoint, authenticated revocation, duplicate operation prevention and immutable-history validation.
- `media_review_canonical_adapter.py`: bridge from a **trusted server-side operational snapshot provider** to protected evidence records. It deliberately does not ship an unsafe JSON or Google Sheets trust adapter. If the authoritative reader is missing or inconsistent it fails closed.
- `db/migrations/0002_sns_media_review_trust_store.sql`: isolated development schema for session grants and protected evidence; applied only in disposable offline tests.

## Trust boundaries and remaining gaps

No login service, production issuer/key distribution, IdP session provisioning, privileged role-admin backend, protected production DB, genuine original-rights verification process or trusted atomic operational queue adapter is currently provisioned by this PR. Thus the classes are only production-ready *building blocks*, not proof of a real authentication integration.

**A human_checked flag in a backend call cannot itself prove that a proof was examined.** The future protected UI must independently authenticate reviewers, record the inspected original and bind a decision transactionally. Production must enforce file ownership, encrypted backups, external audit head anchoring, DB migration and recovery tests.

The queue provider must read canonical, current, server-controlled queue/plan/receipts. The current SQLite review ledger and Google Sheets queue do **not** share one transaction. A change in either store can invalidate a prior check. Solve in Phase 5B-5C before effective approval is allowed.

Every `record_review` result remains:
`effective_approval=false`, `ready_transitions_performed=false`,
`authenticated_approval_integrated=false`, `publish_authorized=false`,
`external_queue_atomicity_guaranteed=false`.

No auto-READY, publisher, X automation, existing production DB, VPS or shared services were changed.

## Local validation

```bash
python3 scripts/test_media_review_verified_adapters.py
python3 scripts/test_media_review_trusted_precommit.py
python3 scripts/test_media_review_transactional_ledger.py
python3 scripts/run_repository_tests.py
python3 scripts/test_all_workflows_safety_flags.py
```

Tests use ephemeral RSA keys and in-memory SQLite, never actual credentials or a live identity provider. Real provider integration and cross-system consistency remain open.

## VPS operations handoff (not authorized in this chat)

Before any production deployment, VPS management must obtain approved source SHA, check `/run/lock/chadult-production-deploy.lock`, run resource preflight, back up before migration, provision a dedicated protected DB and trusted IdP session feed, verify backups and restoration on a disposable copy, prove access denial and provider key rotation, check health and rollback. Do not promote approval or publishing merely because this source-code phase is merged.
