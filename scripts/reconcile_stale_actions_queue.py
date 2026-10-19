#!/usr/bin/env python3
"""One-shot, exact-ID cleanup for two historic, demonstrably stalled GitHub runs.

Never starts a workflow, changes the repository, publishes, or touches Sheets.
Only the normal cancel endpoint is permitted after two independently verified
read-only checks. The job cannot use force-cancel.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

REPOSITORY = "dev-ch-hhuk39/sns-growth-engine"
MIN_AGE_HOURS = 72
TARGETS = {
    37327934561: {
        "name": "Publication Review Board",
        "event": "schedule",
        "sha": "4aa37f5c6409e0d9faa6d1e3e90d248f1984ced3",
    },
    31128114509: {
        "name": "CI WP3 Production Read-Only Verification",
        "event": "workflow_dispatch",
        "sha": "de9fe8601aea26cb30860d9140373c2d384144d2",
    },
}
QUEUED_STATES = frozenset({"queued", "pending", "waiting", "requested"})


class GithubApi:
    def __init__(self, token: str, repository: str) -> None:
        self.token = token
        self.base = "https://api.github.com/repos/" + repository

    def request(self, path: str, *, method: str = "GET") -> dict[str, Any]:
        request = urllib.request.Request(
            self.base + path,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": "Bearer " + self.token,
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "chadult-stale-queue-one-shot",
            },
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            if method == "POST":
                if response.status != 202:
                    raise RuntimeError("github_cancel_not_accepted")
                return {"cancel_http_status": 202}
            return json.load(response)

    def snapshot(self, run_id: int) -> tuple[dict[str, Any], dict[str, Any]]:
        run = self.request("/actions/runs/" + str(run_id))
        jobs = self.request("/actions/runs/" + str(run_id) + "/jobs?per_page=100")
        return run, jobs

    def cancel(self, run_id: int) -> None:
        self.request("/actions/runs/" + str(run_id) + "/cancel", method="POST")


def eligible(run_id: int, run: dict[str, Any], jobs: dict[str, Any],
             now: datetime) -> str:
    target = TARGETS.get(run_id)
    if target is None:
        return "UNLISTED_RUN_BLOCKED"
    if (run.get("name") != target["name"]
            or run.get("event") != target["event"]
            or run.get("head_sha") != target["sha"]
            or (run.get("repository") or {}).get("full_name") != REPOSITORY):
        return "RUN_IDENTITY_MISMATCH"
    if run.get("status") not in QUEUED_STATES or run.get("conclusion") is not None:
        return "RUN_NOT_QUEUED"
    if int(run.get("run_attempt") or 0) != 1:
        return "RUN_RETRY_MISMATCH"
    try:
        created = datetime.fromisoformat(str(run["created_at"]).replace("Z", "+00:00"))
    except (ValueError, KeyError, TypeError):
        return "RUN_AGE_UNVERIFIED"
    if (now - created.astimezone(timezone.utc)).total_seconds() < MIN_AGE_HOURS * 3600:
        return "RUN_TOO_RECENT"
    entries = jobs.get("jobs")
    if not isinstance(entries, list):
        return "JOB_LIST_UNVERIFIED"
    if jobs.get("total_count") != len(entries) or len(entries) >= 100:
        return "JOB_LIST_INCOMPLETE"
    for job in entries:
        if (not isinstance(job, dict) or job.get("status") not in QUEUED_STATES
                or job.get("started_at") is not None
                or job.get("completed_at") is not None
                or job.get("conclusion") is not None):
            return "JOB_ALREADY_STARTED_OR_FINISHED"
    return "ELIGIBLE_STALE_QUEUED"


def assess_and_cancel(client: Any, run_id: int, *, apply: bool,
                      now: datetime | None = None) -> dict[str, Any]:
    if run_id not in TARGETS:
        return {"run_id": run_id, "status": "UNLISTED_RUN_BLOCKED"}
    moment = now or datetime.now(timezone.utc)
    run, jobs = client.snapshot(run_id)
    reason = eligible(run_id, run, jobs, moment)
    if reason != "ELIGIBLE_STALE_QUEUED":
        return {"run_id": run_id, "status": "SKIPPED", "reason": reason}
    if not apply:
        return {"run_id": run_id, "status": "DRY_RUN_ELIGIBLE"}
    # Recheck immediately before the only permitted mutation; never retry
    # cancellations on unclear outcomes or silently fall back to force-cancel.
    latest_run, latest_jobs = client.snapshot(run_id)
    if eligible(run_id, latest_run, latest_jobs, moment) != "ELIGIBLE_STALE_QUEUED":
        return {"run_id": run_id, "status": "SKIPPED_CHANGED_BEFORE_CANCEL"}
    if run.get("status") != latest_run.get("status") or jobs != latest_jobs:
        return {"run_id": run_id, "status": "SKIPPED_SNAPSHOT_CHANGED"}
    client.cancel(run_id)
    return {"run_id": run_id, "status": "CANCEL_REQUESTED_NOT_YET_CONFIRMED"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-stale-run-cancel", action="store_true")
    args = parser.parse_args(argv)
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GH_ACTIONS_TOKEN", "")
    if repo != REPOSITORY or not token:
        print(json.dumps({"status": "BLOCKED", "reason": "scoped_github_auth_unavailable"}))
        return 2
    if args.apply and (
        not args.confirm_stale_run_cancel
        or os.environ.get("SNS_QUEUE_RECOVERY_ALLOWED") != "true"
        or os.environ.get("GITHUB_EVENT_NAME") != "push"
        or os.environ.get("GITHUB_REF") != "refs/heads/main"
    ):
        print(json.dumps({"status": "BLOCKED", "reason": "main_push_confirmation_required"}))
        return 2
    client = GithubApi(token, repo)
    results: list[dict[str, Any]] = []
    try:
        for run_id in TARGETS:
            results.append(assess_and_cancel(client, run_id, apply=args.apply))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
            RuntimeError, ValueError):
        # A cancel request may have reached GitHub even if the response failed.
        # Never retry automatically or claim cleanup succeeded.
        print(json.dumps({"status": "OUTCOME_UNVERIFIED_STOP", "results": results}))
        return 2
    print(json.dumps({"status": "DONE", "mode": "APPLY" if args.apply else "READ_ONLY",
                      "results": results, "would_post": False}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
