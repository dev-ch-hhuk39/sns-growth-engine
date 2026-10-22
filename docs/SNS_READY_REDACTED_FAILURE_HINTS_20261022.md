# SNS READY / Aftercare: classify private subprocess failures without exposing drafts

As of 2026-10-22, scheduled AUTO_READY and Aftercare occasionally returned
nonzero before emitting a valid JSON diagnostics report. Historical runs
could only report READY_DIAGNOSTICS_UNAVAILABLE, without telling an operator
whether the underlying failure could be rate limits, timeouts or permissions.

READY inventory stdout JSON and stderr remain in two separate private
per-step temporary files. When structured JSON is invalid or unavailable,
the redacted reporter now accepts --private-stderr and emits one fixed
PRIVATE_FAILURE_HINT category, never the actual content of that file.
The allowlist identifies only possible classes: API quota/rate,
process timeout, permission rejected, provider unavailable, Python
exception, or unclassified process failure. No arbitrary provider text,
queue identifiers, spreadsheet IDs, or draft content are displayed.

The original subprocess exit code and job failure remain authoritative.
A hint is NOT an assertion that a specific external provider caused the
failure. If structured JSON is valid, existing per-slot account-scoped
rejection reasons remain the canonical diagnostics.

The change modifies only the public workflow reporting contract and the
reporter; it does not alter production generation, review, paid budget,
SNS publishing, Cloudflare R2, GitHub permissions, VPS storage or
Google Sheets write authorization.

The next scheduled apply-mode failures, if any, should supply bounded
fixed-field hints. Historical failure logs cannot be retroactively fixed.

## Follow-up: stdout with non-JSON progress messages

A reproduced no-post manual Apply failed in READY maintenance with private
stderr empty and a report that could not be decoded as one JSON document.
The reporter now searches only a bounded set of column-zero JSON object
starts in the 5MB private stdout buffer and requires the final report's
fixed schema fields (status/results/account coverage/would_post=false).
This allows the last JSON report to be redacted even if harmless progress
messages or embedded generator reports precede it. An early BLOCKED
invocation is rendered only through a fixed reason allowlist; unknown
reason text is never printed.

This is **diagnostic recovery**, not an approval bypass, an automatic retry,
a forced new READY candidate, or evidence that the scheduled generation
failure is resolved. The original command's nonzero status remains decisive.
