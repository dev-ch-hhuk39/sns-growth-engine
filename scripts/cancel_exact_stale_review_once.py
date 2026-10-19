#!/usr/bin/env python3
"""One-shot, exact-ID cancellation of one permanently queued review workflow.

The target was created 2026-10-05 and has a GitHub-created started_at timestamp
one second later despite status=queued, no runner, no steps, no completion.
Only this immutable run/job identity is eligible. Other runs are untouched.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

REPO = "dev-ch-hhuk39/sns-growth-engine"
RUN_ID = 37327934561
JOB_ID = 111823333981
EXPECTED_SHA = "4aa37f5c6409e0d9faa6d1e3e90d248f1984ced3"
EXPECTED_CREATED = "2026-10-05T14:50:11Z"
EXPECTED_JOB_STARTED = "2026-10-05T14:50:12Z"
MIN_AGE_SECONDS = 7 * 86400


class GitHub:
    def __init__(self, token: str):
        self.base = "https://api.github.com/repos/" + REPO
        self.token = token

    def request(self, suffix: str, method: str = "GET") -> dict[str, Any]:
        request = urllib.request.Request(
            self.base + suffix, method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": "Bearer " + self.token,
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "chadult-exact-stale-review-once",
            },
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            if method == "POST":
                if response.status != 202:
                    raise RuntimeError("cancel_request_not_accepted")
                return {"http_status": 202}
            return json.load(response)

    def snapshot(self) -> tuple[dict[str, Any], dict[str, Any]]:
        return (
            self.request("/actions/runs/" + str(RUN_ID)),
            self.request("/actions/runs/" + str(RUN_ID) + "/jobs?per_page=100"),
        )

    def cancel(self, *, force: bool) -> None:
        suffix = "/force-cancel" if force else "/cancel"
        self.request("/actions/runs/" + str(RUN_ID) + suffix, method="POST")


def safe_to_cancel(run: dict[str, Any], jobs: dict[str, Any], *,
                   now: datetime | None = None) -> str:
    if not isinstance(run, dict) or not isinstance(jobs, dict):
        return "INVALID_SOURCE"
    if (run.get("id") != RUN_ID
            or run.get("name") != "Publication Review Board"
            or run.get("event") != "schedule"
            or run.get("head_sha") != EXPECTED_SHA
            or (run.get("repository") or {}).get("full_name") != REPO
            or run.get("created_at") != EXPECTED_CREATED
            or run.get("run_attempt") != 1):
        return "RUN_IDENTITY_MISMATCH"
    if run.get("status") == "completed" and run.get("conclusion") == "cancelled":
        return "ALREADY_CANCELLED"
    if run.get("status") != "queued" or run.get("conclusion") is not None:
        return "RUN_NOT_QUEUED"
    created = datetime.fromisoformat(EXPECTED_CREATED.replace("Z", "+00:00"))
    if ((now or datetime.now(timezone.utc)) - created).total_seconds() < MIN_AGE_SECONDS:
        return "RUN_TOO_YOUNG"
    entries = jobs.get("jobs")
    if jobs.get("total_count") != 1 or not isinstance(entries, list) or len(entries) != 1:
        return "JOB_COUNT_CHANGED"
    job = entries[0]
    if not isinstance(job, dict):
        return "JOB_IDENTITY_CHANGED"
    if (job.get("id") != JOB_ID
            or job.get("name") != "sync"
            or job.get("status") != "queued"
            or job.get("conclusion") is not None
            or job.get("completed_at") is not None
            or job.get("runner_name") not in (None, "")
            or job.get("started_at") != EXPECTED_JOB_STARTED
            or job.get("steps") not in ([], None)):
        return "JOB_STARTED_OR_CHANGED"
    return "EXACT_STALE_UNSTARTED"


def cancel_exact_stale_review(client: Any, *, now: datetime | None = None,
                              sleeper: Any = time.sleep) -> dict[str, Any]:
    stamp = now or datetime.now(timezone.utc)
    before = client.snapshot()
    reason = safe_to_cancel(*before, now=stamp)
    if reason == "ALREADY_CANCELLED":
        return {"status": reason, "run_id": RUN_ID, "would_post": False}
    if reason != "EXACT_STALE_UNSTARTED":
        return {"status": "BLOCKED", "reason": reason, "run_id": RUN_ID, "would_post": False}
    second = client.snapshot()
    if second != before or safe_to_cancel(*second, now=stamp) != "EXACT_STALE_UNSTARTED":
        return {"status": "BLOCKED", "reason": "SNAPSHOT_CHANGED", "run_id": RUN_ID, "would_post": False}
    # A normal cancel is the first and preferred action. Unknown response stops.
    client.cancel(force=False)
    for _ in range(3):
        sleeper(2)
        state = client.snapshot()
        checked = safe_to_cancel(*state, now=stamp)
        if checked == "ALREADY_CANCELLED":
            return {"status": "NORMAL_CANCEL_CONFIRMED", "run_id": RUN_ID, "would_post": False}
        if checked != "EXACT_STALE_UNSTARTED":
            return {"status": "OUTCOME_UNVERIFIED_STOP", "run_id": RUN_ID, "would_post": False}
    # The exact same 14-day-old unstarted run remains queued after a normal
    # accepted cancellation. Only that case permits one force-cancel attempt.
    before_force = client.snapshot()
    if safe_to_cancel(*before_force, now=stamp) != "EXACT_STALE_UNSTARTED":
        return {"status": "OUTCOME_UNVERIFIED_STOP", "run_id": RUN_ID, "would_post": False}
    client.cancel(force=True)
    sleeper(2)
    final = client.snapshot()
    if safe_to_cancel(*final, now=stamp) == "ALREADY_CANCELLED":
        return {"status": "FORCE_CANCEL_CONFIRMED", "run_id": RUN_ID, "would_post": False}
    return {"status": "OUTCOME_UNVERIFIED_STOP", "run_id": RUN_ID, "would_post": False}


def main() -> int:
    if (os.environ.get("GITHUB_REPOSITORY") != REPO
            or os.environ.get("GITHUB_EVENT_NAME") != "push"
            or os.environ.get("GITHUB_REF") != "refs/heads/main"
            or os.environ.get("GITHUB_RUN_ATTEMPT") != "1"
            or os.environ.get("SNS_EXACT_STALE_REVIEW_ALLOWED") != "true"
            or not os.environ.get("GH_ACTIONS_TOKEN")):
        print(json.dumps({"status": "BLOCKED", "reason": "ONE_SHOT_MAIN_AUTH_REQUIRED"}))
        return 2
    try:
        result = cancel_exact_stale_review(GitHub(os.environ["GH_ACTIONS_TOKEN"]))
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, ValueError,
            RuntimeError, TimeoutError):
        result = {"status": "OUTCOME_UNVERIFIED_STOP", "run_id": RUN_ID, "would_post": False}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in {
        "NORMAL_CANCEL_CONFIRMED", "FORCE_CANCEL_CONFIRMED", "ALREADY_CANCELLED"
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
