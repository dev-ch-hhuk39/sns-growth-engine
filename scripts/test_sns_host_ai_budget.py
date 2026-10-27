#!/usr/bin/env python3
"""Offline durable-budget tests; never invoke providers or a live ledger."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))
import sns_host_ai_budget as budget  # noqa: E402


NOW = datetime(2026, 10, 27, 12, tzinfo=budget.JST)
RELEASE = "a" * 40
ACCOUNTS = ("night_scout", "liver_manager", "beauty_account")
ENV_NAMES = (
    "SNS_HOST_AI_BUDGET_REQUIRED", "SNS_HOST_AI_BUDGET_DIR", "SNS_HOST_AI_RUN_ID",
    "SNS_HOST_AI_ACCOUNT_ID", "SNS_HOST_AI_RELEASE",
)
CHILD = """
import json
import sys
from datetime import datetime
import sns_host_ai_budget as budget
budget._now_jst = lambda: datetime(2026, 10, 27, 12, tzinfo=budget.JST)
allowed = 0
codes = []
for _ in range(int(sys.argv[1])):
    try:
        budget.reserve_host_ai_attempt(sys.argv[2], 'offline.test')
        allowed += 1
    except budget.HostAIBudgetError as error:
        codes.append(error.code)
print(json.dumps({'allowed': allowed, 'codes': codes}))
"""


class HostAIBudgetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name).resolve()
        self.directory.chmod(0o700)
        self.environment = mock.patch.dict(os.environ, {}, clear=False)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        for name in ENV_NAMES:
            os.environ.pop(name, None)
        self.clock = mock.patch.object(budget, "_now_jst", return_value=NOW)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.pin()

    def pin(self, account: str = ACCOUNTS[0], run: int = 1, release: str = RELEASE) -> None:
        os.environ.update(self.child_environment(account, run, release))

    def child_environment(
        self, account: str = ACCOUNTS[0], run: int = 1, release: str = RELEASE,
    ) -> dict[str, str]:
        return {
            "PYTHONPATH": str(SRC),
            "SNS_HOST_AI_BUDGET_REQUIRED": "true",
            "SNS_HOST_AI_BUDGET_DIR": str(self.directory),
            "SNS_HOST_AI_RUN_ID": f"{run:032x}",
            "SNS_HOST_AI_ACCOUNT_ID": account,
            "SNS_HOST_AI_RELEASE": release,
        }

    def initialize(self, day: int = 0, month: int = 0, **kwargs: object) -> None:
        arguments = {
            "day_key": "2026-10-27", "month_key": "2026-10",
            "day_used": day, "month_used": month,
            "confirmation": budget.INITIALIZATION_CONFIRMATION,
        }
        arguments.update(kwargs)
        budget.initialize_host_ai_budget(str(self.directory), **arguments)

    def reserve(self, account: str = ACCOUNTS[0]) -> None:
        budget.reserve_host_ai_attempt(account, "offline.test")

    def count(self) -> int:
        with closing(sqlite3.connect(self.directory / budget.DB_NAME)) as connection:
            return connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]

    def blocked(self, code: str, function=None) -> None:
        with self.assertRaises(budget.HostAIBudgetError) as caught:
            (function or self.reserve)()
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(str(caught.exception), "sns_host_ai_budget:" + code)

    def child(self, *, account: str = ACCOUNTS[0], run: int = 1, count: int = 1) -> dict:
        result = subprocess.run(
            [sys.executable, "-c", CHILD, str(count), account],
            env=self.child_environment(account, run), capture_output=True, text=True, check=True,
            timeout=45,
        )
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout)

    def test_disabled_legacy_mode_does_not_inspect_or_create_state(self) -> None:
        for mode in (None, "false", "0", "FALSE"):
            if mode is None:
                os.environ.pop("SNS_HOST_AI_BUDGET_REQUIRED", None)
            else:
                os.environ["SNS_HOST_AI_BUDGET_REQUIRED"] = mode
            os.environ["SNS_HOST_AI_BUDGET_DIR"] = "/nonexistent/offline"
            budget.reserve_host_ai_attempt("", "")
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_invalid_modes_fail_closed(self) -> None:
        for mode in ("", "yes", " true", "false ", "2"):
            os.environ["SNS_HOST_AI_BUDGET_REQUIRED"] = mode
            self.blocked("invalid_mode")
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_missing_or_malformed_context_is_refused(self) -> None:
        for name in ENV_NAMES[1:]:
            with self.subTest(name=name), mock.patch.dict(os.environ, {name: ""}):
                self.blocked("invalid_context")
        for name, value in (
            ("SNS_HOST_AI_RUN_ID", "A" * 32),
            ("SNS_HOST_AI_RUN_ID", "1" * 31),
            ("SNS_HOST_AI_RELEASE", "a" * 39),
            ("SNS_HOST_AI_RELEASE", "A" * 40),
            ("SNS_HOST_AI_ACCOUNT_ID", "unknown"),
        ):
            with self.subTest(name=name, value=value), mock.patch.dict(os.environ, {name: value}):
                self.blocked("invalid_context")

    def test_account_operation_and_scope_denials_consume_nothing(self) -> None:
        self.initialize()
        self.blocked("account_mismatch", lambda: self.reserve(ACCOUNTS[1]))
        for account in (None, "", "unknown"):
            self.blocked("account_mismatch", lambda: self.reserve(account))
        for operation in ("", "prompt with spaces", "x" * 65, None):
            self.blocked("invalid_context", lambda: budget.reserve_host_ai_attempt(ACCOUNTS[0], operation))
        self.assertEqual(self.count(), 0)
        self.reserve()
        self.pin(ACCOUNTS[1])
        self.blocked("run_scope_mismatch", lambda: self.reserve(ACCOUNTS[1]))
        self.pin(release="b" * 40)
        self.blocked("run_scope_mismatch")
        self.assertEqual(self.count(), 1)

    def test_absent_database_never_bootstraps_or_grants(self) -> None:
        self.blocked("uninitialized")
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_initialization_requires_current_explicit_audited_baseline(self) -> None:
        self.blocked("initialization_confirmation_required", lambda: self.initialize(confirmation=""))
        cases = (
            {"day_key": "2026-10-26"}, {"month_key": "2026-09"},
            {"day_used": -1}, {"day_used": 41, "month_used": 41},
            {"day_used": 2, "month_used": 1}, {"month_used": 1001},
            {"day_used": True}, {"month_used": "0"},
        )
        for arguments in cases:
            with self.subTest(arguments=arguments):
                self.blocked("invalid_baseline", lambda: self.initialize(**arguments))
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_existing_database_cannot_be_reinitialized(self) -> None:
        self.initialize()
        self.reserve()
        self.blocked("already_initialized", self.initialize)
        self.assertEqual(self.count(), 1)

    def test_seeded_usage_is_enforced_without_refunds(self) -> None:
        self.initialize(38, 998)
        self.reserve()
        self.reserve()
        self.blocked("daily_limit")
        self.assertEqual(self.count(), 2)

    def test_exhausted_baselines_grant_zero(self) -> None:
        self.initialize(40, 1000)
        self.blocked("daily_limit")
        self.assertEqual(self.count(), 0)

    def test_month_limit_shared_across_accounts_and_days(self) -> None:
        self.initialize(0, 999)
        self.reserve()
        self.pin(ACCOUNTS[1], 2)
        with mock.patch.object(budget, "_now_jst", return_value=datetime(2026, 10, 28, tzinfo=budget.JST)):
            self.blocked("monthly_limit", lambda: self.reserve(ACCOUNTS[1]))
        self.assertEqual(self.count(), 1)

    def test_daily_limit_shared_across_all_three_accounts(self) -> None:
        self.initialize()
        for index, account in enumerate(ACCOUNTS):
            self.pin(account, index + 1)
            for _ in range((20, 19, 1)[index]):
                self.reserve(account)
        self.pin(ACCOUNTS[2], 4)
        self.blocked("daily_limit", lambda: self.reserve(ACCOUNTS[2]))
        self.assertEqual(self.count(), 40)

    def test_execution_limit_persists_across_fresh_processes(self) -> None:
        self.initialize()
        self.assertEqual(self.child(count=11), {"allowed": 11, "codes": []})
        self.assertEqual(self.child(count=10), {"allowed": 9, "codes": ["execution_limit"]})
        self.assertEqual(self.child(), {"allowed": 0, "codes": ["execution_limit"]})
        self.assertEqual(self.count(), 20)

    def test_daily_and_monthly_baselines_persist_across_fresh_processes(self) -> None:
        self.initialize(39, 999)
        self.assertEqual(self.child(account=ACCOUNTS[1], run=2)["allowed"], 1)
        self.assertEqual(self.child(account=ACCOUNTS[2], run=3), {"allowed": 0, "codes": ["daily_limit"]})
        self.assertEqual(self.count(), 1)

    def test_concurrent_fresh_processes_cannot_exceed_global_cap(self) -> None:
        self.initialize(30, 990)
        with ThreadPoolExecutor(max_workers=12) as executor:
            results = list(executor.map(
                lambda index: self.child(account=ACCOUNTS[index % 3], run=index + 1), range(12)
            ))
        self.assertEqual(sum(result["allowed"] for result in results), 10)
        self.assertEqual(sum(len(result["codes"]) for result in results), 2)
        self.assertEqual(self.count(), 10)

    def test_concurrent_fresh_processes_cannot_exceed_run_cap(self) -> None:
        self.initialize()
        self.assertEqual(self.child(count=19)["allowed"], 19)
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda _: self.child(), range(8)))
        self.assertEqual(sum(result["allowed"] for result in results), 1)
        self.assertEqual(
            [code for result in results for code in result["codes"]],
            ["execution_limit"] * 7,
        )
        self.assertEqual(self.count(), 20)

    def test_jst_day_and_month_rollover_uses_durable_history(self) -> None:
        self.initialize(40, 1000)
        # 15:00 UTC is midnight in JST. A new day cannot reset the month.
        with mock.patch.object(budget, "_now_jst", return_value=datetime(2026, 10, 27, 15, tzinfo=timezone.utc)):
            self.blocked("monthly_limit")
        with mock.patch.object(budget, "_now_jst", return_value=datetime(2026, 10, 31, 15, tzinfo=timezone.utc)):
            self.reserve()
        self.assertEqual(self.count(), 1)
        # Old audited periods cannot be selected again by rolling the clock back.
        self.blocked("clock_rollback")

    def test_execution_budget_does_not_reset_on_jst_rollover(self) -> None:
        self.initialize()
        for _ in range(20):
            self.reserve()
        with mock.patch.object(budget, "_now_jst", return_value=datetime(2026, 11, 1, tzinfo=budget.JST)):
            self.blocked("execution_limit")

    def test_naive_clock_fails_closed(self) -> None:
        self.initialize()
        with mock.patch.object(budget, "_now_jst", return_value=datetime(2026, 10, 28)):
            self.blocked("invalid_clock")
        self.assertEqual(self.count(), 0)

    def test_unsafe_directory_paths_modes_and_symlinks(self) -> None:
        self.directory.chmod(0o755)
        self.blocked("unsafe_directory")
        self.directory.chmod(0o700)
        for path in ("relative", str(self.directory) + "/../x", "/"):
            with mock.patch.dict(os.environ, {"SNS_HOST_AI_BUDGET_DIR": path}):
                self.blocked("unsafe_directory")
        sibling = self.directory.parent / (self.directory.name + "-link")
        sibling.symlink_to(self.directory, target_is_directory=True)
        self.addCleanup(sibling.unlink)
        with mock.patch.dict(os.environ, {"SNS_HOST_AI_BUDGET_DIR": str(sibling)}):
            self.blocked("storage_unavailable")

    def test_database_and_lock_permissions_are_private(self) -> None:
        self.initialize()
        for name in (budget.DB_NAME, budget.LOCK_NAME):
            path = self.directory / name
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            path.chmod(0o640)
            self.blocked("unsafe_file")
            path.chmod(0o600)
        self.assertEqual(self.count(), 0)

    def test_db_symlink_hardlink_and_unknown_sidecar_fail_closed(self) -> None:
        self.initialize()
        db = self.directory / budget.DB_NAME
        saved = self.directory.parent / (self.directory.name + "-saved")
        db.rename(saved)
        self.addCleanup(lambda: saved.unlink(missing_ok=True))
        db.symlink_to(saved)
        self.blocked("unsafe_file")
        db.unlink()
        os.link(saved, db)
        self.blocked("unsafe_file")
        db.unlink()
        saved.rename(db)
        sidecar = self.directory / (budget.DB_NAME + "-wal")
        sidecar.touch(mode=0o600)
        self.blocked("unexpected_files")

    def test_foreign_owner_is_rejected_without_chown(self) -> None:
        info = (self.directory).stat()
        values = list(info)
        values[4] = os.geteuid() + 1
        with self.assertRaises(budget.HostAIBudgetError) as caught:
            budget._check_directory(os.stat_result(values), private=True)
        self.assertEqual(caught.exception.code, "unsafe_directory")

    def test_corrupt_and_empty_database_fail_closed(self) -> None:
        self.initialize()
        db = self.directory / budget.DB_NAME
        db.write_bytes(b"not a sqlite database")
        self.blocked("storage_unavailable")
        self.blocked("already_initialized", self.initialize)
        db.write_bytes(b"")
        self.blocked("invalid_schema")

    def test_foreign_schema_or_invalid_history_fail_closed(self) -> None:
        self.initialize()
        self.reserve()
        db = self.directory / budget.DB_NAME
        with closing(sqlite3.connect(db)) as connection, connection:
            connection.execute("CREATE TABLE foreign_table (value TEXT)")
        self.blocked("invalid_schema")
        with closing(sqlite3.connect(db)) as connection, connection:
            connection.execute("DROP TABLE foreign_table")
            connection.execute("DELETE FROM attempts")
        self.blocked("invalid_ledger")

    def test_fsync_failure_denies_transport_but_does_not_refund(self) -> None:
        self.initialize()
        with mock.patch.object(budget.os, "fsync", side_effect=OSError("sensitive raw detail")):
            self.blocked("storage_unavailable")
        self.assertEqual(self.count(), 1)

    def test_payload_operation_and_environment_are_not_persisted(self) -> None:
        self.initialize()
        with mock.patch.dict(os.environ, {"OFFLINE_TEST_SECRET": "sensitive-raw-test-marker"}):
            budget.reserve_host_ai_attempt(ACCOUNTS[0], "never.persist.operation")
        raw = (self.directory / budget.DB_NAME).read_bytes()
        self.assertNotIn(b"never.persist.operation", raw)
        self.assertNotIn(b"sensitive-raw-test-marker", raw)

    def test_default_cli_plan_never_inspects_ledger(self) -> None:
        env = self.child_environment()
        env["SNS_HOST_AI_BUDGET_DIR"] = "/nonexistent/offline"
        result = subprocess.run(
            [sys.executable, str(SRC / "sns_host_ai_budget.py")], env=env,
            capture_output=True, text=True, check=True, timeout=10,
        )
        plan = json.loads(result.stdout)
        self.assertEqual(plan["paid_capacity_granted"], 0)
        self.assertFalse(plan["owner_audit_verified"])
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_cli_init_cannot_omit_confirmation_or_counts(self) -> None:
        for flags in ([], ["--day-used", "0", "--month-used", "0"]):
            result = subprocess.run(
                [sys.executable, str(SRC / "sns_host_ai_budget.py"), "init",
                 "--directory", str(self.directory), "--day-key", "2026-10-27",
                 "--month-key", "2026-10", *flags],
                env={"PYTHONPATH": str(SRC)}, capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.returncode, 2)
        self.assertEqual(list(self.directory.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
