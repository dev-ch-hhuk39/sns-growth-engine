-- Phase 5B-5A: isolated, non-publishing review ledger.
-- Apply only through an approved database migration in a protected environment.
-- The database does NOT own the Google Sheets posting queue; no READY writes.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sns_media_review_heads (
    account_id TEXT NOT NULL,
    slot_id TEXT NOT NULL,
    queue_id TEXT NOT NULL,
    ledger_version INTEGER NOT NULL DEFAULT 0 CHECK (ledger_version >= 0),
    review_state TEXT NOT NULL DEFAULT 'NONE'
        CHECK (review_state IN ('NONE','REVIEW_RECORDED_ONLY','REVOKED')),
    last_event_sha256 TEXT NOT NULL DEFAULT
        '0000000000000000000000000000000000000000000000000000000000000000',
    last_draft_event_sha256 TEXT NOT NULL DEFAULT '',
    last_queue_revision TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (account_id, slot_id, queue_id)
);

CREATE TABLE IF NOT EXISTS sns_media_review_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id TEXT NOT NULL UNIQUE,
    account_id TEXT NOT NULL,
    slot_id TEXT NOT NULL,
    queue_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence > 0),
    action TEXT NOT NULL CHECK (action IN ('REVIEW_RECORD','REVOKE')),
    previous_event_sha256 TEXT NOT NULL,
    event_sha256 TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL,
    UNIQUE (account_id, slot_id, queue_id, sequence),
    FOREIGN KEY (account_id, slot_id, queue_id)
        REFERENCES sns_media_review_heads(account_id, slot_id, queue_id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_sns_media_review_events_candidate
  ON sns_media_review_events(account_id,slot_id,queue_id,sequence);

-- These triggers prevent accidental rewrites from ordinary application code.
-- They do not substitute for OS/DB access control or external hash anchoring.
CREATE TRIGGER IF NOT EXISTS trg_sns_media_review_event_no_update
BEFORE UPDATE ON sns_media_review_events
BEGIN
    SELECT RAISE(ABORT, 'review_event_append_only');
END;

CREATE TRIGGER IF NOT EXISTS trg_sns_media_review_event_no_delete
BEFORE DELETE ON sns_media_review_events
BEGIN
    SELECT RAISE(ABORT, 'review_event_append_only');
END;

CREATE TRIGGER IF NOT EXISTS trg_sns_media_review_head_no_delete
BEFORE DELETE ON sns_media_review_heads
BEGIN
    SELECT RAISE(ABORT, 'review_head_delete_forbidden');
END;
