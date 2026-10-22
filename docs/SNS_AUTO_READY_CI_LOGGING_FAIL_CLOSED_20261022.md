# AUTO_READY hosted CI: redacted receipts and fail-closed child commands (2026-10-22)

## Scope and operator safety
This change covers AUTO_READY and Aftercare READY-inventory logging, the CLI reporting contract
of the parent autopilot loop, and a fixed-field evergreen-bank status renderer.
No publication switch, review/approval rule, Sheet permission, R2 setting,
VPS asset, backup retention, or paid provider budget is changed.

The repository is public. Generated queue IDs and nested subprocess
stdout/stderr may contain unpublished content or operational details;
therefore hosted Actions must not echo complete JSON maintenance reports.

## Publication flow
1. Exact-slot READY maintenance captures stdout/stderr in a private
   temporary file, emits only allowlisted inventory diagnostic aggregates,
   and exits nonzero if maintenance or report parsing failed.
2. The evergreen bank step captures stdout/stderr in another temporary file,
   emits fixed-field bank counts, and fails closed if the archive is incomplete
   or the bank target is unmet.
3. The parent autopilot step uses skip-real-post and summary-only flags. It
   prints only account, step count, status and real-post-gate fields.
   Nonzero return codes from any nested subprocess cause parent nonzero.
4. Aftercare uses the same private captures for READY and evergreen output.
   Both workflows retain their existing approval gates and failure semantics.
5. Temporary reports are removed on EXIT. Publication remains disabled.
   Failure must remain visible as a failed workflow rather than a misleading
   success status.

## Validation and acceptance
- Synthetic: test_run_autopilot_loop_fail_closed.py;
  test_ready_evergreen_bank_summary.py;
  test_auto_ready_ci_redaction_contract.py.
- Existing READY, workflow, no-post, approvals, and isolation tests.
- Public GitHub-hosted PR CI (ci.yml/pr-gate) is required before merge.
- After merge: monitor next scheduled READY and Aftercare runs with
  all publication gates OFF. Historical failures are not proof current code
  is broken.
- A parent command's DONE status means its children returned zero;
  it does NOT mean that a real Threads post occurred.
  Long-term 24/72/168h metrics acceptance is separate.

## Exclusions
This change does not certify full Google Sheets native restore, off-VPS
two-device credential recovery, or deletion eligibility for old VPS releases.
Those remain separate SNS Issue #437 / AgentOps Issue #35 / SNS Issue #439 gates.
