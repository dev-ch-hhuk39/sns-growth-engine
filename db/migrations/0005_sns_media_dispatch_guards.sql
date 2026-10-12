-- Phase 5B-6C: local SQLite media dispatch staging; NO SNS publishing.
-- The remote Sheets queue is not held by this transaction.
-- All states remain BLOCKED. Apply offline after review migrations 1-4.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sns_media_dispatch_heads (
    account_id TEXT NOT NULL,
    slot_id TEXT NOT NULL,
    queue_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version BETWEEN 1 AND 64),
    state TEXT NOT NULL CHECK (state IN (
        'STAGED_BLOCKED','CANCELLED_BLOCKED','DRIFT_BLOCKED',
        'OUTCOME_UNCERTAIN_BLOCKED'
    )),
    intent_version INTEGER NOT NULL,
    intent_event_sha256 TEXT NOT NULL,
    queue_sha256 TEXT NOT NULL,
    context_sha256 TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    media_asset_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    staged_until TEXT NOT NULL,
    last_event_sha256 TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(account_id,slot_id,queue_id),
    UNIQUE(account_id,media_asset_id),
    UNIQUE(account_id,content_sha256),
    FOREIGN KEY (account_id,slot_id,queue_id)
      REFERENCES sns_media_publish_intent_heads(account_id,slot_id,queue_id)
      ON DELETE RESTRICT
);
CREATE TABLE IF NOT EXISTS sns_media_dispatch_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id TEXT NOT NULL UNIQUE,
    account_id TEXT NOT NULL,
    slot_id TEXT NOT NULL,
    queue_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version BETWEEN 1 AND 64),
    action TEXT NOT NULL CHECK (action IN (
        'STAGE','CANCEL','QUARANTINE','MARK_UNCERTAIN'
    )),
    previous_event_sha256 TEXT NOT NULL,
    event_sha256 TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL,
    UNIQUE(account_id,slot_id,queue_id,version),
    FOREIGN KEY(account_id,slot_id,queue_id)
      REFERENCES sns_media_dispatch_heads(account_id,slot_id,queue_id)
      ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_sns_media_dispatch_history
 ON sns_media_dispatch_events(account_id,slot_id,queue_id,version);
CREATE TRIGGER IF NOT EXISTS trg_sns_media_dispatch_events_no_update
 BEFORE UPDATE ON sns_media_dispatch_events
 BEGIN SELECT RAISE(ABORT, 'dispatch_event_append_only'); END;
CREATE TRIGGER IF NOT EXISTS trg_sns_media_dispatch_events_no_delete
 BEFORE DELETE ON sns_media_dispatch_events
 BEGIN SELECT RAISE(ABORT, 'dispatch_event_append_only'); END;
CREATE TRIGGER IF NOT EXISTS trg_sns_media_dispatch_heads_no_delete
 BEFORE DELETE ON sns_media_dispatch_heads
 BEGIN SELECT RAISE(ABORT, 'dispatch_head_delete_forbidden'); END;
