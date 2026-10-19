#!/usr/bin/env python3
"""Offline and adversarial tests for one immutable queued review cancellation."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cancel_exact_stale_review_once as repair

NOW = datetime(2026, 10, 19, tzinfo=timezone.utc)


def run(*, status="queued", conclusion=None, run_id=repair.RUN_ID) -> dict:
    return {
        "id": run_id, "name": "Publication Review Board", "event": "schedule",
        "head_sha": repair.EXPECTED_SHA, "repository": {"full_name": repair.REPO},
        "created_at": repair.EXPECTED_CREATED, "run_attempt": 1,
        "status": status, "conclusion": conclusion,
    }


def jobs(**extra) -> dict:
    one = {
        "id": repair.JOB_ID, "name": "sync", "status": "queued",
        "conclusion": None, "completed_at": None, "runner_name": None,
        "started_at": repair.EXPECTED_JOB_STARTED, "steps": [],
    }
    one.update(extra)
    return {"total_count": 1, "jobs": [one]}


def shot(*, complete=False, **job_overrides) -> tuple[dict, dict]:
    return run(status="completed" if complete else "queued",
               conclusion="cancelled" if complete else None), jobs(**job_overrides)


class FakeClient:
    def __init__(self, snapshots):
        self.snapshots = snapshots
        self.idx = 0
        self.actions = []

    def snapshot(self):
        value = self.snapshots[min(self.idx, len(self.snapshots)-1)]
        self.idx += 1
        return copy.deepcopy(value)

    def cancel(self, *, force):
        self.actions.append("force" if force else "normal")


class StaleReviewReliefTests(unittest.TestCase):
    def test_known_queued_job_has_fabricated_start_marker_but_no_runner(self):
        self.assertEqual(repair.safe_to_cancel(*shot(), now=NOW), "EXACT_STALE_UNSTARTED")
        self.assertEqual(repair.safe_to_cancel(*shot(), now=datetime(2026,10,6,tzinfo=timezone.utc)),
                         "RUN_TOO_YOUNG")

    def test_only_target_run_and_sha_are_eligible(self):
        bad = run(run_id=333)
        self.assertEqual(repair.safe_to_cancel(bad, jobs(), now=NOW), "RUN_IDENTITY_MISMATCH")
        bad = run()
        bad["head_sha"] = "0" * 40
        self.assertEqual(repair.safe_to_cancel(bad, jobs(), now=NOW), "RUN_IDENTITY_MISMATCH")
        bad = run()
        bad["run_attempt"] = 2
        self.assertEqual(repair.safe_to_cancel(bad, jobs(), now=NOW), "RUN_IDENTITY_MISMATCH")

    def test_previously_started_or_changed_job_is_never_cancelled(self):
        for new in (
            {"runner_name": "hosted-runner-1"},
            {"steps": [{"name": "checkout", "status": "completed"}]},
            {"started_at": "2026-10-05T15:05:12Z"},
            {"conclusion": "success"},
            {"completed_at": "2026-10-05T16:00:00Z"},
            {"status": "in_progress"},
        ):
            self.assertEqual(repair.safe_to_cancel(*shot(**new), now=NOW),
                             "JOB_STARTED_OR_CHANGED")

    def test_already_cancelled_is_idempotent(self):
        client = FakeClient([shot(complete=True)])
        out = repair.cancel_exact_stale_review(client, now=NOW, sleeper=lambda _: None)
        self.assertEqual(out["status"], "ALREADY_CANCELLED")
        self.assertEqual(client.actions, [])

    def test_normal_cancellation_is_preferred_and_force_never_used(self):
        client = FakeClient([shot(), shot(), shot(complete=True)])
        out = repair.cancel_exact_stale_review(client, now=NOW, sleeper=lambda _: None)
        self.assertEqual(out["status"], "NORMAL_CANCEL_CONFIRMED")
        self.assertEqual(client.actions, ["normal"])

    def test_one_force_only_after_repeated_exact_queued_proof(self):
        client = FakeClient([shot(), shot(), shot(), shot(), shot(), shot(), shot(complete=True)])
        out = repair.cancel_exact_stale_review(client, now=NOW, sleeper=lambda _: None)
        self.assertEqual(out["status"], "FORCE_CANCEL_CONFIRMED")
        self.assertEqual(client.actions, ["normal", "force"])
        self.assertFalse(out["would_post"])

    def test_outcome_unverified_does_not_claim_cancellation(self):
        client = FakeClient([shot()] * 7)
        out = repair.cancel_exact_stale_review(client, now=NOW, sleeper=lambda _: None)
        self.assertEqual(out["status"], "OUTCOME_UNVERIFIED_STOP")
        self.assertEqual(client.actions, ["normal", "force"])

    def test_job_changes_after_normal_request_blocks_force(self):
        client = FakeClient([shot(), shot(), shot(runner_name="runner-1")])
        out = repair.cancel_exact_stale_review(client, now=NOW, sleeper=lambda _: None)
        self.assertEqual(out["status"], "OUTCOME_UNVERIFIED_STOP")
        self.assertEqual(client.actions, ["normal"])

    def test_two_previews_must_match_byte_for_byte(self):
        client = FakeClient([shot(), shot(steps=[{"name":"checkout"}])])
        out = repair.cancel_exact_stale_review(client, now=NOW, sleeper=lambda _: None)
        self.assertEqual(out["status"], "BLOCKED")
        self.assertEqual(out["reason"], "SNAPSHOT_CHANGED")
        self.assertEqual(client.actions, [])


if __name__ == "__main__":
    unittest.main()
