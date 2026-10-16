# Phase 5B-6W/X: Queue identity and read-only authority cutover audit

Date: 2026-10-13 JST. Local code only, based on commit bba212d.
**This is not an operational authority migration or publishing authorization.**

## 6W: Operational queue writer safeguards

- src/sheets_client.py: queue append now requires an existing valid schema, a
  globally unique queue ID, nonempty account/platform and an unchanged protected
  media READY block. One RAW append, then fresh full-row verification. Unknown
  acknowledgement or readback mismatch stops without automatic retry.
- src/queue_builder.py: drafts are de-duplicated per account + platform, so
  the same draft ID in Night and Liver does not suppress the other account.
  The real and mock SheetsClient support this optional account scope.
- SheetsClient.update_queue_item: requires one exact globally matching queue
  ID using gspread findall instead of silently updating the first match.
  Existing RAW field update and server-side readback remain required.
- scripts/process_threads_queue.update_row: the publishing worker has the
  same exact-ID requirement, blocks READY -> PROCESSING if the source row is
  no longer READY, and now verifies every persisted supported field after a
  single RAW batch update. Unknown results require manual reconciliation.
- MockSheetsClient follows the same duplicate-ID protections.

These protections are **not Google Sheets compare-and-swap**. Other hosts or
legacy scripts may race between preflight and update. No distributed one-use
lease has been created. A verified, operations-owned writer cutover is needed
for an actual single source of truth.

## 6X: Read-only cutover audit

scripts/audit_queue_authority_cutover.py accepts a *local*, minimal-metadata
snapshot and an existing protected SQLite database. It opens the database
read-only (mode=ro, query_only=ON), reuses the existing shadow, managed writer,
outbox and mirror projection chain validators, and checks the frozen 6H
Sheets mutation inventory.

The audit checks queue IDs across accounts, missing protected media rows,
incorrect legacy media READY/PROCESSING/POSTED, uncertain post outcomes,
cross-account posted results, unverifiable posted results, and stale snapshots.
Findings contain static codes and hashed identity prefixes rather than raw
queue IDs, post text or private media. Unexpected input fields (including
captions, tokens, URLs) and excessive file size are rejected.

Offline metadata JSON shape (synthetic illustration only):

    {
      "schema": "sns_operational_queue_offline_metadata_v1",
      "observed_at": "2026-10-13T13:00:00+09:00",
      "queue_rows": [{
        "account_id": "liver_manager",
        "slot_id": "lm_1800_clip_media",
        "queue_id": "synthetic_queue",
        "platform": "threads",
        "status": "WAITING_REVIEW",
        "media_required": "true",
        "media_asset_id": "synthetic_asset"
      }],
      "posted_rows": []
    }

Ops can later run locally, only after authorized data handling:

    python3 scripts/audit_queue_authority_cutover.py \
      --snapshot /private/operator/sns_queue_metadata.json \
      --protected-db /private/operator/review.db \
      --output /tmp/sns_queue_cutover_report.json

Output is sanitized. The command **always exits 2** with
production_cutover_authorized=false, even if local_parity_status=PASS. Offline
JSON is NOT signed Google evidence and protected SQLite is only a blocked
review/mirror authority, NOT the operational queue replacement.

## Tests and remaining implementation

- New offline adversarial suites:
  scripts/test_operational_queue_append_boundary.py;
  scripts/test_queue_cutover_readonly_audit.py.
- Expanded scripts/test_legacy_queue_write_safety.py with publisher identity
  collision, stale READY and read-after-write failure scenarios.
- Existing 6A media interlocks, 6H AST inventory, queue builder, publisher
  and aftercare tests must remain green.
- Mac-local developer QA: python3 scripts/run_local_quality_gate.py --mode
  focused, then --mode full. Never launch GitHub Actions or production canaries
  from this chat.

Production cutover still needs an owner-approved authoritative system choice,
callsite-by-callsite cutover of legacy writers, signed IdP and current ACL,
backup/restore proof, real signed source freshness, a one-use distributed
publish claim and operator canaries. Historical unknown outcomes must be
reconciled without re-posting. Real timed 24h/72h/168h and same-account PDCA
observations are still not proved by synthetic tests.

No credentials, Codex, Actions workflow, public GitHub push, VPS operation,
production Sheets mutation, SNS post, paid AI, or external transport used.

## Final verification evidence (2026-10-13 JST)

- Mac-local full repository offline runner: **984/984 test scripts PASS**, zero
  failures. Existing external credential/network probes and optional
  local-tool probes remain excluded by the repository's normal policy.
- Static workflow safety, Ruff fatal rules, Python compileall, unstaged and
  staged diff checks, and local gitleaks scan: all PASS.
- The first full run had one **test fixture mismatch**: the synthetic
  Threads-ID worksheet used the old single-cell lookup and lacked persisted
  readback. Its fake now implements exact findall and real row readback;
  the long platform identifier remains literal and the full suite then passed.
  Production unique-ID and readback guards were not weakened.
- Full local report: /tmp/sns-20261013-phase6wx-final-full.json .
  Temporary QA evidence is on the connected Mac, not in Git and not
  production provider evidence.
- No actual production source migration or signed IdP/ACL enrollment,
  Google/SNS request, VPS mutation, PR, public push or deployment occurred.
