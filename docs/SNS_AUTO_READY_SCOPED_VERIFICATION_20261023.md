# Scoped READY execution, 2026-10-23

The 2026-10-23 three-account manual no-post tests each prepared
their next text-slot inventory successfully, but run_autopilot_loop
then returned FAILED. A direct production read-only check found:
the legacy all-pipeline recovery verifier exits 1 even though
the scheduled text-inventory verifier passes. The all-pipeline
verifier includes unrelated legacy media/production constraints.
Its failure is not evidence that no-post text READY is unsafe.

The new --ready-only path applies ONLY for one account, --auto-ready,
--apply --confirm-run, --use-sheets, --skip-real-post, no auto-post,
no real-post confirmation, and maximum three candidate approvals.
It uses text-scoped Sheets verification before and after optional
safe candidate approval and performs no Threads worker invocation.
It calls the existing auto_approve_queue validation/persistence with
--skip-setup to avoid rediscovering/creating tabs already verified.

This is not a general bypass of verification and does NOT enable any
publishing path, media rights, owner-review exception or X posting.
The legacy autopilot path keeps full verification and publisher checks.
The job emits three fixed, whitelisted stage statuses only; raw content,
queue IDs, child commands, stderr, and credentials remain private.
Even an ambiguous approval error triggers the postwrite verification
and a nonzero overall outcome.

The separate exact-slot inventory maintainer remains the authoritative
delivery coverage check and the evergreen bank remains a distinct
optional reserve hard failure. The failure analysis is grounded in
job logs: 3/3 night, 3/3 liver and 1/1 Beauty 24h READY read-only
coverage, yet redundant full-pipeline autopilot returned failed
without identifying its nested step. The isolated workflow directly
solves this category of failure without claiming complete live
posting or 24/72/168h metric evidence.
