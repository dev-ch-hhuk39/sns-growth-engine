-- Additive, in-memory-only, non-authorizing shadow comparison schema.
-- DO NOT migrate this to an operational queue or existing SQLite database.
PRAGMA foreign_keys=ON;
CREATE TABLE sns_p0_shadow_batch (
    batch_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL CHECK(schema_version='sns_p0_shadow_parity_v1'),
    queue_count INTEGER NOT NULL CHECK(queue_count>=0),
    posted_count INTEGER NOT NULL CHECK(posted_count>=0),
    source_fingerprint TEXT NOT NULL CHECK(length(source_fingerprint)=64),
    row_manifest_hash TEXT NOT NULL CHECK(length(row_manifest_hash)=64),
    disposition TEXT NOT NULL CHECK(disposition='STAGED_BLOCKED')
);
CREATE TABLE sns_p0_shadow_queue (
    batch_id TEXT NOT NULL REFERENCES sns_p0_shadow_batch(batch_id),
    identity_hmac TEXT NOT NULL CHECK(length(identity_hmac)=64),
    row_hmac TEXT NOT NULL CHECK(length(row_hmac)=64),
    account_id TEXT NOT NULL CHECK(account_id IN ('night_scout','liver_manager')),
    status TEXT NOT NULL,
    PRIMARY KEY(batch_id,identity_hmac)
);
CREATE TABLE sns_p0_shadow_post (
    batch_id TEXT NOT NULL REFERENCES sns_p0_shadow_batch(batch_id),
    identity_hmac TEXT NOT NULL CHECK(length(identity_hmac)=64),
    row_hmac TEXT NOT NULL CHECK(length(row_hmac)=64),
    account_id TEXT NOT NULL CHECK(account_id IN ('night_scout','liver_manager')),
    status TEXT NOT NULL CHECK(status='POSTED'),
    PRIMARY KEY(batch_id,identity_hmac)
);
CREATE TRIGGER sns_p0_shadow_batch_immutable_up BEFORE UPDATE ON sns_p0_shadow_batch
    BEGIN SELECT RAISE(ABORT,'shadow_batch_immutable'); END;
CREATE TRIGGER sns_p0_shadow_batch_immutable_del BEFORE DELETE ON sns_p0_shadow_batch
    BEGIN SELECT RAISE(ABORT,'shadow_batch_immutable'); END;
CREATE TRIGGER sns_p0_shadow_queue_immutable_up BEFORE UPDATE ON sns_p0_shadow_queue
    BEGIN SELECT RAISE(ABORT,'shadow_queue_immutable'); END;
CREATE TRIGGER sns_p0_shadow_queue_immutable_del BEFORE DELETE ON sns_p0_shadow_queue
    BEGIN SELECT RAISE(ABORT,'shadow_queue_immutable'); END;
CREATE TRIGGER sns_p0_shadow_post_immutable_up BEFORE UPDATE ON sns_p0_shadow_post
    BEGIN SELECT RAISE(ABORT,'shadow_post_immutable'); END;
CREATE TRIGGER sns_p0_shadow_post_immutable_del BEFORE DELETE ON sns_p0_shadow_post
    BEGIN SELECT RAISE(ABORT,'shadow_post_immutable'); END;
