#!/usr/bin/env python3
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
for name in ("hybrid-ai-gate-night-scout.yml", "hybrid-ai-gate-liver-manager.yml"):
    text = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    assert "schedule:" not in text
for name in ("media-growth-production-night-scout.yml", "media-growth-production.yml"):
    text = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
    assert "schedule:" in text
    assert 'PUBLISH_ENABLED: "false"' in text
    assert 'ALLOW_REAL_THREADS_POST: "false"' in text
print("PASS test_legacy_duplicate_workflows_manual_only.py")
