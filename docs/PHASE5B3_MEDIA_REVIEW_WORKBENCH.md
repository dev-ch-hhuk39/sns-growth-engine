# Phase 5B-3 — SNS Media Review Workbench (development-only)

## Delivered scope

A stand-alone **offline HTML review workbench** for the four scheduled media slots
of `night_scout` and `liver_manager`. The workbench joins the previous
5B-1 human review plan, optional 5B-2 draft receipt chain, and optional
read-only queue/evidence snapshots. Reviewers can filter by account and P1/P2/P3
and expand concrete missing checks. No media content, caption, source URLs,
credentials, or raw exception messages are displayed.

**All outputs remain `publish_authorized=false`, `authenticated_approval=false`,
`ready_transitions_performed=false`, `writes_performed=false`.** This phase
does not sign off on a decision or mutate the operational Sheets review queue.

## Generate the workbench

```bash
python3 scripts/build_media_review_workbench.py \
  --plan-json review-plan.json \
  --receipts-json review-receipts.json \
  --queue-snapshot-json queue-readonly-snapshot.json \
  --evidence-snapshot-json evidence-readonly-snapshot.json \
  --account-id liver_manager \
  --output-html media-review-workbench.html
```

Only `--plan-json` and `--output-html` are required. If snapshots are missing
or stale, the affected candidates display explicit blockers. The destination
must be a **new local file**, created with permission `0600`; it is never
overwritten. The page opens in a browser as a static local file with
no network endpoints and no submit/approve action. Do not publish or host it
on a public web server. Keep review documents outside Git.

## Read-only snapshot contracts

These are example *transport formats*, not authenticated attestations.
Use only exports collected through the permitted read-only review route.

### Queue snapshot

```json
{
  "schema_version": "sns_media_queue_snapshot_v1",
  "read_only": true,
  "captured_at": "2026-10-11T08:00:00Z",
  "rows": [
    {
      "queue_id": "clip_001", "account_id": "liver_manager",
      "slot_id": "lm_1800_clip_media", "status": "READY",
      "media_asset_id": "media_asset_001",
      "rights_status": "APPROVED", "permission_status": "APPROVED",
      "rights_review_required": false, "validator_status": "PASS",
      "internal_leak_status": "PASS", "account_fit_status": "PASS",
      "alignment_status": "PASS", "hybrid_ai_status": "PASS"
    }
  ]
}
```

### Evidence snapshot

```json
{
  "schema_version": "sns_media_evidence_snapshot_v1",
  "read_only": true,
  "captured_at": "2026-10-11T08:00:00Z",
  "records": [
    {
      "evidence_id": "ev_rights_20261011",
      "kind": "rights_grant", "account_id": "liver_manager",
      "slot_id": "lm_1800_clip_media", "queue_id": "clip_001",
      "media_asset_id": "media_asset_001",
      "verification_status": "VERIFIED",
      "usage_scope": "THREADS_ORGANIC_ONLY",
      "rights_valid_from": "2026-10-01T00:00:00Z",
      "rights_expires_at": "2026-12-01T00:00:00Z",
      "revoked": false
    }
  ]
}
```

An approval-draft references **all** required evidence kinds as defined in
`scripts/build_media_review_approval_receipts.py`. Snapshots must be no more
than 30 minutes old. Missing/duplicate IDs, scope mismatch, unknown proof IDs,
revocation, expired rights, missing media asset, incomplete quality gates,
or a stale snapshot results in a visible blocker. Import does **not** establish
evidence authenticity; a JSON `VERIFIED` label is not a trust proof.

## Existing operational queue — important boundary

`scripts/apply_publication_review_decisions.py` and
`scripts/approve_queue.py` already contain their own Sheets mutations.
**This workbench does not call or change them.** It must not be treated as
an authorization source by those older workflows. They require a separate
security review before any new authenticated approval path is connected.

## Why actual authenticated approval is not enabled

The repository has no server-side reviewer identity provider or protected
evidence repository connected to the Phase 5B-2 receipt contract. Creating
locally editable JSON with a claimed reviewer ID cannot replace either.
Actual READY decisions must await:

1. Trusted session/role verification on the server and account-scoped RBAC.
2. A protected evidence store validating original asset and creator rights,
   media lineage, expiration, paid/organic/channel usage, and revocation.
3. Fresh canonical queue reads and an atomic compare-and-swap + append-only
   audit transaction. Never mark a queue READY from a local receipt alone.
4. Publisher-side revalidation just before posting, and independent real
   posting approval (publishing remains disabled).
5. An audited rollout plan, with any VPS changes handed to the dedicated
   shared VPS operations chat.

These blockers are explicitly listed rather than bypassed.

## Tests

```bash
python3 scripts/test_build_media_review_workbench.py
python3 scripts/run_repository_tests.py --pattern build_media_review_workbench
```

Full GitHub CI must pass before merge. No production deployment in this phase.
