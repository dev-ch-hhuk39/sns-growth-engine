-- P0 offline rehearsal only. This schema cannot authorize real SNS posting.
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS sns_p0_rehearsal_heads (
    queue_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL CHECK(account_id IN ('night_scout','liver_manager')),
    platform TEXT NOT NULL CHECK(platform='threads'),
    source_sha256 TEXT NOT NULL CHECK(length(source_sha256)=64),
    observed_at TEXT NOT NULL,
    version INTEGER NOT NULL CHECK(version BETWEEN 1 AND 4),
    state TEXT NOT NULL CHECK(state IN (
        'OBSERVED_BLOCKED','CLAIMED_BLOCKED',
        'OUTCOME_UNKNOWN_BLOCKED','CANCELLED_BLOCKED'
    )),
    last_event_sha256 TEXT NOT NULL CHECK(length(last_event_sha256)=64),
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sns_p0_rehearsal_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id TEXT NOT NULL UNIQUE,
    queue_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK(version BETWEEN 1 AND 4),
    action TEXT NOT NULL CHECK(action IN ('OBSERVE','CLAIM','UNCERTAIN','CANCEL')),
    previous_event_sha256 TEXT NOT NULL,
    event_sha256 TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL,
    UNIQUE(queue_id,version),
    FOREIGN KEY(queue_id) REFERENCES sns_p0_rehearsal_heads(queue_id)
      ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_sns_p0_rehearsal_history
 ON sns_p0_rehearsal_events(queue_id,version);
CREATE TRIGGER IF NOT EXISTS sns_p0_rehearsal_event_no_update
 BEFORE UPDATE ON sns_p0_rehearsal_events
 BEGIN SELECT RAISE(ABORT,'p0_rehearsal_event_immutable'); END;
CREATE TRIGGER IF NOT EXISTS sns_p0_rehearsal_event_no_delete
 BEFORE DELETE ON sns_p0_rehearsal_events
 BEGIN SELECT RAISE(ABORT,'p0_rehearsal_event_immutable'); END;
CREATE TRIGGER IF NOT EXISTS sns_p0_rehearsal_head_no_delete
 BEFORE DELETE ON sns_p0_rehearsal_heads
 BEGIN SELECT RAISE(ABORT,'p0_rehearsal_head_immutable'); END;
