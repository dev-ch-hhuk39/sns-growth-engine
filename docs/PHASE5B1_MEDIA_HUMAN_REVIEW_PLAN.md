# Phase 5B-1: Media Human Review Plan

## Purpose

Turn an existing **read-only scheduled autopost audit JSON** into account- and
slot-specific tasks for media rights, source lineage, technical evidence, and
caption quality. This tool **cannot approve rights, transition READY, publish,
download media, modify Sheets, or access the shared VPS**.

## Run from existing evidence

Run `python3 scripts/build_media_human_review_plan.py --audit-json AUDIT.json --output-json NEW_PLAN.json`.
The destination must not already exist. Omit `--output-json` to print sanitized JSON.

The input must be a complete scheduled read-only audit with four media slots,
posting and writes disabled, and unchanged protected rows. Missing or invalid
safety evidence causes a nonzero exit; it does not imply approval.

## Review categories

- P1: missing exact-slot candidate, unverified rights, permission, or queue ID.
- P2: missing technical, clip, source, model, or caption evidence.
- P3: apparent metadata completeness; **final human approval still required**.

Exact candidates only, maximum five per media slot. Recent media from another
slot is counted but never promoted automatically.

Output is a strict allowlist: account ID, slot ID, sanitized queue ID, enumerated
blocker codes, counts, manual review state. It never includes raw post text,
transcripts, source URLs, keys, or untrusted exception details.

P3 is NOT a publishable classification. Final rights/consent, claims, asset,
account fit and review must use the canonical approval flow.

## Next development stages

Phase 5B-2: explicit reviewer approval contract, rights expiry, evidence IDs
and append-only audit trail. Human approval remains mandatory.

Phase 5B-3: integrate in UI/operational review queue and test with per-account
scopes. Any VPS deployment, cron or server operation is handed off to the
dedicated shared VPS management chat.

## Test

`python3 scripts/test_build_media_human_review_plan.py`

`python3 scripts/run_repository_tests.py --pattern build_media_human_review_plan`

The full GitHub CI regression suite is required before merging.
