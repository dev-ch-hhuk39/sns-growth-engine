#!/usr/bin/env python3
"""Extra, durable host-wide guard for paid HTTP attempts (standard library only).

Call ``reserve_host_ai_attempt`` immediately before *each* transport attempt,
including retries. A successful reservation is never refunded. This composes
with existing provider/JSON/Sheets budgets; it does not replace them or authorize
paid operation. Host deployment must protect the environment and this directory.

No database is created by a reservation. An operator must separately audit all
current JST day/month spending, then explicitly initialize the ledger offline.
The audit/attestation itself cannot be verified by this module. Never initialize
another directory or restore an older ledger to obtain fresh capacity.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
from typing import Iterator


JST = timezone(timedelta(hours=9), "JST")
EXECUTION_LIMIT = 20
DAILY_LIMIT = 40
MONTHLY_LIMIT = 1000
DB_NAME = "host-ai-budget.sqlite3"
LOCK_NAME = "host-ai-budget.lock"
INITIALIZATION_CONFIRMATION = "AUDITED_CURRENT_JST_BASELINES"
_APPLICATION_ID = 0x534E5342
_SCHEMA_VERSION = 1
_ACCOUNTS = frozenset({"night_scout", "liver_manager", "beauty_account"})
_HEX32 = re.compile(r"[0-9a-f]{32}\Z")
_HEX40 = re.compile(r"[0-9a-f]{40}\Z")
_OPERATION = re.compile(r"[a-z][a-z0-9_.:-]{0,63}\Z")
_SCHEMA = {
    "budget_metadata": """CREATE TABLE budget_metadata (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        schema_version INTEGER NOT NULL CHECK (schema_version = 1),
        initialized_day TEXT NOT NULL,
        initialized_month TEXT NOT NULL,
        baseline_day INTEGER NOT NULL CHECK (baseline_day BETWEEN 0 AND 40),
        baseline_month INTEGER NOT NULL CHECK (baseline_month BETWEEN 0 AND 1000),
        last_day TEXT NOT NULL,
        reservation_count INTEGER NOT NULL CHECK (reservation_count >= 0),
        CHECK (baseline_day <= baseline_month))""",
    "runs": """CREATE TABLE runs (
        run_id TEXT PRIMARY KEY NOT NULL,
        account_id TEXT NOT NULL CHECK (
            account_id IN ('night_scout', 'liver_manager', 'beauty_account')),
        release TEXT NOT NULL)""",
    "attempts": """CREATE TABLE attempts (
        attempt_id INTEGER PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES runs(run_id),
        day_key TEXT NOT NULL,
        month_key TEXT NOT NULL)""",
}


class HostAIBudgetError(RuntimeError):
    """Fixed, non-sensitive refusal reason; never includes caller values."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__("sns_host_ai_budget:" + code)


def _deny(code: str) -> None:
    raise HostAIBudgetError(code)


def _now_jst() -> datetime:
    return datetime.now(JST)


def _day_key() -> str:
    now = _now_jst()
    if now.tzinfo is None or now.utcoffset() is None:
        _deny("invalid_clock")
    return now.astimezone(JST).strftime("%Y-%m-%d")


def _valid_day(value: object) -> bool:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        return False
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%Y-%m-%d") == value
    except ValueError:
        return False


@dataclass(frozen=True)
class _Context:
    directory: str
    run_id: str
    account_id: str
    release: str


def _context(account_id: str, operation: str) -> _Context | None:
    mode = os.environ.get("SNS_HOST_AI_BUDGET_REQUIRED")
    if mode is None or mode.lower() in {"false", "0"}:
        return None
    if mode.lower() not in {"true", "1"}:
        _deny("invalid_mode")
    directory = os.environ.get("SNS_HOST_AI_BUDGET_DIR", "")
    run_id = os.environ.get("SNS_HOST_AI_RUN_ID", "")
    host_account = os.environ.get("SNS_HOST_AI_ACCOUNT_ID", "")
    release = os.environ.get("SNS_HOST_AI_RELEASE", "")
    if (
        not directory
        or not _HEX32.fullmatch(run_id)
        or host_account not in _ACCOUNTS
        or not _HEX40.fullmatch(release)
        or not isinstance(operation, str)
        or not _OPERATION.fullmatch(operation)
    ):
        _deny("invalid_context")
    if account_id not in _ACCOUNTS or account_id != host_account:
        _deny("account_mismatch")
    return _Context(directory, run_id, host_account, release)


def _check_directory(info: os.stat_result, *, private: bool) -> None:
    if not stat.S_ISDIR(info.st_mode):
        _deny("unsafe_directory")
    mode = stat.S_IMODE(info.st_mode)
    if private:
        if info.st_uid != os.geteuid() or mode != 0o700:
            _deny("unsafe_directory")
    elif info.st_uid not in {0, os.geteuid()} or (
        mode & 0o022 and not (info.st_uid == 0 and mode & stat.S_ISVTX)
    ):
        _deny("unsafe_directory")


@contextmanager
def _private_directory(directory: str) -> Iterator[tuple[int, Path]]:
    # Walk with no-follow descriptors, including ancestors. A dedicated 0700
    # directory under a root-owned sticky temporary directory is safe for tests.
    if (
        not isinstance(directory, str)
        or not os.path.isabs(directory)
        or directory != os.path.normpath(directory)
        or directory == "/"
        or "\x00" in directory
    ):
        _deny("unsafe_directory")
    descriptors: list[int] = []
    try:
        descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(descriptor)
        _check_directory(os.fstat(descriptor), private=False)
        components = directory.split("/")[1:]
        for index, component in enumerate(components):
            descriptor = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=descriptor,
            )
            descriptors.append(descriptor)
            _check_directory(os.fstat(descriptor), private=index == len(components) - 1)
        yield descriptor, Path(directory)
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _check_file(info: os.stat_result) -> None:
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_nlink != 1
    ):
        _deny("unsafe_file")


def _inspect_directory(descriptor: int, *, require_db: bool) -> None:
    entries = set(os.listdir(descriptor))
    if entries - {DB_NAME, LOCK_NAME, DB_NAME + "-journal"}:
        _deny("unexpected_files")
    if require_db and DB_NAME not in entries:
        _deny("uninitialized")
    for name in entries:
        _check_file(os.stat(name, dir_fd=descriptor, follow_symlinks=False))


@contextmanager
def _locked_directory(directory: str, *, initialize: bool = False) -> Iterator[tuple[int, Path]]:
    with _private_directory(directory) as (descriptor, path):
        _inspect_directory(descriptor, require_db=not initialize)
        flags = os.O_RDWR | os.O_NOFOLLOW
        if initialize:
            flags |= os.O_CREAT
        lock = os.open(LOCK_NAME, flags, 0o600, dir_fd=descriptor)
        try:
            _check_file(os.fstat(lock))
            if os.fstat(lock).st_size != 0:
                _deny("unsafe_file")
            fcntl.flock(lock, fcntl.LOCK_EX)
            _inspect_directory(descriptor, require_db=not initialize)
            # SQLite must open by name. Verify the protected path still resolves
            # to the same directory; no world-writable non-sticky ancestor exists.
            current = os.stat(path, follow_symlinks=False)
            held = os.fstat(descriptor)
            if (current.st_dev, current.st_ino) != (held.st_dev, held.st_ino):
                _deny("unsafe_directory")
            yield descriptor, path
        finally:
            os.close(lock)


@contextmanager
def _connection(path: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(
        (path / DB_NAME).as_uri() + "?mode=rw", uri=True, timeout=30, isolation_level=None
    )
    try:
        connection.execute("PRAGMA trusted_schema = OFF")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA synchronous = FULL")
        connection.execute("PRAGMA temp_store = MEMORY")
        # WAL/shm files are deliberately unsupported. The only valid format uses
        # a rollback journal with the same 0600 permissions as the database.
        if connection.execute("PRAGMA journal_mode").fetchone() != ("delete",):
            _deny("invalid_schema")
        connection.execute("BEGIN IMMEDIATE")
        yield connection
        connection.execute("COMMIT")
    finally:
        connection.close()


def _normalized_sql(value: str) -> str:
    return " ".join(value.split())


def _validate_ledger(connection: sqlite3.Connection, today: str) -> tuple[int, int, Counter[str]]:
    if (
        connection.execute("PRAGMA application_id").fetchone() != (_APPLICATION_ID,)
        or connection.execute("PRAGMA user_version").fetchone() != (_SCHEMA_VERSION,)
    ):
        _deny("invalid_schema")
    actual = connection.execute(
        "SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
    ).fetchall()
    if len(actual) != len(_SCHEMA) or any(
        kind != "table" or name not in _SCHEMA or _normalized_sql(sql) != _normalized_sql(_SCHEMA[name])
        for kind, name, sql in actual
    ):
        _deny("invalid_schema")
    if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
        _deny("invalid_ledger")
    if connection.execute("PRAGMA foreign_key_check").fetchall():
        _deny("invalid_ledger")
    metadata = connection.execute("SELECT * FROM budget_metadata").fetchall()
    if len(metadata) != 1:
        _deny("invalid_ledger")
    singleton, version, initial_day, initial_month, baseline_day, baseline_month, last_day, count = metadata[0]
    if (
        singleton != 1 or version != _SCHEMA_VERSION
        or not _valid_day(initial_day) or initial_month != initial_day[:7]
        or not _valid_day(last_day) or last_day < initial_day
        or type(baseline_day) is not int or type(baseline_month) is not int
        or not 0 <= baseline_day <= DAILY_LIMIT
        or not baseline_day <= baseline_month <= MONTHLY_LIMIT
        or type(count) is not int or count < 0
    ):
        _deny("invalid_ledger")
    if today < last_day:
        _deny("clock_rollback")
    runs = connection.execute("SELECT run_id, account_id, release FROM runs").fetchall()
    known_runs = set()
    for run_id, account_id, release in runs:
        if (
            not isinstance(run_id, str) or not _HEX32.fullmatch(run_id)
            or account_id not in _ACCOUNTS
            or not isinstance(release, str) or not _HEX40.fullmatch(release)
        ):
            _deny("invalid_ledger")
        known_runs.add(run_id)
    days: Counter[str] = Counter({initial_day: baseline_day})
    months: Counter[str] = Counter({initial_month: baseline_month})
    run_counts: Counter[str] = Counter()
    previous_day = initial_day
    attempts = connection.execute(
        "SELECT attempt_id, run_id, day_key, month_key FROM attempts ORDER BY attempt_id"
    ).fetchall()
    for expected_id, (attempt_id, run_id, day, month) in enumerate(attempts, start=1):
        if (
            attempt_id != expected_id or run_id not in known_runs
            or not _valid_day(day) or month != day[:7] or day < previous_day
        ):
            _deny("invalid_ledger")
        previous_day = day
        days[day] += 1
        months[month] += 1
        run_counts[run_id] += 1
    if (
        len(attempts) != count or previous_day != last_day
        or known_runs != set(run_counts)
        or any(value > DAILY_LIMIT for value in days.values())
        or any(value > MONTHLY_LIMIT for value in months.values())
        or any(value > EXECUTION_LIMIT for value in run_counts.values())
    ):
        _deny("invalid_ledger")
    return days[today], months[today[:7]], run_counts


def _sync_files(descriptor: int) -> None:
    # COMMIT's synchronous=FULL flushes SQLite's journal/database. Also explicitly
    # flush the ledger and directory entry before authorizing the HTTP attempt.
    handle = os.open(DB_NAME, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=descriptor)
    try:
        _check_file(os.fstat(handle))
        os.fsync(handle)
    finally:
        os.close(handle)
    os.fsync(descriptor)


def reserve_host_ai_attempt(account_id: str, operation: str) -> None:
    """Durably consume one global attempt or raise ``HostAIBudgetError``.

    Absent/false ``SNS_HOST_AI_BUDGET_REQUIRED`` preserves legacy behavior. True
    requires ``SNS_HOST_AI_BUDGET_DIR``, ``SNS_HOST_AI_RUN_ID`` (32 lowercase hex),
    ``SNS_HOST_AI_ACCOUNT_ID`` and ``SNS_HOST_AI_RELEASE`` (40 lowercase hex).
    Run IDs remain bound to one account/release forever, across fresh processes.
    Operation is syntax checked but never persisted; no prompts or keys are read.
    """
    try:
        context = _context(account_id, operation)
        if context is None:
            return
        today = _day_key()
        with _locked_directory(context.directory) as (descriptor, path):
            with _connection(path) as connection:
                daily, monthly, runs = _validate_ledger(connection, today)
                scope = connection.execute(
                    "SELECT account_id, release FROM runs WHERE run_id = ?", (context.run_id,)
                ).fetchone()
                if scope is not None and scope != (context.account_id, context.release):
                    _deny("run_scope_mismatch")
                if runs[context.run_id] >= EXECUTION_LIMIT:
                    _deny("execution_limit")
                if daily >= DAILY_LIMIT:
                    _deny("daily_limit")
                if monthly >= MONTHLY_LIMIT:
                    _deny("monthly_limit")
                connection.execute(
                    "INSERT OR IGNORE INTO runs VALUES (?, ?, ?)",
                    (context.run_id, context.account_id, context.release),
                )
                connection.execute(
                    "INSERT INTO attempts (run_id, day_key, month_key) VALUES (?, ?, ?)",
                    (context.run_id, today, today[:7]),
                )
                connection.execute(
                    "UPDATE budget_metadata SET last_day = ?, reservation_count = reservation_count + 1",
                    (today,),
                )
            _inspect_directory(descriptor, require_db=True)
            _sync_files(descriptor)
    except HostAIBudgetError:
        raise
    except Exception:
        # Unknown storage/format failures must neither authorize an attempt nor
        # expose raw filesystem/SQLite/caller details through exception text.
        raise HostAIBudgetError("storage_unavailable") from None


def initialize_host_ai_budget(
    directory: str,
    *,
    day_key: str,
    month_key: str,
    day_used: int,
    month_used: int,
    confirmation: str,
) -> None:
    """Offline operator action; mandatory audited baselines, no implicit grant.

    The directory must already exist as a private 0700 directory. An existing
    database is always refused, even if empty/corrupt. The explicit confirmation
    attests to an independent audit; this function cannot establish its truth.
    """
    try:
        today = _day_key()
        if confirmation != INITIALIZATION_CONFIRMATION:
            _deny("initialization_confirmation_required")
        if (
            not _valid_day(day_key) or day_key != today or month_key != today[:7]
            or type(day_used) is not int or type(month_used) is not int
            or not 0 <= day_used <= DAILY_LIMIT
            or not day_used <= month_used <= MONTHLY_LIMIT
        ):
            _deny("invalid_baseline")
        with _locked_directory(directory, initialize=True) as (descriptor, path):
            if DB_NAME in os.listdir(descriptor) or DB_NAME + "-journal" in os.listdir(descriptor):
                _deny("already_initialized")
            handle = os.open(
                DB_NAME, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600, dir_fd=descriptor,
            )
            try:
                _check_file(os.fstat(handle))
                os.fsync(handle)
            finally:
                os.close(handle)
            with _connection(path) as connection:
                connection.execute(f"PRAGMA application_id = {_APPLICATION_ID}")
                connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
                for sql in _SCHEMA.values():
                    connection.execute(sql)
                connection.execute(
                    "INSERT INTO budget_metadata VALUES (1, ?, ?, ?, ?, ?, ?, 0)",
                    (_SCHEMA_VERSION, day_key, month_key, day_used, month_used, day_key),
                )
                _validate_ledger(connection, today)
            _inspect_directory(descriptor, require_db=True)
            _sync_files(descriptor)
    except HostAIBudgetError:
        raise
    except Exception:
        raise HostAIBudgetError("storage_unavailable") from None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("plan", help="Offline plan only; never inspect/create a ledger")
    initialize = subparsers.add_parser("init", help="Explicit offline operator initialization")
    initialize.add_argument("--directory", required=True)
    initialize.add_argument("--day-key", required=True)
    initialize.add_argument("--month-key", required=True)
    initialize.add_argument("--day-used", required=True, type=int)
    initialize.add_argument("--month-used", required=True, type=int)
    initialize.add_argument("--confirm-audited-baseline", action="store_true", required=True)
    args = parser.parse_args()
    try:
        if args.command == "init":
            initialize_host_ai_budget(
                args.directory, day_key=args.day_key, month_key=args.month_key,
                day_used=args.day_used, month_used=args.month_used,
                confirmation=INITIALIZATION_CONFIRMATION if args.confirm_audited_baseline else "",
            )
            print(json.dumps({"status": "initialized", "owner_audit_verified": False}))
        else:
            print(json.dumps({
                "status": "refused_until_independent_audit_and_explicit_initialization",
                "paid_capacity_granted": 0,
                "execution_limit": EXECUTION_LIMIT,
                "daily_limit": DAILY_LIMIT,
                "monthly_limit": MONTHLY_LIMIT,
                "conservative_baseline_day": DAILY_LIMIT,
                "conservative_baseline_month": MONTHLY_LIMIT,
                "owner_audit_verified": False,
            }, sort_keys=True))
        return 0
    except HostAIBudgetError as error:
        print(json.dumps({"status": "refused", "code": error.code}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
