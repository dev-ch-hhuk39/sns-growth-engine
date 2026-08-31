#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
workflow = (ROOT / ".github/workflows/beauty-threads-production.yml").read_text(encoding="utf-8")
prepare = (ROOT / "scripts/prepare_beauty_review_candidates.py").read_text(encoding="utf-8")

assert "Bounded Beauty READY recovery" in workflow
assert "Select scheduled Beauty route after recovery" in workflow
assert "NO_READY_CANDIDATE after bounded Beauty recovery" in workflow
assert "exit 1" in workflow[workflow.index("Report no scheduled approved Beauty row"):]
assert "quality_gate_topic_regeneration" in prepare
assert 'f"{queue_id}_{content_hash[:8]}"' in prepare
assert "beauty_media_route_delegated_no_text_fallback" not in prepare

print("PASS test_beauty_scheduled_ready_recovery.py")
