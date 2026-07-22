#!/usr/bin/env python3
"""Dispatch-only media canaries are healthy, not missing schedules."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_autonomous_health import build_health

health = build_health("all")
workflows = health["workflow_files"]
media = health["media_schedule"]
canary_keys = [key for key in workflows if key.startswith(("media_", "direct_media_"))]
checks = [
    ("media schedules remain off", media["media_schedule_on"] is False),
    ("media mode is dispatch-only canary", media["media_execution_mode"] == "dispatch_only_canary"),
    ("all media canary workflows are healthy", media["media_canary_workflows_healthy"] is True),
    ("media workflows declare dispatch-only trigger", all(workflows[key]["trigger_mode"] == "dispatch_only_canary" for key in canary_keys)),
    ("no intentional media cron is reported missing", not any("media_" in item and "schedule_" in item for item in health["problems"])),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(ok for _, ok in checks) else 1)
