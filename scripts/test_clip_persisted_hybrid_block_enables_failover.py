#!/usr/bin/env python3
"""A persisted Hybrid BLOCKED result is terminal for clip selection."""
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

from run_media_production_pipeline import persisted_hybrid_gate_status  # noqa: E402


blocked = {
    "status": "WAITING_REVIEW",
    "generation_policy_json": json.dumps({
        "hybrid_ai_gate": {
            "status": "BLOCKED",
            "blocked_reasons": ["clip_transcript_noise_present"],
        }
    }),
}
assert persisted_hybrid_gate_status(blocked) == "BLOCKED"
assert persisted_hybrid_gate_status({
    "status": "WAITING_REVIEW",
    "generation_policy_json": json.dumps({"hybrid_ai_gate": {"status": "PASS"}}),
}) == "PASS"
assert persisted_hybrid_gate_status({"generation_policy_json": "not-json"}) == ""

pipeline = (ROOT / "scripts/run_media_production_pipeline.py").read_text(encoding="utf-8")
assert 'persisted_hybrid_gate_status(row) == "BLOCKED"' in pipeline
assert "effective_excluded_clip_ids.add(clip_id)" in pipeline

print("PASS test_clip_persisted_hybrid_block_enables_failover.py")
