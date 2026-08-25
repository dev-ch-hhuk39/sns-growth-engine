#!/usr/bin/env python3
"""Clip preparation and publishing share one bounded scheduled path."""
from __future__ import annotations

from pathlib import Path

from run_media_production_pipeline import build_plan

ROOT = Path(__file__).resolve().parents[1]


queue_plan = build_plan(
    apply=True,
    confirm=True,
    client=None,
    account_id="night_scout",
    post_saved_media=True,
    prepare_saved_media_queue=True,
    slot_id="ns_2100_clip_media",
)
assert queue_plan["status"] == "PLAN_ONLY"
assert "media_public_post_auto_disabled" not in queue_plan["blocked_reasons"]

for workflow_name in (
    "media-growth-post-night-scout.yml",
    "media-growth-post-liver-manager.yml",
):
    workflow = (ROOT / ".github/workflows" / workflow_name).read_text(encoding="utf-8")
    assert "--json-output /tmp/clip-queue.json" in workflow
    assert "Hybrid review and autonomous exact media promotion" in workflow
    assert "--autonomous-low-risk" in workflow
    assert "no eligible exact clip queue" in workflow
    assert "media-to-text" not in workflow

for workflow_name in (
    "media-growth-production-night-scout.yml",
    "media-growth-production.yml",
):
    workflow = (ROOT / ".github/workflows" / workflow_name).read_text(encoding="utf-8")
    for step in (
        "Transcribe approved source videos",
        "Generate transcript-grounded clip candidates",
        "Prepare one approved media asset",
    ):
        step_body = workflow.split(f"- name: {step}", 1)[1].split("- name:", 1)[0]
        assert "github.event_name == 'schedule'" in step_body

pipeline = (ROOT / "scripts/run_media_production_pipeline.py").read_text(encoding="utf-8")
assert "FAILED_READ_AFTER_WRITE" in pipeline
assert '"NO_ELIGIBLE_CLIP"' in pipeline
assert "effective_excluded_clip_ids" in pipeline

print("PASS test_clip_scheduled_autonomous_path.py")
