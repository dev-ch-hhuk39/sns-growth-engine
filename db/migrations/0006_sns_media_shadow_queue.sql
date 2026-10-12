-- Phase 5B-6E: SHADOW canonical queue snapshots, not a publish source of truth.
-- Requires protected review migrations 0001-0005. Only a trusted backend may
-- seed this table. Production Sheets remains independent and unmodified.
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS sns_media_shadow_queue_heads (
    account_id TEXT NOT NULL,
    slot_id TEXT NOT NULL,
    queue_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK(version BETWEEN 1 AND 512),
    state TEXT NOT NULL CHECK(state IN (
        'SHADOW_BLOCKED', 'CONFLICT_BLOCKED', 'SOURCE_UNAVAILABLE_BLOCKED'
    )),
    queue_revision TEXT NOT NULL,
    queue_sha256 TEXT NOT NULL,
    context_sha256 TEXT NOT NULL,
    snapshot_sha256 TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    last_event_sha256 TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(account_id,slot_id,queue_id)
);
CREATE TABLE IF NOT EXISTS sns_media_shadow_queue_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id TEXT NOT NULL UNIQUE,
    account_id TEXT NOT NULL,
    slot_id TEXT NOT NULL,
    queue_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK(version BETWEEN 1 AND 512),
    action TEXT NOT NULL CHECK(action IN (
        'IMPORT','REFRESH','OBSERVE','DRIFT','SOURCE_LOST'
    )),
    previous_event_sha256 TEXT NOT NULL,
    event_sha256 TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL,
    UNIQUE(account_id,slot_id,queue_id,version),
    FOREIGN KEY(account_id,slot_id,queue_id)
      REFERENCES sns_media_shadow_queue_heads(account_id,slot_id,queue_id)
      ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_sns_shadow_queue_history
  ON sns_media_shadow_queue_events(account_id,slot_id,queue_id,version);
CREATE TRIGGER IF NOT EXISTS trg_sns_shadow_queue_events_immutable_update
  BEFORE UPDATE ON sns_media_shadow_queue_events
  BEGIN SELECT RAISE(ABORT,'shadow_queue_event_append_only'); END;
CREATE TRIGGER IF NOT EXISTS trg_sns_shadow_queue_events_immutable_delete
  BEFORE DELETE ON sns_media_shadow_queue_events
  BEGIN SELECT RAISE(ABORT,'shadow_queue_event_append_only'); END;
CREATE TRIGGER IF NOT EXISTS trg_sns_shadow_queue_heads_no_delete
  BEFORE DELETE ON sns_media_shadow_queue_heads
  BEGIN SELECT RAISE(ABORT,'shadow_queue_head_delete_forbidden'); END;
