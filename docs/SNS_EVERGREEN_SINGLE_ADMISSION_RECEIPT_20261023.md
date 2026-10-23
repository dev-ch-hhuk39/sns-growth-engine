# SNS Growth Engine: one verified Sheets admission for evergreen candidates

Date: 2026-10-23 JST

## Confirmed code path
- In the 24-hour evergreen refill path, admit_bank_batch already
  clears both temporary queue date fields, appends the exact queue ID
  to the evergreen_bank tab, rereads both Sheets tabs, validates each
  source queue identity and the new bank record, and returns an
  affirmative SAVED / read_after_write PASS receipt.
- The caller was then repeating date clearing for every newly generated
  candidate through release_temporary_bank_allocations. This redundant
  per-row Sheets update/readback increases quota usage and can raise an
  ambiguous error AFTER the canonical batch has committed.
- The standalone legacy release function stays intact for its existing
  independent consumers/tests; the production replenishment caller
  no longer invokes it after an already verified admission.

## Change
- One bounded verified_bank_admission helper for newly generated and
  pre-existing eligible unallocated bank candidates.
- Require a complete SAVED receipt, exact candidate count,
  read_after_write PASS and would_post false.
- Do not count a candidate or claim READY_INVENTORY_OK when the
  admission receipt is incomplete or ambiguous.
- Refresh the read-only snapshot after the verified batch.
- Explicit synthetic regression verifies one canonical batch, dates
  cleared only once, no legacy second write, and fail-closed receipts.
- Private stderr classification now reveals only exact allowlisted
  evergreen readback error codes in the public CI hint. Quota and
  provider timeout signals retain higher priority. Other private
  exception text, paths and queue IDs are never printed.

## Sheets quota reduction

Production replenishment originally requested four read-only tabs
(queue, evergreen_bank, posted_results, content_slot_runs) using four
separate API calls. Genuine SheetsClient objects now prime the existing
one-request values_batch_get snapshot for all four before inventory checks.
Mock clients retain their existing test adapter. A failed initial batch
stops immediately before candidate admission or paid generation.

Synthetic tests verify one batch and fail-closed on quota errors. This
reduces initial values reads from four to one, but does not eliminate
Sheets metadata requests or guarantee success during a rate-limited minute.
The bank-only CLI previously loaded the queue and ensured bank headers
before invoking replenishment, which performed those same operations again.
The wrapper now delegates exactly one queue snapshot and one bank header
check to the canonical replenisher. A bank-only dry-run plan does not
create a Sheets client or request credentials. Normal READY delivery
keeps its existing data loading and approval path unchanged.

## Safety / limitations
- Zero real SNS posts or activation changes.
- No changes to R2, other VPS applications, credentials, or workflows.
- This removes one unnecessary failure surface; it is NOT evidence
  that the historical Beauty Python exception's exact cause has
  been established or that the 8 missing reserves are now approved.
- The Beauty evergreen inventory most recently had 22 effective
  approved entries of the required 30 in a read-only synthetic shadow
  audit; independent production replenishment remains an acceptance
  requirement, with paid budget, reviewer and quality gates unchanged.
- PR #463, which hardens provider output parsing, is separately open,
  with clean checks but an outstanding manual merge requirement.
