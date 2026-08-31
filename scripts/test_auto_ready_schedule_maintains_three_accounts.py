#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
workflow = (ROOT / ".github/workflows/autopilot-auto-ready.yml").read_text(encoding="utf-8")

assert 'cron: "0 */6 * * *"' in workflow
assert 'beauty_account' in workflow
assert 'if [ "${{ github.event_name }}" = "schedule" ]' in workflow
assert 'max_ready=3' in workflow
assert "env.AUTO_READY_APPLY == 'true'" in workflow
assert "--skip-real-post" in workflow
assert 'PUBLISH_ENABLED: "false"' in workflow
assert 'ALLOW_REAL_X_POST: "false"' in workflow

print("PASS test_auto_ready_schedule_maintains_three_accounts.py")
