# SNS Growth Engine: preserve bounded quality exploration (2026-10-23)

The public PR #457 repository-wide test detected an unintended change to
evergreen-bank quality retries. The earlier 10 distinct bounded theme
attempts on ordinary editorial QUALITY_EXHAUSTED were reduced to one,
because the newly introduced exact-slot planner incorrectly retired the
selected slot after any non-progressing attempt.

This correction preserves the ten-attempt total cap for ordinary
editorial rejections and spreads attempts over still-deficient canonical
text slots by attempt count, then available stock and deficit. The
existing provider timeout, quota/rate-limit and paid-approval-budget
circuit breakers still stop immediately; successful inventory keeps
all publisher, provenance and review gates.

No old queue IDs are changed, no posts are published, no additional
schedule/CI workflow is introduced, and no R2 or other VPS services
are modified. Production acceptance requires manual full regression
and a real no-post scheduled Apply result, separately from a healthy
read-only preview.
