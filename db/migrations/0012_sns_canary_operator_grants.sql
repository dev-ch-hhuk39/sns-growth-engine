-- Phase 5B-6O: deny-by-default, server-provisioned human canary grants.
-- Requires 0001-0011. Source development only; no live database migration.
-- Only the dedicated privileged operations process may insert/update grants.
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS sns_mirror_canary_operator_grants (
  signer_kid TEXT NOT NULL,
  signer_subject TEXT NOT NULL,
  account_id TEXT NOT NULL,
  destination_id TEXT NOT NULL,
  approval_slot INTEGER NOT NULL CHECK(approval_slot IN (1,2)),
  grant_generation INTEGER NOT NULL CHECK(
    grant_generation >= 1 AND grant_generation <= 2147483647
  ),
  valid_from INTEGER NOT NULL,
  valid_until INTEGER NOT NULL CHECK(valid_until > valid_from),
  enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
  revoked_at INTEGER,
  provisioned_by TEXT NOT NULL CHECK(length(provisioned_by) >= 5),
  PRIMARY KEY(signer_kid,account_id,destination_id,approval_slot),
  UNIQUE(signer_subject,account_id,destination_id,approval_slot),
  FOREIGN KEY(account_id,destination_id)
    REFERENCES sns_mirror_delivery_destinations(account_id,destination_id)
    ON DELETE RESTRICT
);

-- Never silently swap the allowed signer or widen an existing grant scope.
CREATE TRIGGER IF NOT EXISTS trg_canary_grant_scope_immutable
  BEFORE UPDATE ON sns_mirror_canary_operator_grants
  WHEN NEW.signer_kid != OLD.signer_kid
    OR NEW.signer_subject != OLD.signer_subject
    OR NEW.account_id != OLD.account_id
    OR NEW.destination_id != OLD.destination_id
    OR NEW.approval_slot != OLD.approval_slot
    OR NEW.provisioned_by != OLD.provisioned_by
  BEGIN SELECT RAISE(ABORT,'canary_grant_scope_immutable'); END;

-- Any disabled or revoked grant needs a new generation on reactivation.
-- Old signed JWTs remain invalid even after an operator is re-authorized.
CREATE TRIGGER IF NOT EXISTS trg_canary_grant_generation_monotonic
  BEFORE UPDATE ON sns_mirror_canary_operator_grants
  WHEN NEW.grant_generation < OLD.grant_generation
    OR (OLD.enabled=0 AND NEW.enabled=1
        AND NEW.grant_generation <= OLD.grant_generation)
    OR (OLD.revoked_at IS NOT NULL AND NEW.revoked_at IS NULL
        AND NEW.grant_generation <= OLD.grant_generation)
  BEGIN SELECT RAISE(ABORT,'canary_grant_generation_not_advanced'); END;

CREATE TRIGGER IF NOT EXISTS trg_canary_grant_no_delete
  BEFORE DELETE ON sns_mirror_canary_operator_grants
  BEGIN SELECT RAISE(ABORT,'canary_grant_delete_forbidden'); END;
