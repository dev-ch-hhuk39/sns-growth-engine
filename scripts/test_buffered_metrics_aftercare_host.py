#!/usr/bin/env python3
"""Action-free metrics-aftercare host policy tests (offline, no provider access).

Test only the pure local --plan branch and preflight denials. Live lock,
credentials and Sheets flows require explicit separate VPS Ops validation.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
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
    def test_shell_tracing_cannot_print_protected_runtime_credentials(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent=Path(temporary).resolve()
            runtime=parent/'runtime'
            revision='a'*40
            release=runtime/'releases'/revision
            (release/'scripts').mkdir(parents=True)
            (release/'scripts/process_threads_metric_jobs.py').touch()
            (release/'.production-release').write_text(revision+'\n')
            (release/'.venv/bin').mkdir(parents=True)
            interpreter=release/'.venv/bin/python'
            interpreter.write_text('#!/bin/sh\nexit 99\n');interpreter.chmod(0o700)
            (runtime/'current').symlink_to(release)
            shared=runtime/'shared';shared.mkdir()
            private=shared/'runtime.env'
            sentinel='protected-aftercare-fixture-value'
            private.write_text('GEMINI_API_KEY='+sentinel+'\n')
            private.chmod(0o600)
            lock=parent/'deploy.lock';lock.touch()
            host=parent/'host.sh'
            host.write_text(HOST.read_text().replace('/run/lock/chadult-production-deploy.lock',str(lock)))
            binaries=parent/'bin';binaries.mkdir()
            flock=binaries/'flock';flock.write_text('#!/bin/sh\nexit 0\n');flock.chmod(0o700)
            readlink=binaries/'readlink'
            readlink.write_text('#!'+sys.executable+'\nimport os,sys\nprint(os.path.realpath(sys.argv[-1]))\n')
            readlink.chmod(0o700)
            result=subprocess.run(['bash','-x',str(host),'--account-id','night_scout','--apply','--confirm-metrics'],
                env={'PATH':str(binaries)+os.pathsep+os.environ['PATH'],
                     'BUFFERED_RUNTIME_ROOT':str(runtime)},capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,77,result.stderr)
            self.assertIn('independent metrics write approval',result.stderr)
            self.assertNotIn(sentinel,result.stdout+result.stderr)

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
        self.assertIn('exec 9>"$sheet_lock"', host)
        self.assertIn('flock -w 240 9', host)
        self.assertIn('exec 7>"$account_lock"', host)
        self.assertIn('flock -n -E 75 7', host)
        self.assertLess(
            host.index('flock -w 240 9'),
            host.index('--max-jobs 20 --dry-run --use-sheets'),
        )
        self.assertIn("chadult-production-deploy.lock", host)
        self.assertIn("sheets-io.lock", host)
        self.assertIn("--trigger xserver_cron", poster.replace(
            'case "$TRIGGER" in xserver_cron', "--trigger xserver_cron"
        ))
        self.assertLess(
            host.index('flock -s -w 120 8'),
            host.index('resolved="$(readlink -f "$release")"'),
        )

    def test_feedback_plan_is_still_offline(self):
        result = execute(
            "--account-id", "night_scout", "--with-feedback-preview",
        )
        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["feedback_preview"])
        self.assertEqual(payload["feedback_stages"], [
            "measured_attribution", "next_text_ready_coverage",
        ])
        self.assertFalse(payload["would_connect"])
        self.assertFalse(payload["would_write"])

    def test_feedback_stages_are_strictly_read_only_and_after_metrics(self):
        source = HOST.read_text(encoding="utf-8")
        self.assertEqual(source.count('if [[ "$feedback_preview" == true ]]'), 1)
        self.assertLess(
            source.index("--apply --confirm-metrics --use-sheets"),
            source.rindex("run_growth_attribution_cycle.py"),
        )
        self.assertIn("run_growth_attribution_cycle.py", source)
        self.assertIn("maintain_text_ready_inventory.py", source)
        # Read-only preview section must never gain an apply confirmation.
        readonly_tail = source.split(
            'if [[ "$feedback_preview" == true ]]', 1,
        )[1]
        self.assertNotIn("--confirm-attribution", readonly_tail)
        self.assertNotIn("--confirm-ready-maintenance", readonly_tail)
        self.assertIn("export GEMINI_API_KEY=", source)
        self.assertNotIn("run_pdca_cycle.py", source)
        self.assertNotIn("prepare_beauty_review_candidates.py", source)

    def test_feedback_write_modes_refuse_non_manual_or_non_apply_invocations(self):
        bad_cases = (
            ("--with-strategy-apply",),
            ("--with-ready-bank-reuse",),
            ("--dry-run", "--confirm-readonly", "--with-strategy-apply"),
            ("--dry-run", "--confirm-readonly", "--with-ready-bank-reuse"),
            ("--apply", "--confirm-metrics", "--trigger", "xserver_cron",
             "--with-strategy-apply"),
            ("--apply", "--confirm-metrics", "--trigger", "xserver_cron",
             "--with-ready-bank-reuse"),
            ("--max-bank-allocations", "7"),
            ("--max-bank-allocations", "-1"),
            ("--max-bank-allocations", "2; echo injection"),
        )
        for args in bad_cases:
            with self.subTest(args=args):
                result = execute("--account-id", "night_scout", *args)
                self.assertEqual(result.returncode, 64, result.stderr)
                self.assertEqual(result.stdout, "")

    def test_feedback_write_activation_requires_ops_private_env(self):
        for stage in ("--with-strategy-apply", "--with-ready-bank-reuse"):
            with self.subTest(stage=stage):
                result = execute(
                    "--account-id", "night_scout", "--apply",
                    "--confirm-metrics", "--trigger", "manual", stage,
                    extra_env={
                        "AFTERCARE_METRICS_WRITE_APPROVED": "true",
                        "AFTERCARE_ACTIONS_DISABLED_ATTESTED": "true",
                        "AFTERCARE_STRATEGY_WRITE_APPROVED": "true",
                        "AFTERCARE_READY_BANK_REUSE_APPROVED": "true",
                    },
                )
                # The untrusted process env is never a grant; no immutable
                # ops provisioned runtime exists in this offline test.
                self.assertEqual(result.returncode, 78)
                self.assertEqual(result.stdout, "")

    def test_strategy_and_ready_approval_are_separate_and_zero_ai(self):
        host = HOST.read_text(encoding="utf-8")
        for name in (
            "AFTERCARE_STRATEGY_WRITE_APPROVED",
            "AFTERCARE_READY_BANK_REUSE_APPROVED",
        ):
            self.assertIn(f"unset {name}", host)
            self.assertIn(f'${{{name}:-false}}', host)
        self.assertIn("--apply --confirm-attribution --use-sheets", host)
        self.assertIn("--max-write-rows 120", host)
        self.assertIn("--apply --confirm-ready-maintenance", host)
        self.assertIn("--use-sheets --reuse-only", host)
        self.assertIn('--max-bank-allocations "$bank_allocations"', host)
        self.assertIn("export GEMINI_API_KEY=", host)
        self.assertLess(
            host.index("process_threads_metric_jobs.py"),
            host.index("run_growth_attribution_cycle.py"),
        )
        self.assertNotIn("workflow_dispatch", host)

    def test_no_actions_scheduler_install_or_media_publisher_calls(self):
        host = HOST.read_text(encoding="utf-8")
        for forbidden in (
            "gh workflow", "workflow_dispatch", "git push",
            "crontab -", "install_buffered_production_runtime.sh",
            "reconcile_due_production_slots.py",
            "collect_video_references.py", "run_media_production_pipeline.py",
             "run_pdca_cycle.py",
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
