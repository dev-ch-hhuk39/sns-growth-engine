# Historical Publication Review mirrors - 2026-10-20

Read-only live Sheets inspection found 1,637 unique queue IDs and 58 duplicate review pairs: older rows 2-59 and newer rows 60-117. The older copies have no reviewer decision, notes, decision_applied_at, or result. Later copies have the same immutable review_id, account, platform and post_type, with strictly newer last_sync_at. Eight pairs differ in queue_status; 11 differ in public_post_text. Neither entry may be silently deleted.

The legacy REVIEW indexer now selects only the later snapshot when immutable scope and timestamp are proven, the older state is PENDING_REVIEW, and the older row has no manual reviewer data. Every ambiguous duplicate (old decision, missing or reversed timestamp, third occurrence, account/type mismatch) blocks all review writers before any mutation. QUEUE identities must always be unique.

The review sync now emits changed-cell-only updates, updating the sync timestamps only when another projection field actually changes, while preserving all human-authored cells and performing exact readback. No historic row is deleted, cleared, renamed or hidden. Separate archival/deletion requires independent owner-approved proof.

Tests: scripts/test_legacy_review_mirror_reconciliation.py plus existing review-board safety suites. A passing review workflow does not prove operational posting, READY inventory, media permissions or performance feedback. SNS publishing remains disabled.
