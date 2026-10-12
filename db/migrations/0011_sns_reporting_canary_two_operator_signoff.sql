-- Phase 5B-6N: independent two-operator canary approval replay journal.
-- Requires migrations 0001-0010. Never apply to shared VPS in dev chat.
-- Only trusted, separately pinned operator signing keys may approve a PUT.
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS sns_mirror_canary_signoff_uses (
  signer_jti TEXT NOT NULL PRIMARY KEY,
  signer_kid TEXT NOT NULL,
  signer_subject TEXT NOT NULL,
  signed_token_sha256 TEXT NOT NULL UNIQUE,
  event_sha256 TEXT NOT NULL,
  destination_id TEXT NOT NULL,
  account_id TEXT NOT NULL,
  row_number INTEGER NOT NULL CHECK(row_number BETWEEN 2 AND 10000),
  projection_sha256 TEXT NOT NULL CHECK(length(projection_sha256)=64),
  operation_id TEXT NOT NULL,
  operator_slot INTEGER NOT NULL CHECK(operator_slot IN (1,2)),
  consumed_at INTEGER NOT NULL,
  UNIQUE(operation_id,operator_slot),
  UNIQUE(event_sha256,destination_id,operator_slot),
  FOREIGN KEY(event_sha256) REFERENCES sns_media_mirror_outbox_heads(event_sha256)
    ON DELETE RESTRICT,
  FOREIGN KEY(account_id,destination_id)
    REFERENCES sns_mirror_delivery_destinations(account_id,destination_id)
    ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_mirror_canary_signoffs_by_destination
  ON sns_mirror_canary_signoff_uses(destination_id,event_sha256);
CREATE TRIGGER IF NOT EXISTS trg_sns_mirror_canary_signoffs_no_update
  BEFORE UPDATE ON sns_mirror_canary_signoff_uses
  BEGIN SELECT RAISE(ABORT,'canary_approval_use_append_only'); END;
CREATE TRIGGER IF NOT EXISTS trg_sns_mirror_canary_signoffs_no_delete
  BEFORE DELETE ON sns_mirror_canary_signoff_uses
  BEGIN SELECT RAISE(ABORT,'canary_approval_use_append_only'); END;
