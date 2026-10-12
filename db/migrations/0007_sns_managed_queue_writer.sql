-- Phase 5B-6F: safe SQLite queue command authority and read-only mirror plan.
-- This DOES NOT migrate Google Sheets or make media publishing authorized.
-- Install only after migrations 0001-0006 on an approved private DB.
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS sns_media_managed_queue_heads (
 account_id TEXT NOT NULL, slot_id TEXT NOT NULL, queue_id TEXT NOT NULL,
 version INTEGER NOT NULL CHECK(version BETWEEN 1 AND 128),
 state TEXT NOT NULL CHECK(state IN (
  'MANAGED_BLOCKED','HOLD_BLOCKED','ARCHIVED_BLOCKED','CONFLICT_BLOCKED')),
 shadow_version INTEGER NOT NULL,
 shadow_event_sha256 TEXT NOT NULL,
 queue_sha256 TEXT NOT NULL,
 last_event_sha256 TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 PRIMARY KEY(account_id,slot_id,queue_id),
 FOREIGN KEY(account_id,slot_id,queue_id)
  REFERENCES sns_media_shadow_queue_heads(account_id,slot_id,queue_id)
  ON DELETE RESTRICT
);
CREATE TABLE IF NOT EXISTS sns_media_managed_queue_events (
 event_id INTEGER PRIMARY KEY AUTOINCREMENT,
 operation_id TEXT NOT NULL UNIQUE,
 account_id TEXT NOT NULL, slot_id TEXT NOT NULL, queue_id TEXT NOT NULL,
 version INTEGER NOT NULL CHECK(version BETWEEN 1 AND 128),
 action TEXT NOT NULL CHECK(action IN ('BIND','RECONCILE','HOLD','ARCHIVE','QUARANTINE')),
 previous_event_sha256 TEXT NOT NULL,
 event_sha256 TEXT NOT NULL UNIQUE,
 payload_json TEXT NOT NULL,
 UNIQUE(account_id,slot_id,queue_id,version),
 FOREIGN KEY(account_id,slot_id,queue_id)
  REFERENCES sns_media_managed_queue_heads(account_id,slot_id,queue_id)
  ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_managed_queue_events
 ON sns_media_managed_queue_events(account_id,slot_id,queue_id,version);
CREATE TABLE IF NOT EXISTS sns_media_sheet_mirror_previews (
 event_sha256 TEXT PRIMARY KEY,
 account_id TEXT NOT NULL, slot_id TEXT NOT NULL, queue_id TEXT NOT NULL,
 writer_version INTEGER NOT NULL,
 projection_sha256 TEXT NOT NULL,
 projection_json TEXT NOT NULL,
 FOREIGN KEY(account_id,slot_id,queue_id)
  REFERENCES sns_media_managed_queue_heads(account_id,slot_id,queue_id)
  ON DELETE RESTRICT,
 UNIQUE(account_id,slot_id,queue_id,writer_version)
);
CREATE INDEX IF NOT EXISTS idx_managed_queue_mirror_previews
 ON sns_media_sheet_mirror_previews(account_id,slot_id,queue_id,writer_version);

CREATE TRIGGER IF NOT EXISTS trg_managed_queue_events_update
 BEFORE UPDATE ON sns_media_managed_queue_events
 BEGIN SELECT RAISE(ABORT,'managed_queue_event_append_only'); END;
CREATE TRIGGER IF NOT EXISTS trg_managed_queue_events_delete
 BEFORE DELETE ON sns_media_managed_queue_events
 BEGIN SELECT RAISE(ABORT,'managed_queue_event_append_only'); END;
CREATE TRIGGER IF NOT EXISTS trg_managed_queue_mirror_update
 BEFORE UPDATE ON sns_media_sheet_mirror_previews
 BEGIN SELECT RAISE(ABORT,'managed_queue_mirror_immutable'); END;
CREATE TRIGGER IF NOT EXISTS trg_managed_queue_mirror_delete
 BEFORE DELETE ON sns_media_sheet_mirror_previews
 BEGIN SELECT RAISE(ABORT,'managed_queue_mirror_immutable'); END;
CREATE TRIGGER IF NOT EXISTS trg_managed_queue_head_delete
 BEFORE DELETE ON sns_media_managed_queue_heads
 BEGIN SELECT RAISE(ABORT,'managed_queue_head_delete_forbidden'); END;
