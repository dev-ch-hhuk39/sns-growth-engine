#!/usr/bin/env python3
"""Action-free metrics-aftercare host policy tests (offline, no provider access).

Test only the pure local --plan branch and preflight denials. Live lock,
credentials and Sheets flows require explicit separate VPS Ops validation.
"""
from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / "scripts" / "run_buffered_metrics_aftercare_host.sh"
PUBLISHER = ROOT / "scripts" / "run_buffered_production_host.sh"


def execute(*args: str, extra_env: dict[str, str] | None = None):
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": "/tmp",
        "BUFFERED_RUNTIME_ROOT": "/nonexistent/no-vps-runtime",
        "AFTERCARE_METRICS_WRITE_APPROVED": "true",
        "PUBLISH_ENABLED": "true",
        "ALLOW_REAL_THREADS_POST": "true",
    }
    env.update(extra_env or {})
    return subprocess.run(
        ["bash", str(HOST), *args],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=8,
        check=False,
    )


class MetricsAftercareNoActionsTests(unittest.TestCase):
    def test_only_intended_accounts_have_offline_plans(self):
        for account in ("night_scout", "liver_manager"):
            with self.subTest(account=account):
                result = execute("--account-id", account)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, "")
                parsed = json.loads(result.stdout)
                self.assertEqual(parsed["status"], "PLAN_ONLY")
                self.assertEqual(parsed["account_id"], account)
                self.assertEqual(parsed["stage"], "metrics_24_72_168")
                self.assertFalse(parsed["would_connect"])
                self.assertFalse(parsed["would_write"])
                self.assertFalse(parsed["would_post"])
                self.assertFalse(parsed["github_actions_used"])

    def test_cron_plan_is_offline_and_non_mutating(self):
        result = execute(
            "--account-id", "night_scout", "--plan", "--trigger", "xserver_cron",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["trigger"], "xserver_cron")
        self.assertNotIn("GCP_SA_JSON", result.stdout)

    def test_public_environment_cannot_activate_plan(self):
        result = execute(
            "--account-id", "night_scout",
            extra_env={"AFTERCARE_METRICS_WRITE_APPROVED": "true"},
        )
        self.assertEqual(json.loads(result.stdout)["status"], "PLAN_ONLY")

    def test_beauty_all_and_unexpected_accounts_block(self):
        for account in ("beauty_account", "all", "unknown", "../night_scout", ""):
            with self.subTest(account=account):
                result = execute("--account-id", account)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("PLAN_ONLY", result.stdout)

    def test_readonly_live_mode_requires_explicit_readonly_ack(self):
        result = execute("--account-id", "night_scout", "--dry-run")
        self.assertEqual(result.returncode, 64)
        self.assertIn("--confirm-readonly", result.stderr)

    def test_apply_requires_two_independent_gates(self):
        result = execute("--account-id", "liver_manager", "--apply")
        self.assertEqual(result.returncode, 64)
        self.assertIn("--confirm-metrics", result.stderr)
        result = execute(
            "--account-id", "liver_manager", "--apply", "--confirm-metrics",
        )
        # Even with untrusted process env set to "true", there is no
        # installed immutable release or service-account secret.
        self.assertEqual(result.returncode, 78)
        self.assertEqual(result.stdout, "")
        self.assertNotIn("AFTERCARE_METRICS_WRITE_APPROVED=true", result.stderr)

    def test_readonly_dryrun_requires_installed_vps_runtime(self):
        result = execute(
            "--account-id", "night_scout",
            "--dry-run", "--confirm-readonly",
        )
        self.assertEqual(result.returncode, 78)
        self.assertEqual(result.stdout, "")

    def test_no_confirmation_mixing_or_unexpected_trigger(self):
        for args in (
            ("--apply", "--confirm-metrics", "--confirm-readonly"),
            ("--dry-run", "--confirm-readonly", "--confirm-metrics"),
            ("--plan", "--confirm-metrics"),
            ("--trigger", "github_schedule_recovery"),
            ("--trigger", "github_actions"),
            ("--dry-run", "--apply"),
        ):
            with self.subTest(args=args):
                result = execute("--account-id", "night_scout", *args)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("PLAN_ONLY", result.stdout)

    def test_host_only_invokes_metric_worker_and_shared_runtime_locks(self):
        host = HOST.read_text(encoding="utf-8")
        poster = PUBLISHER.read_text(encoding="utf-8")
        self.assertIn("process_threads_metric_jobs.py", host)
        self.assertIn("--max-jobs 20 --dry-run --use-sheets", host)
        self.assertIn(
            "--max-jobs 20 --apply --confirm-metrics --use-sheets", host,
        )
        self.assertIn("AFTERCARE_METRICS_WRITE_APPROVED", host)
        self.assertIn("unset AFTERCARE_METRICS_WRITE_APPROVED", host)
        self.assertIn("unset AFTERCARE_ACTIONS_DISABLED_ATTESTED", host)
        self.assertIn("AFTERCARE_ACTIONS_DISABLED_ATTESTED", host)
        self.assertIn("CODE_REVISION", host)
        self.assertIn('flock -s -w 120 8', host)
        self.assertIn('flock -w 240 "$sheet_lock"', host)
        self.assertIn('flock -n -E 75 "$account_lock"', host)
        self.assertIn("chadult-production-deploy.lock", host)
        self.assertIn("sheets-io.lock", host)
        self.assertIn("--trigger xserver_cron", poster.replace(
            'case "$TRIGGER" in xserver_cron', "--trigger xserver_cron"
        ))
        self.assertLess(
            host.index('flock -s -w 120 8'),
            host.index('resolved="$(readlink -f "$release")"'),
        )

    def test_no_actions_scheduler_install_or_media_publisher_calls(self):
        host = HOST.read_text(encoding="utf-8")
        for forbidden in (
            "gh workflow", "workflow_dispatch", "git push",
            "crontab -", "install_buffered_production_runtime.sh",
            "reconcile_due_production_slots.py",
            "collect_video_references.py", "run_media_production_pipeline.py",
            "run_pdca_cycle.py", "maintain_text_ready_inventory.py",
        ):
            self.assertNotIn(forbidden, host)
        for key in (
            "export PUBLISH_ENABLED=false",
            "export ALLOW_REAL_THREADS_POST=false",
            "export ALLOW_MEDIA_POSTS=false",
            "export GEMINI_API_KEY=\"\"",
        ):
            self.assertIn(key, host)


if __name__ == "__main__":
    unittest.main()
