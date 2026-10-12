-- Phase 5B-6B: offline, non-authorizing intent reservation + audit.
-- Does NOT confer a real publish permit. Never write external Sheets/READY.
-- Provision ONLY on a dedicated private review database after migrations 1-3.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sns_media_publish_intent_heads (
    account_id TEXT NOT NULL,
    slot_id TEXT NOT NULL,
    queue_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1 AND version <= 128),
    state TEXT NOT NULL CHECK (state IN (
        'HELD_BLOCKED', 'CANCELLED_BLOCKED', 'QUARANTINED_BLOCKED'
    )),
    queue_sha256 TEXT NOT NULL,
    context_sha256 TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    media_asset_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    review_version INTEGER NOT NULL,
    review_event_sha256 TEXT NOT NULL,
    binding_version INTEGER NOT NULL,
    binding_event_sha256 TEXT NOT NULL,
    held_until TEXT NOT NULL,
    last_event_sha256 TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (account_id, slot_id, queue_id),
    -- Conservative anti-repost: one physical asset OR one caption per account
    -- can ever be reserved by this ledger; cancellation does not release it.
    UNIQUE (account_id, media_asset_id),
    UNIQUE (account_id, content_sha256),
    FOREIGN KEY (account_id, slot_id, queue_id)
       REFERENCES sns_media_review_heads(account_id, slot_id, queue_id)
       ON DELETE RESTRICT
);
CREATE TABLE IF NOT EXISTS sns_media_publish_intent_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id TEXT NOT NULL UNIQUE,
    account_id TEXT NOT NULL,
    slot_id TEXT NOT NULL,
    queue_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1 AND version <= 128),
    action TEXT NOT NULL CHECK (action IN ('HOLD','CANCEL','QUARANTINE')),
    previous_event_sha256 TEXT NOT NULL,
    event_sha256 TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL,
    UNIQUE (account_id, slot_id, queue_id, version),
    FOREIGN KEY (account_id, slot_id, queue_id)
       REFERENCES sns_media_publish_intent_heads(account_id, slot_id, queue_id)
       ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_sns_media_publish_intent_history
 ON sns_media_publish_intent_events
    (account_id, slot_id, queue_id, version);

CREATE TRIGGER IF NOT EXISTS trg_sns_media_publish_intent_events_immutable_update
BEFORE UPDATE ON sns_media_publish_intent_events
BEGIN
    SELECT RAISE(ABORT, 'publish_intent_event_append_only');
END;
CREATE TRIGGER IF NOT EXISTS trg_sns_media_publish_intent_events_immutable_delete
BEFORE DELETE ON sns_media_publish_intent_events
BEGIN
    SELECT RAISE(ABORT, 'publish_intent_event_append_only');
END;
CREATE TRIGGER IF NOT EXISTS trg_sns_media_publish_intent_heads_no_delete
BEFORE DELETE ON sns_media_publish_intent_heads
BEGIN
    SELECT RAISE(ABORT, 'publish_intent_head_delete_forbidden');
END;
