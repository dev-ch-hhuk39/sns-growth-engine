#!/usr/bin/env python3
"""Durable single-host one-use ledger for an *existing* Threads text publisher.

This is a supplemental provider-call barrier, NOT source-of-truth migration,
provider authorization, signed Sheets evidence, or approval of live activity.
Real opt-in is disabled by default and must be controlled by the operator.
No credentials, captions, media URLs or source text are stored in SQLite.

Operational assumptions: exactly one trusted host, a private LOCAL filesystem,
shared persistent SQLite file, stable HMAC key, no bypassing provider callers.
Neither SQLite nor this module can serialize remote unregistered publishers.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import stat
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import quote

SCHEMA_VERSION = 1
DB_SCHEMA = "sns_p0_one_use_provider_gate_v1"
ZERO_MAC = "0" * 64
QUEUES = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{3,159}$")
ACCOUNTS = frozenset({"night_scout", "liver_manager"})
POST_ID = re.compile(r"^[A-Za-z0-9_.:-]{2,160}$")
SHA = re.compile(r"^[0-9a-f]{64}$")
VALID_REASONS = frozenset({"PROVIDER_REJECTED_OR_UNKNOWN", "PROVIDER_ACK_MISSING", "LEDGER_ACK_UNAVAILABLE"})
STATES = frozenset({"CLAIMED_UNCERTAIN", "PROVIDER_ACKED", "PROVIDER_OUTCOME_UNVERIFIED", "POSTED_VERIFIED"})
ROOT = Path(__file__).resolve().parents[1]

DDL = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS sns_p0_once_meta (
    id INTEGER PRIMARY KEY CHECK(id=1),
    schema_version INTEGER NOT NULL CHECK(schema_version=1),
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sns_p0_once_heads (
    queue_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL CHECK(account_id IN ('night_scout','liver_manager')),
    platform TEXT NOT NULL CHECK(platform='threads'),
    source_sha256 TEXT NOT NULL CHECK(length(source_sha256)=64),
    state TEXT NOT NULL CHECK(state IN (
       'CLAIMED_UNCERTAIN','PROVIDER_ACKED',
       'PROVIDER_OUTCOME_UNVERIFIED','POSTED_VERIFIED'
    )),
    revision INTEGER NOT NULL CHECK(revision BETWEEN 1 AND 3),
    provider_post_id TEXT UNIQUE,
    last_event_mac TEXT NOT NULL CHECK(length(last_event_mac)=64),
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sns_p0_once_content_account
    ON sns_p0_once_heads(account_id,source_sha256);
CREATE TABLE IF NOT EXISTS sns_p0_once_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id TEXT NOT NULL UNIQUE,
    queue_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK(revision BETWEEN 1 AND 3),
    action TEXT NOT NULL CHECK(action IN ('CLAIM','ACK','UNKNOWN','VERIFY')),
    previous_event_mac TEXT NOT NULL CHECK(length(previous_event_mac)=64),
    event_mac TEXT NOT NULL UNIQUE CHECK(length(event_mac)=64),
    payload_json TEXT NOT NULL,
    UNIQUE(queue_id,revision),
    FOREIGN KEY(queue_id) REFERENCES sns_p0_once_heads(queue_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_sns_p0_once_event_queue
    ON sns_p0_once_events(queue_id,revision);
CREATE TABLE IF NOT EXISTS sns_p0_once_send_attempts (
    queue_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    source_sha256 TEXT NOT NULL CHECK(length(source_sha256)=64),
    claim_event_mac TEXT NOT NULL CHECK(length(claim_event_mac)=64),
    payload_json TEXT NOT NULL,
    send_mac TEXT NOT NULL CHECK(length(send_mac)=64),
    FOREIGN KEY(queue_id) REFERENCES sns_p0_once_heads(queue_id) ON DELETE RESTRICT
);
CREATE TRIGGER IF NOT EXISTS sns_p0_once_send_no_update
    BEFORE UPDATE ON sns_p0_once_send_attempts
    BEGIN SELECT RAISE(ABORT,'p0_once_send_immutable'); END;
CREATE TRIGGER IF NOT EXISTS sns_p0_once_send_no_delete
    BEFORE DELETE ON sns_p0_once_send_attempts
    BEGIN SELECT RAISE(ABORT,'p0_once_send_immutable'); END;
CREATE TRIGGER IF NOT EXISTS sns_p0_once_events_no_update
    BEFORE UPDATE ON sns_p0_once_events
    BEGIN SELECT RAISE(ABORT,'p0_once_journal_immutable'); END;
CREATE TRIGGER IF NOT EXISTS sns_p0_once_events_no_delete
    BEFORE DELETE ON sns_p0_once_events
    BEGIN SELECT RAISE(ABORT,'p0_once_journal_immutable'); END;
CREATE TRIGGER IF NOT EXISTS sns_p0_once_heads_no_delete
    BEFORE DELETE ON sns_p0_once_heads
    BEGIN SELECT RAISE(ABORT,'p0_once_head_immutable'); END;
"""


class P0OnceBlocked(RuntimeError):
    """Only fixed non-sensitive safety reason codes."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":")).encode("utf-8")


def _mac(key: bytes, value: dict[str, Any]) -> str:
    return hmac.new(key, _canonical(value), hashlib.sha256).hexdigest()


def source_fingerprint(*, account_id: str, queue_id: str, text: str,
                       media_used: bool = False) -> str:
    """Bind the exact text to one account and queue; never store raw text."""
    if (type(account_id) is not str or account_id not in ACCOUNTS
            or type(queue_id) is not str or not QUEUES.fullmatch(queue_id)
            or type(text) is not str or not text.strip()
            or len(text) > 30000 or type(media_used) is not bool
            or media_used):
        raise P0OnceBlocked("P0_ONCE_SCOPE_OR_TEXT_INVALID")
    return hashlib.sha256(_canonical({
        "account_id": account_id,
        "platform": "threads", "public_text": text, "media_used": False,
        "schema": DB_SCHEMA,
    })).hexdigest()


def _safe_path(path: str, *, allow_test_path: bool) -> Path:
    if type(path) is not str or not path or "\x00" in path:
        raise P0OnceBlocked("P0_ONCE_DB_PATH_INVALID")
    candidate = Path(path)
    if not candidate.is_absolute() or candidate.suffix != ".sqlite3":
        raise P0OnceBlocked("P0_ONCE_DB_PATH_INVALID")
    real = candidate.resolve(strict=False)
    if not allow_test_path:
        for dirname in ("/tmp", "/private/tmp", "/var/tmp", "/private/var/tmp", "/var/folders", "/private/var/folders"):
            blocked_dir = Path(dirname)
            if real == blocked_dir or blocked_dir in real.parents:
                raise P0OnceBlocked("P0_ONCE_DB_EPHEMERAL_LOCATION_FORBIDDEN")
    # macOS maps its OS-managed /var and /tmp roots to /private/var
    # and /private/tmp. Only explicit test paths may use these aliases.
    # Other symlinks, including symlinked directories nested within
    # those roots, remain strictly forbidden.
    is_system_test_alias = False
    if allow_test_path and sys.platform == "darwin":
        raw = str(candidate)
        for alias, canonical in (("/var/", "/private/var/"),
                                 ("/tmp/", "/private/tmp/")):
            if raw.startswith(alias) and str(real) == canonical + raw[len(alias):]:
                is_system_test_alias = True
                break
    if candidate.is_symlink() or (candidate != real and not is_system_test_alias):
        raise P0OnceBlocked("P0_ONCE_DB_SYMLINK_OR_ALIAS_FORBIDDEN")
    if is_system_test_alias:
        # Require every component BELOW the well-known OS alias to be
        # an ordinary directory. This closes the arbitrary-link bypass.
        remainder = raw.split("/", 2)[2]
        root_alias = Path("/") / raw.split("/")[1]
        current = root_alias
        for part in Path(remainder).parts[:-1]:
            current = current / part
            if current.is_symlink():
                raise P0OnceBlocked("P0_ONCE_DB_SYMLINK_OR_ALIAS_FORBIDDEN")
    if ROOT == real or ROOT in real.parents:
        raise P0OnceBlocked("P0_ONCE_DB_IN_SOURCE_TREE_FORBIDDEN")
    if not real.parent.is_dir():
        raise P0OnceBlocked("P0_ONCE_DB_PARENT_NOT_FOUND")
    parent = real.parent.stat()
    if (parent.st_uid != os.getuid() or parent.st_mode & 0o022):
        raise P0OnceBlocked("P0_ONCE_DB_PARENT_PERMISSIONS_UNSAFE")
    return real


def _private_file(path: Path) -> None:
    try:
        st = path.lstat()
    except OSError:
        raise P0OnceBlocked("P0_ONCE_DB_FILE_MISSING") from None
    if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid()
            or st.st_mode & 0o077):
        raise P0OnceBlocked("P0_ONCE_DB_PERMISSIONS_UNSAFE")


def initialize_local_db(path: str, *, explicit_operator_init: bool,
                        allow_test_path: bool = False) -> None:
    """Initialize only an explicitly requested *new*, private ledger file.

    Never automatically recreate a missing ledger: after a lost DB, all
    historical one-use claims may be lost, so operational posting MUST STOP.
    """
    if explicit_operator_init is not True:
        raise P0OnceBlocked("P0_ONCE_OPERATOR_INIT_REQUIRED")
    target = _safe_path(path, allow_test_path=allow_test_path)
    if target.exists() or target.is_symlink():
        raise P0OnceBlocked("P0_ONCE_DB_ALREADY_EXISTS")
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(str(target), flags, 0o600)
        os.close(fd)
        _private_file(target)
        with _db(path, allow_test_path=allow_test_path) as db:
            db.executescript(DDL)
            db.execute("INSERT INTO sns_p0_once_meta (id,schema_version,created_at) VALUES(1,?,?)",
                       (SCHEMA_VERSION, _now()))
    except P0OnceBlocked:
        # Do NOT remove a partially-created DB; require manual reconciliation.
        raise
    except (sqlite3.Error, OSError):
        raise P0OnceBlocked("P0_ONCE_DB_INITIALIZATION_FAILED") from None


@contextmanager
def _db(path: str, *, allow_test_path: bool) -> Iterator[sqlite3.Connection]:
    target = _safe_path(path, allow_test_path=allow_test_path)
    _private_file(target)
    uri = "file:" + quote(str(target), safe="/") + "?mode=rw"
    db = None
    try:
        db = sqlite3.connect(uri, uri=True, timeout=5,
                             isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=5000")
        db.execute("PRAGMA synchronous=FULL")
        yield db
    except P0OnceBlocked:
        raise
    except sqlite3.Error:
        raise P0OnceBlocked("P0_ONCE_DB_UNVERIFIED_NO_RETRY") from None
    finally:
        if db is not None:
            db.close()


def _verify_schema(db: sqlite3.Connection) -> None:
    try:
        row = db.execute("SELECT schema_version FROM sns_p0_once_meta WHERE id=1").fetchone()
        if row is None or row[0] != SCHEMA_VERSION:
            raise P0OnceBlocked("P0_ONCE_DB_SCHEMA_MISMATCH")
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise P0OnceBlocked("P0_ONCE_SQLITE_INTEGRITY_FAILED")
        trigger_names = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'")}
        required = {"sns_p0_once_events_no_update",
                    "sns_p0_once_events_no_delete",
                    "sns_p0_once_heads_no_delete",
                    "sns_p0_once_send_no_update",
                    "sns_p0_once_send_no_delete"}
        if db.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
                      "AND name='sns_p0_once_send_attempts'").fetchone()[0] != 1:
            raise P0OnceBlocked("P0_ONCE_SEND_ATTEMPT_TABLE_MISSING")
        if not required.issubset(trigger_names):
            raise P0OnceBlocked("P0_ONCE_IMMUTABLE_JOURNAL_GUARD_MISSING")
        indexes = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
        if "idx_sns_p0_once_content_account" not in indexes:
            raise P0OnceBlocked("P0_ONCE_CONTENT_UNIQUENESS_GUARD_MISSING")
    except sqlite3.Error:
        raise P0OnceBlocked("P0_ONCE_DB_SCHEMA_UNAVAILABLE") from None


def _head(db: sqlite3.Connection, queue_id: str) -> dict[str, Any] | None:
    result = db.execute("SELECT * FROM sns_p0_once_heads WHERE queue_id=?",
                        (queue_id,)).fetchone()
    return dict(result) if result is not None else None


def _audit(db: sqlite3.Connection, queue_id: str, head: dict[str, Any] | None,
           key: bytes) -> None:
    rows = db.execute("SELECT * FROM sns_p0_once_events WHERE queue_id=? ORDER BY revision",
                      (queue_id,)).fetchall()
    if (head is None) != (len(rows) == 0):
        raise P0OnceBlocked("P0_ONCE_JOURNAL_HEAD_MISMATCH")
    if head is None:
        return
    previous = ZERO_MAC
    last: dict[str, Any] = {}
    for version, row in enumerate(rows, 1):
        try:
            event = json.loads(row["payload_json"])
        except (TypeError, ValueError):
            raise P0OnceBlocked("P0_ONCE_JOURNAL_CORRUPT") from None
        if (not isinstance(event, dict) or event.get("version") != version
                or event.get("queue_id") != queue_id
                or event.get("account_id") != head["account_id"]
                or event.get("source_sha256") != head["source_sha256"]
                or event.get("action") != row["action"]
                or event.get("previous_event_mac") != previous
                or row["previous_event_mac"] != previous
                or row["revision"] != version
                or event.get("operation_id") != row["operation_id"]
                or _mac(key, event) != row["event_mac"]):
            raise P0OnceBlocked("P0_ONCE_JOURNAL_CORRUPT")
        previous = row["event_mac"]
        last = event
    if (len(rows) != head["revision"] or previous != head["last_event_mac"]
            or head["platform"] != "threads"
            or last.get("schema") != DB_SCHEMA
            or last.get("platform") != "threads"
            or last.get("state") != head["state"]
            or last.get("provider_post_id") != (head["provider_post_id"] or "")
            or head["state"] not in STATES):
        raise P0OnceBlocked("P0_ONCE_JOURNAL_HEAD_MISMATCH")


class P0OnceGuard:
    """Every attempt uses a fresh transaction, never a renewable lease.

    An interrupted or ambiguous claim remains irrevocable. Backups and
    manual provider reconciliation are outside the automatic publish path.
    """

    def __init__(self, db_path: str, secret_key: bytes, *, allow_test_path: bool = False):
        if type(secret_key) is not bytes or len(secret_key) < 32:
            raise P0OnceBlocked("P0_ONCE_HMAC_KEY_INVALID")
        self.db_path = db_path
        self.secret_key = secret_key
        self.allow_test_path = allow_test_path
        with _db(self.db_path, allow_test_path=self.allow_test_path) as db:
            _verify_schema(db)

    @classmethod
    def from_env(cls) -> "P0OnceGuard":
        db_path = os.environ.get("SNS_P0_ONCE_DB_PATH", "")
        key_hex = os.environ.get("SNS_P0_ONCE_HMAC_KEY_HEX", "")
        if not re.fullmatch(r"[0-9a-fA-F]{64,}", key_hex) or len(key_hex) % 2:
            raise P0OnceBlocked("P0_ONCE_HMAC_KEY_NOT_CONFIGURED")
        return cls(db_path, bytes.fromhex(key_hex))

    def _event(self, db: sqlite3.Connection, *, account_id: str,
               queue_id: str, source_sha256: str, action: str, state: str,
               provider_post_id: str = "") -> dict[str, Any]:
        old = _head(db, queue_id)
        _audit(db, queue_id, old, self.secret_key)
        if old is not None:
            if old["account_id"] != account_id or old["source_sha256"] != source_sha256:
                raise P0OnceBlocked("P0_ONCE_GLOBAL_QUEUE_OR_SOURCE_COLLISION")
        if action == "CLAIM":
            if old is not None:
                raise P0OnceBlocked("P0_ONCE_ALREADY_CLAIMED_NO_RETRY")
            duplicate = db.execute(
                "SELECT queue_id FROM sns_p0_once_heads "
                "WHERE account_id=? AND source_sha256=?",
                (account_id, source_sha256),
            ).fetchone()
            if duplicate is not None:
                raise P0OnceBlocked("P0_ONCE_SAME_TEXT_ACCOUNT_ALREADY_CLAIMED")
        elif action in ("ACK", "UNKNOWN"):
            if old is None or old["state"] != "CLAIMED_UNCERTAIN":
                raise P0OnceBlocked("P0_ONCE_ILLEGAL_TRANSITION_NO_RETRY")
        elif action == "VERIFY":
            if old is None or old["state"] != "PROVIDER_ACKED":
                raise P0OnceBlocked("P0_ONCE_ILLEGAL_TRANSITION_NO_RETRY")
            if not provider_post_id or provider_post_id != old["provider_post_id"]:
                raise P0OnceBlocked("P0_ONCE_PROVIDER_ID_MISMATCH")
        else:
            raise P0OnceBlocked("P0_ONCE_ACTION_INVALID")
        revision = old["revision"] + 1 if old else 1
        prev = old["last_event_mac"] if old else ZERO_MAC
        event = {
            "schema": DB_SCHEMA,
            "operation_id": "p0_once_" + secrets.token_hex(16),
            "account_id": account_id, "queue_id": queue_id,
            "platform": "threads", "source_sha256": source_sha256,
            "version": revision, "action": action, "state": state,
            "provider_post_id": provider_post_id,
            "occurred_at": _now(), "previous_event_mac": prev,
        }
        signature = _mac(self.secret_key, event)
        if old is None:
            db.execute("""INSERT INTO sns_p0_once_heads
                (queue_id,account_id,platform,source_sha256,state,revision,
                 provider_post_id,last_event_mac,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (queue_id, account_id, "threads", source_sha256, state, revision,
                 provider_post_id or None, signature, event["occurred_at"]),
            )
        else:
            updated = db.execute("""UPDATE sns_p0_once_heads
                SET state=?,revision=?,provider_post_id=?,last_event_mac=?,updated_at=?
                WHERE queue_id=? AND account_id=? AND revision=? AND last_event_mac=?""",
                (state, revision, provider_post_id or None, signature, event["occurred_at"],
                 queue_id, account_id, old["revision"], prev),
            )
            if updated.rowcount != 1:
                raise P0OnceBlocked("P0_ONCE_CAS_CONFLICT_NO_RETRY")
        db.execute("""INSERT INTO sns_p0_once_events
            (operation_id,queue_id,revision,action,previous_event_mac,event_mac,payload_json)
            VALUES(?,?,?,?,?,?,?)""",
            (event["operation_id"], queue_id, revision, action, prev,
             signature, _canonical(event).decode("ascii")),
        )
        return {"status": state, "revision": revision, "event_mac": signature}

    def _transition(self, *, account_id: str, queue_id: str, source_sha256: str,
                    action: str, state: str, provider_post_id: str = "") -> dict[str, Any]:
        if (type(account_id) is not str or account_id not in ACCOUNTS
                or type(queue_id) is not str
                or not QUEUES.fullmatch(queue_id)
                or type(source_sha256) is not str or not SHA.fullmatch(source_sha256)
                or type(provider_post_id) is not str):
            raise P0OnceBlocked("P0_ONCE_SCOPE_INVALID")
        if provider_post_id and not POST_ID.fullmatch(provider_post_id):
            raise P0OnceBlocked("P0_ONCE_PROVIDER_ID_INVALID")
        with _db(self.db_path, allow_test_path=self.allow_test_path) as db:
            _verify_schema(db)
            try:
                db.execute("BEGIN IMMEDIATE")
                result = self._event(db, account_id=account_id, queue_id=queue_id,
                                     source_sha256=source_sha256, action=action,
                                     state=state, provider_post_id=provider_post_id)
                db.execute("COMMIT")
            except P0OnceBlocked:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise
            except sqlite3.Error:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise P0OnceBlocked("P0_ONCE_SQLITE_OUTCOME_UNKNOWN_NO_RETRY") from None
            saved = _head(db, queue_id)
            _audit(db, queue_id, saved, self.secret_key)
            if saved is None or saved["last_event_mac"] != result["event_mac"]:
                raise P0OnceBlocked("P0_ONCE_COMMIT_READBACK_UNKNOWN_NO_RETRY")
            return result

    def claim(self, *, account_id: str, queue_id: str, source_sha256: str) -> dict[str, Any]:
        return self._transition(account_id=account_id, queue_id=queue_id,
                                source_sha256=source_sha256, action="CLAIM",
                                state="CLAIMED_UNCERTAIN")

    def provider_accepted(self, *, account_id: str, queue_id: str,
                          source_sha256: str, provider_post_id: str) -> dict[str, Any]:
        if not provider_post_id:
            raise P0OnceBlocked("P0_ONCE_PROVIDER_ACK_MISSING_NO_RETRY")
        return self._transition(account_id=account_id, queue_id=queue_id,
                                source_sha256=source_sha256, action="ACK",
                                state="PROVIDER_ACKED", provider_post_id=provider_post_id)

    def quarantine(self, *, account_id: str, queue_id: str,
                   source_sha256: str) -> dict[str, Any]:
        return self._transition(account_id=account_id, queue_id=queue_id,
                                source_sha256=source_sha256, action="UNKNOWN",
                                state="PROVIDER_OUTCOME_UNVERIFIED")

    def verify_posted(self, *, account_id: str, queue_id: str,
                      source_sha256: str, provider_post_id: str,
                      queue_readback_pass: bool, result_readback_pass: bool) -> dict[str, Any]:
        if queue_readback_pass is not True or result_readback_pass is not True:
            raise P0OnceBlocked("P0_ONCE_FINAL_READBACK_REQUIRED")
        return self._transition(account_id=account_id, queue_id=queue_id,
                                source_sha256=source_sha256, action="VERIFY",
                                state="POSTED_VERIFIED", provider_post_id=provider_post_id)

    def _checked_claim_receipt(self, db: sqlite3.Connection, *,
                               account_id: str, queue_id: str, text: str,
                               source_sha256: str, event_mac: str) -> None:
        if (type(account_id) is not str or account_id not in ACCOUNTS
                or type(queue_id) is not str or not QUEUES.fullmatch(queue_id)
                or type(text) is not str
                or type(source_sha256) is not str or not SHA.fullmatch(source_sha256)
                or type(event_mac) is not str or not SHA.fullmatch(event_mac)):
            raise P0OnceBlocked("P0_ONCE_SEND_RECEIPT_INVALID")
        if source_fingerprint(account_id=account_id, queue_id=queue_id,
                              text=text) != source_sha256:
            raise P0OnceBlocked("P0_ONCE_SEND_SOURCE_CHANGED")
        head = _head(db, queue_id)
        _audit(db, queue_id, head, self.secret_key)
        if (head is None or head["account_id"] != account_id
                or head["source_sha256"] != source_sha256
                or head["state"] != "CLAIMED_UNCERTAIN"
                or head["revision"] != 1
                or not hmac.compare_digest(head["last_event_mac"], event_mac)):
            raise P0OnceBlocked("P0_ONCE_SEND_RECEIPT_NOT_CURRENT")

    def validate_claim_receipt(
        self, *, account_id: str, queue_id: str, text: str,
        source_sha256: str, event_mac: str,
    ) -> None:
        """Check claim authenticity without reserving/renewing a send."""
        with _db(self.db_path, allow_test_path=self.allow_test_path) as db:
            _verify_schema(db)
            self._checked_claim_receipt(
                db, account_id=account_id, queue_id=queue_id, text=text,
                source_sha256=source_sha256, event_mac=event_mac,
            )
            if db.execute("SELECT 1 FROM sns_p0_once_send_attempts WHERE queue_id=?",
                          (queue_id,)).fetchone():
                raise P0OnceBlocked("P0_ONCE_SEND_ALREADY_STARTED_NO_RETRY")

    def consume_send_receipt(
        self, *, account_id: str, queue_id: str, text: str,
        source_sha256: str, event_mac: str,
    ) -> None:
        """Durably reserve the sole HTTP attempt before making a network call.

        This record is immutable; uncertain/failed requests never free it.
        Concurrent processes racing the same claim can only insert one row.
        """
        with _db(self.db_path, allow_test_path=self.allow_test_path) as db:
            _verify_schema(db)
            try:
                db.execute("BEGIN IMMEDIATE")
                self._checked_claim_receipt(
                    db, account_id=account_id, queue_id=queue_id, text=text,
                    source_sha256=source_sha256, event_mac=event_mac,
                )
                payload = {"schema": DB_SCHEMA, "queue_id": queue_id,
                           "account_id": account_id, "source_sha256": source_sha256,
                           "claim_event_mac": event_mac,
                           "operation_id": "p0_send_" + secrets.token_hex(16),
                           "started_at": _now()}
                signature = _mac(self.secret_key, payload)
                db.execute(
                    "INSERT INTO sns_p0_once_send_attempts "
                    "(queue_id,account_id,source_sha256,claim_event_mac,payload_json,send_mac) "
                    "VALUES(?,?,?,?,?,?)",
                    (queue_id, account_id, source_sha256, event_mac,
                     _canonical(payload).decode("ascii"), signature),
                )
                db.execute("COMMIT")
            except P0OnceBlocked:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise
            except sqlite3.IntegrityError:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise P0OnceBlocked("P0_ONCE_SEND_ALREADY_STARTED_NO_RETRY") from None
            except sqlite3.Error:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise P0OnceBlocked("P0_ONCE_SEND_RESERVATION_UNKNOWN_NO_RETRY") from None
            row = db.execute(
                "SELECT payload_json,send_mac FROM sns_p0_once_send_attempts WHERE queue_id=?",
                (queue_id,),
            ).fetchone()
            try:
                verified = (row is not None
                            and row["send_mac"] == signature
                            and hmac.compare_digest(
                                _mac(self.secret_key, json.loads(row["payload_json"])),
                                row["send_mac"]))
            except (TypeError, ValueError):
                verified = False
            if not verified:
                raise P0OnceBlocked("P0_ONCE_SEND_READBACK_UNKNOWN_NO_RETRY")

    def inspect(self, *, queue_id: str) -> dict[str, Any]:
        if type(queue_id) is not str or not QUEUES.fullmatch(queue_id):
            raise P0OnceBlocked("P0_ONCE_QUEUE_ID_INVALID")
        with _db(self.db_path, allow_test_path=self.allow_test_path) as db:
            _verify_schema(db)
            row = _head(db, queue_id)
            _audit(db, queue_id, row, self.secret_key)
            if row is None:
                raise P0OnceBlocked("P0_ONCE_QUEUE_NOT_FOUND")
            return {
                "status": row["state"], "revision": row["revision"],
                "queue_hash": hashlib.sha256(queue_id.encode()).hexdigest()[:16],
                "provider_ack_recorded": bool(row["provider_post_id"]),
                "retry_allowed": False, "source_cutover_authorized": False,
            }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="One-use barrier administration (NO posting or source cutover)",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Create a NEW empty private local ledger")
    init.add_argument("--db-path", required=True)
    init.add_argument("--explicit-operator-init", action="store_true")
    inspect = commands.add_parser("inspect", help="Read-only one-queue inspection")
    inspect.add_argument("--db-path", required=True)
    inspect.add_argument("--queue-id", required=True)
    args = parser.parse_args()
    try:
        if args.command == "init":
            initialize_local_db(args.db_path,
                                explicit_operator_init=args.explicit_operator_init)
            result = {"status": "LEDGER_CREATED_NOT_ACTIVATED",
                      "publish_authorized": False,
                      "source_cutover_authorized": False}
        else:
            key_hex = os.environ.get("SNS_P0_ONCE_HMAC_KEY_HEX", "")
            if not re.fullmatch(r"[0-9a-fA-F]{64,}", key_hex) or len(key_hex) % 2:
                raise P0OnceBlocked("P0_ONCE_HMAC_KEY_NOT_CONFIGURED")
            ledger = P0OnceGuard(args.db_path, bytes.fromhex(key_hex))
            result = ledger.inspect(queue_id=args.queue_id)
        print(json.dumps(result, sort_keys=True))
        return 0
    except P0OnceBlocked as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    sys.exit(main())
