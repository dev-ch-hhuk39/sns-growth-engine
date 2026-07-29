#!/usr/bin/env python3
"""Media schedules are connected but activation-guarded before canaries."""
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
    ("media schedules are connected", media["media_schedule_connected"] is True),
    ("media mode is activation guarded", media["media_execution_mode"] == "scheduled_activation_guarded"),
    ("all media canary workflows are healthy", media["media_canary_workflows_healthy"] is True),
    ("media publishers declare guarded schedule trigger", all(workflows[key]["trigger_mode"] == "scheduled_activation_guarded" for key in scheduled_keys)),
    ("media preparation remains dispatch only", all(workflows[key]["trigger_mode"] == "dispatch_only_preparation" for key in preparation_keys)),
    ("no guarded media cron is reported missing", not any("media_" in item and "schedule_" in item for item in health["problems"])),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(ok for _, ok in checks) else 1)
