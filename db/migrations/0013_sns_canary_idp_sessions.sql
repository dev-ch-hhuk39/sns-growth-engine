-- Phase 5B-6P: independent authenticated IdP session proof for operator canary.
-- Requires 0001-0012. NOT applied to production from this development chat.
-- An independent trusted IdP callback must authenticate/provision session.
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS sns_mirror_canary_idp_sessions (
  session_id TEXT PRIMARY KEY,
  subject TEXT NOT NULL,
  issuer TEXT NOT NULL CHECK(length(issuer) BETWEEN 12 AND 255),
  signer_kid TEXT NOT NULL,
  token_jti TEXT NOT NULL UNIQUE,
  assertion_sha256 TEXT NOT NULL UNIQUE CHECK(length(assertion_sha256)=64),
  authenticated_at INTEGER NOT NULL CHECK(authenticated_at > 0),
  mfa_at INTEGER NOT NULL CHECK(mfa_at >= authenticated_at),
  issued_at INTEGER NOT NULL CHECK(issued_at >= mfa_at - 30),
  expires_at INTEGER NOT NULL CHECK(
    expires_at > issued_at AND expires_at - issued_at <= 300
  ),
  authentication_profile TEXT NOT NULL
    CHECK(authentication_profile='PHISHING_RESISTANT_MFA'),
  enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
  revoked_at INTEGER,
  provisioned_by TEXT NOT NULL CHECK(length(provisioned_by) >= 8)
);
CREATE INDEX IF NOT EXISTS idx_sns_canary_idp_by_subject
  ON sns_mirror_canary_idp_sessions(subject);

CREATE TRIGGER IF NOT EXISTS trg_sns_canary_idp_session_fixed_fields
  BEFORE UPDATE ON sns_mirror_canary_idp_sessions
  WHEN NEW.session_id != OLD.session_id
    OR NEW.subject != OLD.subject
    OR NEW.issuer != OLD.issuer
    OR NEW.signer_kid != OLD.signer_kid
    OR NEW.token_jti != OLD.token_jti
    OR NEW.assertion_sha256 != OLD.assertion_sha256
    OR NEW.authenticated_at != OLD.authenticated_at
    OR NEW.mfa_at != OLD.mfa_at
    OR NEW.issued_at != OLD.issued_at
    OR NEW.expires_at != OLD.expires_at
    OR NEW.authentication_profile != OLD.authentication_profile
    OR NEW.provisioned_by != OLD.provisioned_by
  BEGIN SELECT RAISE(ABORT,'canary_idp_session_immutable'); END;

-- Disabled/revoked sessions are terminal, not reactivated with the same
-- token hash. A future independent session must use a fresh sid/jti/token.
CREATE TRIGGER IF NOT EXISTS trg_sns_canary_idp_session_no_reactivation
  BEFORE UPDATE ON sns_mirror_canary_idp_sessions
  WHEN (OLD.enabled=0 AND NEW.enabled=1)
    OR (OLD.revoked_at IS NOT NULL AND NEW.revoked_at IS NULL)
  BEGIN SELECT RAISE(ABORT,'canary_idp_session_reactivation_forbidden'); END;
CREATE TRIGGER IF NOT EXISTS trg_sns_canary_idp_session_no_delete
  BEFORE DELETE ON sns_mirror_canary_idp_sessions
  BEGIN SELECT RAISE(ABORT,'canary_idp_session_delete_forbidden'); END;
