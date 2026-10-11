-- Phase 5B-5B: dedicated trust data. Migration is explicit and OFFLINE only.
-- Provision authenticated sessions and scoped grants exclusively through a trusted IdP/backend.
-- Never seed a reviewer, grant, approval, or evidence verification from client JSON.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sns_review_sessions (
    session_id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    issuer TEXT NOT NULL,
    token_sha256 TEXT NOT NULL,
    token_jti TEXT NOT NULL,
    authenticated_at INTEGER NOT NULL,
    mfa_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    revoked_at INTEGER,
    CHECK (expires_at > authenticated_at),
    CHECK (mfa_at >= authenticated_at),
    CHECK (mfa_at <= expires_at),
    CHECK (revoked_at IS NULL OR revoked_at > 0)
);
CREATE INDEX IF NOT EXISTS idx_sns_review_sessions_subject
    ON sns_review_sessions(subject, expires_at);

CREATE TABLE IF NOT EXISTS sns_review_account_grants (
    subject TEXT NOT NULL,
    account_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('ADMIN','MEDIA_REVIEWER','VIEWER')),
    enabled INTEGER NOT NULL CHECK (enabled IN (0,1)),
    PRIMARY KEY (subject, account_id, role)
);

-- Every proof stores its original bytes plus exact integrity digest in a protected DB.
-- Historical attestations/revocations are never overwritten.
CREATE TABLE IF NOT EXISTS sns_review_evidence_events (
    evidence_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0 AND revision <= 128),
    operation_id TEXT NOT NULL UNIQUE,
    action TEXT NOT NULL CHECK (action IN ('VERIFY','REVOKE')),
    metadata_json TEXT NOT NULL,
    original_bytes BLOB NOT NULL,
    original_sha256 TEXT NOT NULL,
    previous_event_sha256 TEXT NOT NULL,
    event_sha256 TEXT NOT NULL UNIQUE,
    reviewer_subject TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (evidence_id, revision)
);
CREATE INDEX IF NOT EXISTS idx_sns_review_evidence_latest
    ON sns_review_evidence_events(evidence_id, revision DESC);

CREATE TRIGGER IF NOT EXISTS trg_sns_review_evidence_no_update
BEFORE UPDATE ON sns_review_evidence_events
BEGIN
    SELECT RAISE(ABORT,'protected_evidence_append_only');
END;
CREATE TRIGGER IF NOT EXISTS trg_sns_review_evidence_no_delete
BEFORE DELETE ON sns_review_evidence_events
BEGIN
    SELECT RAISE(ABORT,'protected_evidence_delete_forbidden');
END;
