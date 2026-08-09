#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from check_autonomous_health import build_health
health = build_health("all")
media = health["media_schedule"]
workflows = health["workflow_files"]
publishers = {"media_post_liver_manager", "media_post_night_scout", "direct_media_liver_manager", "direct_media_night_scout"}
preparers = {"media_prepare_liver_manager", "media_prepare_night_scout"}
checks = [
    ("health has no workflow false positives", health["status"] == "PASS"),
    ("media scheduled publishing disabled until acquisition is validated", media["media_schedule_on"] is False),
    ("media schedules connected", media["media_schedule_connected"] is True),
    ("media mode reports staged disablement", media["media_execution_mode"] == "disabled_pending_acquisition_validation"),
    ("all media workflows healthy", media["media_canary_workflows_healthy"] is True),
    ("publishers activation guarded", all(workflows[k]["trigger_mode"] == "scheduled_activation_guarded" for k in publishers)),
    ("preparers scheduled preparation", all(workflows[k]["trigger_mode"] == "scheduled_preparation" for k in preparers)),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(ok for _, ok in checks) else 1)
