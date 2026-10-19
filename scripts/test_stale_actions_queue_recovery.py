#!/usr/bin/env python3
"""Offline-only tests; no GitHub cancel operation or real network access."""
from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import yaml

import reconcile_stale_actions_queue as recovery

NOW = datetime(2026, 10, 19, 2, 0, tzinfo=timezone.utc)
TARGET_ID = 37327934561
RUN = {
    "name": "Publication Review Board", "event": "schedule",
    "head_sha": "4aa37f5c6409e0d9faa6d1e3e90d248f1984ced3",
    "status": "queued", "conclusion": None, "run_attempt": 1,
    "repository": {"full_name": recovery.REPOSITORY},
    "created_at": "2026-10-05T14:50:11Z",
}
JOBS = {
    "total_count": 1, "jobs": [
        {"status": "queued", "started_at": None,
         "completed_at": None, "conclusion": None},
    ],
}


class FakeApi:
    def __init__(self, run=None, jobs=None, second_run=None, second_jobs=None):
        self.run = run if run is not None else dict(RUN)
        self.jobs = jobs if jobs is not None else dict(JOBS)
        self.second_run = second_run
        self.second_jobs = second_jobs
        self.get_calls = 0
        self.canceled: list[int] = []

    def snapshot(self, run_id):
        self.get_calls += 1
        if self.get_calls == 2 and self.second_run is not None:
            return self.second_run, self.second_jobs
        return self.run, self.jobs

    def cancel(self, run_id):
        self.canceled.append(run_id)


class StaleQueueRecoveryTests(unittest.TestCase):
    def test_verified_old_never_started_job_can_be_requested_once(self):
        api = FakeApi()
        result = recovery.assess_and_cancel(api, TARGET_ID, apply=True, now=NOW)
        self.assertEqual(result["status"], "CANCEL_REQUESTED_NOT_YET_CONFIRMED")
        self.assertEqual(api.canceled, [TARGET_ID])
        self.assertEqual(api.get_calls, 2)

    def test_dry_run_never_cancels(self):
        api = FakeApi()
        result = recovery.assess_and_cancel(api, TARGET_ID, apply=False, now=NOW)
        self.assertEqual(result["status"], "DRY_RUN_ELIGIBLE")
        self.assertEqual(api.canceled, [])

    def test_recent_or_running_run_is_not_eligible(self):
        self.assertEqual(
            recovery.eligible(TARGET_ID, RUN, JOBS,
                              datetime(2026, 10, 5, 15, 0, tzinfo=timezone.utc)),
            "RUN_TOO_RECENT",
        )
        for status in ("in_progress", "completed"):
            run = {**RUN, "status": status}
            self.assertEqual(recovery.eligible(TARGET_ID, run, JOBS, NOW), "RUN_NOT_QUEUED")

    def test_existing_started_job_or_partial_job_list_blocks(self):
        started = {"total_count": 1, "jobs": [
            {"status": "in_progress", "started_at": "2026-10-15T00:00:00Z",
             "completed_at": None, "conclusion": None},
        ]}
        self.assertEqual(recovery.eligible(TARGET_ID, RUN, started, NOW),
                         "JOB_ALREADY_STARTED_OR_FINISHED")
        self.assertEqual(recovery.eligible(TARGET_ID, RUN, {"total_count": 2, "jobs": []}, NOW),
                         "JOB_LIST_INCOMPLETE")

    def test_wrong_repository_sha_event_or_id_is_rejected(self):
        self.assertEqual(recovery.eligible(99999, RUN, JOBS, NOW), "UNLISTED_RUN_BLOCKED")
        for key, wrong in [
            ("head_sha", "00bad"),
            ("event", "workflow_dispatch"),
            ("repository", {"full_name": "other/owner"}),
        ]:
            self.assertEqual(recovery.eligible(TARGET_ID, {**RUN, key: wrong}, JOBS, NOW),
                             "RUN_IDENTITY_MISMATCH")

    def test_changed_or_moving_target_cannot_be_canceled(self):
        changed = {**RUN, "status": "in_progress"}
        api = FakeApi(second_run=changed, second_jobs=JOBS)
        result = recovery.assess_and_cancel(api, TARGET_ID, apply=True, now=NOW)
        self.assertEqual(result["status"], "SKIPPED_CHANGED_BEFORE_CANCEL")
        self.assertEqual(api.canceled, [])

    def test_main_push_and_gate_required_for_apply(self):
        with patch.dict("os.environ", {
            "GITHUB_REPOSITORY": recovery.REPOSITORY,
            "GH_ACTIONS_TOKEN": "fake-do-not-log",
            "SNS_QUEUE_RECOVERY_ALLOWED": "true",
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_REF": "refs/heads/main",
        }):
            with patch("builtins.print") as output:
                code = recovery.main(["--apply", "--confirm-stale-run-cancel"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.call_args.args[0])["status"], "BLOCKED")

    def test_workflow_runs_only_on_trusted_main_push_with_minimal_permission(self):
        root = Path(__file__).resolve().parents[1]
        workflow = root / ".github" / "workflows" / "sns-stale-actions-queue-recovery.yml"
        raw = workflow.read_text(encoding="utf-8")
        spec = yaml.safe_load(raw)
        job = spec["jobs"]["inspect-stale-runs"]
        self.assertEqual(job["runs-on"], "ubuntu-latest")
        self.assertEqual(job["permissions"], {"contents": "read", "actions": "write"})
        self.assertIn("branches: [main]", raw)
        self.assertIn("paths:", raw)
        self.assertNotIn("  schedule:", raw)
        self.assertIn("github.event_name == 'push'", raw)
        self.assertIn("github.event_name == 'workflow_dispatch'", raw)
        self.assertIn("--apply --confirm-stale-run-cancel", raw)

    def test_only_normal_cancel_endpoint_no_force_cancel_or_external_send(self):
        script = Path(recovery.__file__).read_text(encoding="utf-8")
        self.assertIn('"/cancel"', script)
        self.assertNotIn('"\u002fforce-cancel"', script)
        self.assertNotIn("graph.threads.net", script)
        self.assertNotIn("posted_results", script)
        self.assertNotIn("secrets.GH_SECRET_WRITE_TOKEN", script)


if __name__ == "__main__":
    unittest.main()
