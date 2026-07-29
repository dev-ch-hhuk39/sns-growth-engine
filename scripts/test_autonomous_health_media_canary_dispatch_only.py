#!/usr/bin/env python3
"""Media publishers remain manual-only until canary evidence activates them."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_autonomous_health import build_health

health = build_health("all")
workflows = health["workflow_files"]
media = health["media_schedule"]
scheduled_keys = {"media_post_liver_manager", "media_post_night_scout", "direct_media_liver_manager", "direct_media_night_scout"}
preparation_keys = {key for key in workflows if key.startswith(("media_prepare_",))}
checks = [
    ("media scheduled publishing remains disabled", media["media_schedule_on"] is False),
    ("media schedules are inactive before activation", media["media_schedule_connected"] is False),
    ("media mode is manual canary only", media["media_execution_mode"] == "manual_canary_only"),
    ("all media canary workflows are healthy", media["media_canary_workflows_healthy"] is True),
    ("media publishers remain dispatch only", all(workflows[key]["trigger_mode"] == "dispatch_only_preparation" for key in scheduled_keys)),
    ("media preparation remains dispatch only", all(workflows[key]["trigger_mode"] == "dispatch_only_preparation" for key in preparation_keys)),
    ("no inactive media workflow is reported missing", not any("media_" in item and "schedule_" in item for item in health["problems"])),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(ok for _, ok in checks) else 1)
