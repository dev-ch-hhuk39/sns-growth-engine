# SNS Growth Engine short-horizon READY no-due-slot distinction

2026-10-23: A posting-disabled 6-hour liver_manager AUTO_READY workflow
failed because there were zero text due slots in that short window.

One-account, 1-23 hour, non-evergreen bank maintenance now verifies
canonical due slots BEFORE any Sheets client or paid generator is created.
If there are no due text slots it returns status SKIPPED_NO_DUE_TEXT_SLOTS,
horizon_hours, zero covered/required, coverage_failure_reason of
NO_REQUIRED_TEXT_SLOTS, percentage null, reserve_status NOT_APPLICABLE,
empty hard delivery failures, no results and would_post false.
This is a no-op, NOT READY coverage success.

The diagnostic renderer enforces exact account, horizon, zero counters,
and no-post proof before displaying the fixed SKIPPED code; invalid skip
reports fail closed. No queue IDs or provider text are printed.

The original _coverage_result(0,0) FAILED invariant is retained.
Full 24h+ operational coverage, all-account monitoring and evergreen
reserve stock still fail closed if no planned due-slot proof exists.
Existing workflow Sheets verification remains mandatory. Approval and
publishing settings, CI cadence, VPS and R2 are unchanged.

Operational acceptance requires a new no-post 6-hour successful SKIP
run followed by an independent real 24-hour slot/stock assessment.
