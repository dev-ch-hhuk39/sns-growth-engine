# Phase 5B-2 — Media Review Evidence & Draft Approval Receipts

## Security boundary

An entry here is **not a verified human approval**. The reviewer ID and
evidence IDs are self-reported until Phase 5B-3 connects a trusted login,
evidence store and the canonical operational queue. No service tokens, URLs,
media content, captions, Sheets access, READY transition, or posting are used.

This phase validates a person's **proposed decision** against an existing
Phase 5B-1 human-review plan. It creates an immutable local JSON snapshot
with chained SHA-256 event digests, so accidental alterations are detectable
relative to a saved head hash. SHA-256 chaining alone is **not a digital
signature** and cannot prove authorship or prevent complete ledger rewriting.

## Intake schema

1. Generate a sanitized review plan using
   `scripts/build_media_human_review_plan.py` on an authorized read-only audit.
2. Compute the plan fingerprint:

```bash
python3 -c 'import hashlib,json,sys; p=json.load(open(sys.argv[1])); print(hashlib.sha256(json.dumps(p,ensure_ascii=True,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest())' review-plan.json
```

3. Prepare an intake JSON with an exact plan fingerprint, an explicit
   reviewer identity *claim*, and one or more decisions. Examples:

```json
{
  "schema_version": "sns_media_review_intake_v1",
  "source_plan_sha256": "<sha256 of complete plan>",
  "events": [
    {
      "account_id": "liver_manager",
      "slot_id": "lm_1800_clip_media",
      "queue_id": "clip_001",
      "reviewer_id": "reviewer_0001",
      "reviewed_at": "2026-10-11T11:00:00+09:00",
      "decision": "REQUEST_EVIDENCE",
      "reason_code": "evidence_missing"
    }
  ]
}
```

Allowed decisions: `APPROVE`, `REJECT`, `REQUEST_EVIDENCE`, `REVOKE`.
Use `REQUEST_EVIDENCE` with an empty queue ID only for a missing exact-slot
candidate. A missing candidate can never be approved or rejected.

An `APPROVE` draft is allowed only for an exact candidate with no blockers
and Phase 5B-1 priority P3. It requires:

- `human_checks_confirmed: true` (self-reported; authentication is still pending)
- `usage_scope: THREADS_ORGANIC_ONLY` (does not include paid ads or X)
- timezone-aware `rights_valid_from` and `rights_expires_at` covering both
  the declared review time and the current validation time
- distinct, constrained evidence references prefixed `ev_` for
  `rights_grant`, `publisher_permission`, `source_identity`,
  `media_validation`, `caption_quality`, `account_fit`,
  `asset_provenance`, plus `clip_lineage` for source-video clips

Other decisions take an enumerated `reason_code`; `REVOKE` also requires
`revokes_event_sha256` pointing at the latest approval-draft event for the
same exact candidate. Cross-account, wrong-slot, expired, unsigned,
duplicate, incomplete, and malformed inputs are rejected.

## Generate offline receipt snapshot

```bash
python3 scripts/build_media_review_approval_receipts.py \
  --plan-json review-plan.json \
  --intake-json reviewer-decisions.json \
  --output-json review-receipts-v1.json
```

To produce an append-only *logical* history, pass the previous snapshot
as `--previous-receipts-json` and supply a **new** `--output-json` path.
The prior snapshot is not overwritten. Confirm or externally pin the
expected head SHA-256 outside the file before treating it as evidence
of changes. History with broken hashes, wrong source-plan bindings,
or unexpected fields is refused. Only sanitized IDs, timestamps,
enumerated reasons and event hashes are exported.

**Every event** always has `reviewer_identity_verified=false`,
`effective_approval=false`, and `publish_authorized=false`.
**Every snapshot** has `authenticated_approval=false`,
`ready_transitions_performed=false` and `writes_performed=false`
(meaning no operational queue/Sheets writes; the new local JSON file
is deliberately written when requested).

## Before Phase 5B-3 can enable authoritative review

- Bind reviewer identity and role to a server-side authenticated session.
- Retrieve and validate evidence IDs in a protected evidence store;
  match the exact source and media asset identity in the current queue.
- Check license start, expiry, channel, organic/paid scope, consent
  revocation, usage territory and the account/slot at decision and
  immediately before any eventual publish.
- Persist authorized approvals or revocations atomically in the
  canonical ledger, with immutable server-side audit records.
- Re-run rights, caption, quality, media and READY validation immediately
  before any transition, and continue to require explicit posting approval.

No automation, VPS operation, cron job or GitHub deployment is part of
Phase 5B-2. For regression, run:

`python3 -m unittest scripts.test_build_media_review_approval_receipts`

Full repository GitHub CI is mandatory before merging.
