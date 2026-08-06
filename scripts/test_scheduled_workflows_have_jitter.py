#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

for name in (
    "autonomous-growth-loop-night-scout.yml",
    "autonomous-growth-loop-liver-manager.yml",
):
    text = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
    assert "random.randint" not in text
    assert "time.sleep" not in text
    assert "Early runtime preflight" in text
    assert "scheduled_window_decision" in text
    assert "run_scheduled_text_slot_pipeline.py" in text

guard = (ROOT / "scripts/scheduled_execution_guard.py").read_text(encoding="utf-8")
assert 'MAX_SCHEDULE_DELAY_MINUTES = int(os.environ.get("MAX_SCHEDULE_DELAY_MINUTES", "15"))' in guard
assert "scheduled_run_out_of_window" in guard
print("PASS test_scheduled_workflows_have_jitter.py")
