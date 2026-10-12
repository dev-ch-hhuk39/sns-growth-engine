-- Phase 5B-6I: isolated service identity & OFFLINE-only reporting replica rehearsal.
-- Requires schema 0001-0008. No Google API, real Sheets writes, SNS publishing.
PRAGMA foreign_keys=ON;

-- Must be provisioned by independent trusted operations; request paths read only.
CREATE TABLE IF NOT EXISTS sns_mirror_rehearsal_service_sessions (
  session_id TEXT PRIMARY KEY,
  subject TEXT NOT NULL,
  issuer TEXT NOT NULL,
  token_sha256 TEXT NOT NULL,
  token_jti TEXT NOT NULL,
  issued_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL CHECK(expires_at > issued_at),
  revoked_at INTEGER,
  enabled INTEGER NOT NULL CHECK(enabled IN (0,1))
);
CREATE TABLE IF NOT EXISTS sns_mirror_rehearsal_destinations (
  destination_id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL,
  service_subject TEXT NOT NULL,
  reporting_spreadsheet_id TEXT NOT NULL,
  operational_spreadsheet_id TEXT NOT NULL,
  reporting_tab TEXT NOT NULL,
  mode TEXT NOT NULL CHECK(mode='ISOLATED_REPORTING_ONLY'),
  enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
  CHECK(reporting_spreadsheet_id <> operational_spreadsheet_id),
  UNIQUE(account_id,destination_id)
);
CREATE TABLE IF NOT EXISTS sns_mirror_rehearsal_heads (
  event_sha256 TEXT NOT NULL,
  destination_id TEXT NOT NULL,
  account_id TEXT NOT NULL,
  version INTEGER NOT NULL CHECK(version BETWEEN 1 AND 8),
  state TEXT NOT NULL CHECK(state IN (
    'PREPARED_BLOCKED','SIMULATED_READBACK_BLOCKED',
    'OUTCOME_UNKNOWN_BLOCKED','SIMULATED_RECONCILED_BLOCKED',
    'CONFLICT_BLOCKED'
  )),
  projection_sha256 TEXT NOT NULL,
  last_event_sha256 TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(event_sha256,destination_id),
  FOREIGN KEY(event_sha256) REFERENCES sns_media_mirror_outbox_heads(event_sha256)
    ON DELETE RESTRICT,
  FOREIGN KEY(account_id,destination_id) REFERENCES sns_mirror_rehearsal_destinations(account_id,destination_id)
    ON DELETE RESTRICT
);
CREATE TABLE IF NOT EXISTS sns_mirror_rehearsal_events (
  event_id INTEGER PRIMARY KEY AUTOINCREMENT,
  operation_id TEXT NOT NULL UNIQUE,
  event_sha256 TEXT NOT NULL,
  destination_id TEXT NOT NULL,
  version INTEGER NOT NULL CHECK(version BETWEEN 1 AND 8),
  action TEXT NOT NULL CHECK(action IN (
    'PREPARE','SIMULATED_READBACK','OUTCOME_UNKNOWN',
    'READ_ONLY_RECONCILE','CONFLICT'
  )),
  previous_event_sha256 TEXT NOT NULL,
  audit_sha256 TEXT NOT NULL UNIQUE,
  payload_json TEXT NOT NULL,
  UNIQUE(event_sha256,destination_id,version),
  FOREIGN KEY(event_sha256,destination_id)
    REFERENCES sns_mirror_rehearsal_heads(event_sha256,destination_id)
    ON DELETE RESTRICT
);
CREATE TRIGGER IF NOT EXISTS trg_sns_mirror_rehearsal_events_no_update
 BEFORE UPDATE ON sns_mirror_rehearsal_events
 BEGIN SELECT RAISE(ABORT,'mirror_rehearsal_event_append_only'); END;
CREATE TRIGGER IF NOT EXISTS trg_sns_mirror_rehearsal_events_no_delete
 BEFORE DELETE ON sns_mirror_rehearsal_events
 BEGIN SELECT RAISE(ABORT,'mirror_rehearsal_event_append_only'); END;
CREATE TRIGGER IF NOT EXISTS trg_sns_mirror_rehearsal_heads_no_delete
 BEFORE DELETE ON sns_mirror_rehearsal_heads
 BEGIN SELECT RAISE(ABORT,'mirror_rehearsal_head_delete_forbidden'); END;
