#!/usr/bin/env python3
"""Production workflows stay private-runner-only and reject untrusted triggers."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((ROOT / ".github/workflows").glob("*.yml"))
RUNNER = ["self-hosted", "linux", "x64", "sns-growth", "production"]

checks: list[tuple[str, bool]] = []
for path in WORKFLOWS:
    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw) or {}
    for job_name, job in (data.get("jobs") or {}).items():
        checks.append((f"{path.name}:{job_name}:self-hosted", job.get("runs-on") == RUNNER))
    checks.append((f"{path.name}:no untrusted trigger", all(term not in raw for term in ("pull_request:", "pull_request_target:", "repository_dispatch:", "issue_comment:", "workflow_run:"))))
    if "actions/checkout@" in raw:
        checks.append((f"{path.name}:checkout credentials disabled", "persist-credentials: false" in raw))

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
