#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
workflow = (ROOT / ".github/workflows/autopilot-auto-ready.yml").read_text(encoding="utf-8")

assert 'cron: "7 */2 * * *"' in workflow
assert "fail-fast: false" in workflow
assert "max-parallel: 1" in workflow
assert workflow.count("--verify-only --text-inventory-scope") == 2
assert "steps.preparation_guard.outcome == 'success'" in workflow
assert '[BLOCKED] kill_switch=true' in workflow
assert "matrix.account_id" in workflow
assert "--evergreen-bank" in workflow
assert 'beauty_account' in workflow
assert 'if [ "${{ github.event_name }}" = "schedule" ]' in workflow
assert 'max_ready=3' in workflow
assert "env.AUTO_READY_APPLY == 'true'" in workflow
assert "--skip-real-post" in workflow
assert 'PUBLISH_ENABLED: "false"' in workflow
assert 'ALLOW_REAL_X_POST: "false"' in workflow

print("PASS test_auto_ready_schedule_maintains_three_accounts.py")
