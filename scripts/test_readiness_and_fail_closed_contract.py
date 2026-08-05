#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

from activated_autopost_test_utils import assert_activation_config, assert_all_slot_schedules

ROOT = Path(__file__).resolve().parents[1]

assert_activation_config()
assert_all_slot_schedules()

activation = (ROOT / "scripts/scheduled_publish_activation_gate.py").read_text(encoding="utf-8")
for marker in (
    "pre_activation_queue_archive_not_completed",
    "production_publish_activation_approved",
    "scheduled_publish_enabled",
):
    assert marker in activation

# The universal Threads worker must independently fail closed unless the
# persisted Hybrid AI gate is current. Media preparation/promotion is a
# separate staged route, so do not require the direct-media preparation helper
# itself to duplicate the publisher's gate implementation.
worker = (ROOT / "scripts/process_threads_queue.py").read_text(encoding="utf-8")
for marker in (
    "from hybrid_ai_gate import",
    "requires_hybrid_ai_gate",
    "hybrid_ai_gate_passed",
):
    assert marker in worker

pipeline = (ROOT / "scripts/run_hybrid_ready_pipeline.py").read_text(encoding="utf-8")
assert "scripts/run_hybrid_ai_queue_gate.py" in pipeline
assert "scripts/promote_hybrid_approved_media.py" in pipeline
assert "selected_queue_id" in pipeline

for name in (
    "direct-reference-media-night-scout.yml",
    "direct-reference-media-liver-manager.yml",
    "media-growth-post-night-scout.yml",
    "media-growth-post-liver-manager.yml",
):
    workflow = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
    assert "run_hybrid_ready_pipeline.py" in workflow
    assert "selected_queue_id" in workflow
    assert '--queue-id "$qid"' in workflow
    assert "[SAFE_NO_POST]" in workflow

print("PASS test_readiness_and_fail_closed_contract.py")
