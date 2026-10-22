# Manual READY status inspection without publishing or Sheets writes

Previously, a manual AUTO_READY dispatch using confirm_auto_ready=false
exited without checking the publication queue. The read-only preview now
inspects actual Google Sheets rows using exact-slot publisher DRY_RUN gates,
and emits redacted per-account coverage and rejection categories. It does
not generate ideas, make paid AI calls, change review status, or publish.

Operator: Autopilot AUTO_READY Pilot -> Run workflow -> main ->
account scope all or one -> horizon 6 or 24 hours ->
confirm_auto_ready=false. This is a real read-only readiness check.

Both stdout JSON and stderr are private temporary files and removed on EXIT.
Failures leave the job failed, and queue IDs/content cannot reach public CI.
The existing apply, review, quality and publication guards remain unchanged.
A PASS proves current coverage only, not future continuity or live posting.
