# SNS Growth Engine generator output safety contract, 2026-10-23

A no-write/no-paid-provider production Beauty reserve shadow found
22 of required 30 usable candidates. The previous 24-hour job logged
a private PYTHON_EXCEPTION, but the exact private traceback was not
retained by the public GitHub Actions log.

Source review found unsafe assumptions in generated envelopes:
null/scalar queue-id lists, null Beauty apply_result, a truthy
read_after_write=FAILED string, malformed nested budget stages and
invalid reviewer JSON could raise exceptions or bypass readback gates.

This patch rejects malformed queue identifiers and unaffirmed Beauty
read-after-write responses before running READY approval. Provider
and reviewer output shape faults are classified as fixed
GENERATION_OUTPUT_INVALID / READY_REVIEW_REPORT_INVALID codes,
without emitting unpublished text or IDs to CI logs. A malformed
review file can never authorize READY even with child exit code 0.
Paid-provider rate-limit, budget, timeout and approval guards remain.

These are prevention and error handling improvements, not proof of
the historical exception's exact cause and not actual replenishment
of the eight missing validated Beauty reserves.

No SNS real posting, R2 modification, other VPS services or changes
to the configured reserve minimum were authorized or performed.
