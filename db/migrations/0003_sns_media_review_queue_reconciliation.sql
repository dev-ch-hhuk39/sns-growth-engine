-- Phase 5B-5C: transactionally bind isolated review events to observed queue
-- revisions in the SAME SQLite database. No Sheets updates or publish grants.
-- This is an append-only reconciliation journal, NOT a Sheets transaction.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sns_media_review_queue_bindings (
    account_id TEXT NOT NULL,
    slot_id TEXT NOT NULL,
    queue_id TEXT NOT NULL,
    queue_revision TEXT NOT NULL,
    queue_sha256 TEXT NOT NULL,
    context_sha256 TEXT NOT NULL,
    ledger_version INTEGER NOT NULL CHECK (ledger_version > 0),
    ledger_event_sha256 TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN (
        'REVIEW_RECORDED_BLOCKED','REVOKED_BLOCKED','DRIFT_QUARANTINED'
    )),
    reconciliation_state TEXT NOT NULL CHECK (reconciliation_state IN (
        'PENDING','MATCHED_BLOCKED','CONFLICT_BLOCKED'
    )),
    binding_version INTEGER NOT NULL CHECK (binding_version > 0),
    last_event_sha256 TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (account_id, slot_id, queue_id),
    FOREIGN KEY (account_id, slot_id, queue_id)
        REFERENCES sns_media_review_heads(account_id, slot_id, queue_id)
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS sns_media_review_queue_reconciliation_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id TEXT NOT NULL UNIQUE,
    account_id TEXT NOT NULL,
    slot_id TEXT NOT NULL,
    queue_id TEXT NOT NULL,
    binding_version INTEGER NOT NULL CHECK (binding_version > 0),
    action TEXT NOT NULL CHECK (action IN (
        'REVIEW_BOUND','REVIEW_REVOKED','SOURCE_MATCH',
        'SOURCE_DRIFT','SOURCE_UNAVAILABLE'
    )),
    previous_event_sha256 TEXT NOT NULL,
    event_sha256 TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL,
    UNIQUE (account_id, slot_id, queue_id, binding_version),
    FOREIGN KEY (account_id, slot_id, queue_id)
        REFERENCES sns_media_review_queue_bindings(account_id, slot_id, queue_id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_sns_review_reconcile_history
    ON sns_media_review_queue_reconciliation_events
        (account_id,slot_id,queue_id,binding_version);

CREATE TRIGGER IF NOT EXISTS trg_sns_review_reconcile_event_no_update
BEFORE UPDATE ON sns_media_review_queue_reconciliation_events
BEGIN
    SELECT RAISE(ABORT,'reconciliation_append_only');
END;
CREATE TRIGGER IF NOT EXISTS trg_sns_review_reconcile_event_no_delete
BEFORE DELETE ON sns_media_review_queue_reconciliation_events
BEGIN
    SELECT RAISE(ABORT,'reconciliation_append_only');
END;
CREATE TRIGGER IF NOT EXISTS trg_sns_review_queue_binding_no_delete
BEFORE DELETE ON sns_media_review_queue_bindings
BEGIN
    SELECT RAISE(ABORT,'review_binding_delete_forbidden');
END;
