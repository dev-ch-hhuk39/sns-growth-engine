-- Phase 5B-6J: opt-in isolated reporting-Sheet delivery, never SNS posting.
-- Requires migrations 0001-0009. Apply only via approved ops process.
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS sns_mirror_delivery_sessions (
  session_id TEXT PRIMARY KEY,
  subject TEXT NOT NULL,
  issuer TEXT NOT NULL,
  token_sha256 TEXT NOT NULL,
  token_jti TEXT NOT NULL,
  issued_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL CHECK(expires_at > issued_at),
  revoked_at INTEGER,
  enabled INTEGER NOT NULL CHECK(enabled IN (0,1)) DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sns_mirror_delivery_destinations (
  destination_id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL,
  service_subject TEXT NOT NULL,
  reporting_spreadsheet_id TEXT NOT NULL,
  operational_spreadsheet_id TEXT NOT NULL,
  reporting_tab TEXT NOT NULL,
  mode TEXT NOT NULL CHECK(mode='ISOLATED_REPORTING_ONLY'),
  enabled INTEGER NOT NULL CHECK(enabled IN (0,1)) DEFAULT 0,
  CHECK(reporting_spreadsheet_id <> operational_spreadsheet_id),
  UNIQUE(account_id,destination_id)
);
-- Rows are provisioned manually; never append a row or infer from client data.
CREATE TABLE IF NOT EXISTS sns_mirror_delivery_row_map (
  destination_id TEXT NOT NULL,
  account_id TEXT NOT NULL,
  slot_id TEXT NOT NULL,
  queue_id TEXT NOT NULL,
  row_number INTEGER NOT NULL CHECK(row_number BETWEEN 2 AND 10000),
  PRIMARY KEY(destination_id,account_id,slot_id,queue_id),
  UNIQUE(destination_id,row_number),
  FOREIGN KEY(account_id,destination_id)
    REFERENCES sns_mirror_delivery_destinations(account_id,destination_id)
    ON DELETE RESTRICT
);
CREATE TABLE IF NOT EXISTS sns_mirror_delivery_heads (
  event_sha256 TEXT NOT NULL,
  destination_id TEXT NOT NULL,
  account_id TEXT NOT NULL,
  row_number INTEGER NOT NULL CHECK(row_number BETWEEN 2 AND 10000),
  version INTEGER NOT NULL CHECK(version BETWEEN 1 AND 4),
  state TEXT NOT NULL CHECK(state IN (
    'PREPARED_BLOCKED','READBACK_VERIFIED_BLOCKED',
    'OUTCOME_UNKNOWN_BLOCKED','RECONCILED_BLOCKED','CONFLICT_BLOCKED'
  )),
  projection_sha256 TEXT NOT NULL,
  last_event_sha256 TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(event_sha256,destination_id),
  FOREIGN KEY(event_sha256) REFERENCES sns_media_mirror_outbox_heads(event_sha256)
    ON DELETE RESTRICT,
  FOREIGN KEY(account_id,destination_id)
    REFERENCES sns_mirror_delivery_destinations(account_id,destination_id)
    ON DELETE RESTRICT
);
CREATE TABLE IF NOT EXISTS sns_mirror_delivery_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  operation_id TEXT NOT NULL UNIQUE,
  event_sha256 TEXT NOT NULL,
  destination_id TEXT NOT NULL,
  version INTEGER NOT NULL CHECK(version BETWEEN 1 AND 4),
  action TEXT NOT NULL CHECK(action IN (
    'PREPARE','READBACK_VERIFIED','OUTCOME_UNKNOWN','RECONCILE','CONFLICT'
  )),
  previous_event_sha256 TEXT NOT NULL,
  audit_sha256 TEXT NOT NULL UNIQUE,
  payload_json TEXT NOT NULL,
  UNIQUE(event_sha256,destination_id,version),
  FOREIGN KEY(event_sha256,destination_id)
    REFERENCES sns_mirror_delivery_heads(event_sha256,destination_id)
    ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_mirror_delivery_row
  ON sns_mirror_delivery_heads(destination_id,row_number);
CREATE TRIGGER IF NOT EXISTS trg_mirror_delivery_events_immutable_update
  BEFORE UPDATE ON sns_mirror_delivery_events
  BEGIN SELECT RAISE(ABORT,'mirror_delivery_event_append_only'); END;
CREATE TRIGGER IF NOT EXISTS trg_mirror_delivery_events_immutable_delete
  BEFORE DELETE ON sns_mirror_delivery_events
  BEGIN SELECT RAISE(ABORT,'mirror_delivery_event_append_only'); END;
CREATE TRIGGER IF NOT EXISTS trg_mirror_delivery_heads_no_delete
  BEFORE DELETE ON sns_mirror_delivery_heads
  BEGIN SELECT RAISE(ABORT,'mirror_delivery_head_delete_forbidden'); END;
CREATE TRIGGER IF NOT EXISTS trg_mirror_delivery_row_map_no_update
  BEFORE UPDATE ON sns_mirror_delivery_row_map
  BEGIN SELECT RAISE(ABORT,'mirror_delivery_mapping_immutable'); END;
CREATE TRIGGER IF NOT EXISTS trg_mirror_delivery_row_map_no_delete
  BEFORE DELETE ON sns_mirror_delivery_row_map
  BEGIN SELECT RAISE(ABORT,'mirror_delivery_mapping_immutable'); END;
