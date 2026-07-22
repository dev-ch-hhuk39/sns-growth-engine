#!/usr/bin/env python3
"""The replacement library-health workflow stays read-only and bounded.

The filename is retained because older runbooks invoke it directly.
"""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / ".github" / "workflows" / "library-health.yml"
text = PATH.read_text(encoding="utf-8")
workflow = yaml.safe_load(text)
job = workflow["jobs"]["library-health"]
steps = job["steps"]
runs = "\n".join(str(step.get("run", "")) for step in steps)
checks = [
    ("weekly and manual triggers", "workflow_dispatch:" in text and "schedule:" in text),
    ("ephemeral GitHub-hosted runner", job.get("runs-on") == "ubuntu-latest"),
    ("checkout credentials disabled", any(step.get("with", {}).get("persist-credentials") is False for step in steps)),
    ("Python 3.12 selected for last30days", any(step.get("with", {}).get("python-version") == "3.12" for step in steps)),
    ("exact OSS requirements installed", "requirements-oss.txt" in runs),
    ("Agent Reach doctor runs", "agent-reach doctor" in runs),
    ("last30days preflight runs", "last30days.py\" --preflight" in runs),
    ("provider contracts tested", "test_provider_registry_capabilities.py" in runs),
    ("no idle wait", "time.sleep" not in runs and "random.randint" not in runs),
    ("no external execution flags", not any(flag in runs for flag in ("--confirm-real-post", "--confirm-download", "--confirm-cut", "--confirm-upload"))),
]
for name, passed in checks:
    print(f"  {'PASS' if passed else 'FAIL'} {name}")
failed = [name for name, passed in checks if not passed]
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
