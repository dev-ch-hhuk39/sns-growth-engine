-- Phase 5B-6G: local, non-authorizing mirror outbox. 0001-0007 first.
-- No external Google Sheets mutation, API credentials, or SNS publish permit.
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS sns_media_mirror_outbox_heads (
    event_sha256 TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    slot_id TEXT NOT NULL,
    queue_id TEXT NOT NULL,
    writer_version INTEGER NOT NULL,
    projection_sha256 TEXT NOT NULL,
    version INTEGER NOT NULL CHECK(version BETWEEN 1 AND 64),
    state TEXT NOT NULL CHECK(state IN (
        'QUEUED_BLOCKED','CLAIMED_BLOCKED',
        'UNCERTAIN_BLOCKED','SUPERSEDED_BLOCKED','CANCELLED_BLOCKED'
    )),
    lease_expires_at TEXT,
    last_event_sha256 TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(event_sha256) REFERENCES sns_media_sheet_mirror_previews(event_sha256)
      ON DELETE RESTRICT,
    UNIQUE(account_id,slot_id,queue_id,writer_version)
);
CREATE INDEX IF NOT EXISTS idx_sns_mirror_outbox_candidate
 ON sns_media_mirror_outbox_heads(account_id,slot_id,queue_id,writer_version);
CREATE TABLE IF NOT EXISTS sns_media_mirror_outbox_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id TEXT NOT NULL UNIQUE,
    event_sha256 TEXT NOT NULL,
    version INTEGER NOT NULL CHECK(version BETWEEN 1 AND 64),
    action TEXT NOT NULL CHECK(action IN (
        'ENQUEUE','CLAIM','UNCERTAIN','SUPERSEDE','CANCEL'
    )),
    previous_event_sha256 TEXT NOT NULL,
    journal_sha256 TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL,
    UNIQUE(event_sha256,version),
    FOREIGN KEY(event_sha256) REFERENCES sns_media_mirror_outbox_heads(event_sha256)
       ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_sns_mirror_outbox_history
 ON sns_media_mirror_outbox_events(event_sha256,version);
CREATE TRIGGER IF NOT EXISTS trg_sns_mirror_outbox_events_immutable_update
BEFORE UPDATE ON sns_media_mirror_outbox_events
BEGIN SELECT RAISE(ABORT,'mirror_outbox_event_append_only'); END;
CREATE TRIGGER IF NOT EXISTS trg_sns_mirror_outbox_events_immutable_delete
BEFORE DELETE ON sns_media_mirror_outbox_events
BEGIN SELECT RAISE(ABORT,'mirror_outbox_event_append_only'); END;
CREATE TRIGGER IF NOT EXISTS trg_sns_mirror_outbox_heads_no_delete
BEFORE DELETE ON sns_media_mirror_outbox_heads
BEGIN SELECT RAISE(ABORT,'mirror_outbox_head_delete_forbidden'); END;
