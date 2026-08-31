#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
approve = (root / "scripts/auto_approve_queue.py").read_text(encoding="utf-8")
selector = (root / "scripts/select_beauty_scheduled_ready.py").read_text(encoding="utf-8")
schema = (root / "src/sheets_client.py").read_text(encoding="utf-8")

assert '"approval_mode": "autonomous_safe"' in approve
assert '"automated_approved": "true"' in approve
assert '"human_approved": "false"' in approve
assert "automated_approved = approval_source == AUTONOMOUS_APPROVAL_SOURCE" in selector
for field in ("approval_mode", "automated_approved", "human_approved"):
    assert field in schema
print("PASS test_autonomous_approval_evidence.py")
