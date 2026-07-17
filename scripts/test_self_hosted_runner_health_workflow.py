#!/usr/bin/env python3
"""Self-hosted runner health must validate the same production runtime safely."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / ".github" / "workflows" / "self-hosted-runner-health.yml"
text = PATH.read_text(encoding="utf-8")
workflow = yaml.safe_load(text)
job = workflow["jobs"]["health"]
steps = job["steps"]
runs = "\n".join(str(step.get("run", "")) for step in steps)
checks = [
    ("manual trigger only", "workflow_dispatch:" in text and "schedule:" not in text),
    ("production self-hosted labels", job.get("runs-on") == ["self-hosted", "linux", "x64", "sns-growth", "production"]),
    ("checkout credentials disabled", any(step.get("with", {}).get("persist-credentials") is False for step in steps)),
    ("python 3.11 selected", any(step.get("with", {}).get("python-version") == "3.11" for step in steps)),
    ("repository venv created", "python3 -m venv .runner-venv" in runs),
    ("yt-dlp checked from venv", ".runner-venv/bin/python -m yt_dlp --version" in runs),
    ("hardcoded removed venv absent", "/var/lib/sns-growth-engine/venv/bin/yt-dlp" not in runs),
    ("Sheets health is read only", "check_autonomous_health.py --account-id all --dry-run --use-sheets" in runs),
    ("temporary venv always cleaned", any(step.get("if") == "always()" and "rm -rf .runner-venv" in str(step.get("run", "")) for step in steps)),
    ("no external execution flags", not any(flag in runs for flag in ("--confirm-real-post", "--confirm-download", "--confirm-cut", "--confirm-upload"))),
]
for name, passed in checks:
    print(f"  {'PASS' if passed else 'FAIL'} {name}")
failed = [name for name, passed in checks if not passed]
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
