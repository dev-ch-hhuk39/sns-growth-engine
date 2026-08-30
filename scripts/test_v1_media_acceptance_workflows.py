#!/usr/bin/env python3
"""V1 media acceptance stays bounded, exact-queue and account scoped."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source(name: str) -> str:
    return (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")


direct_prepare = source("direct-media-preparation.yml")
clip_prepare = source("approved-source-clip-preparation.yml")
beauty = source("beauty-threads-production.yml")

assert "config/managed_accounts.json" in direct_prepare
assert "route_slot_id" in direct_prepare
assert 'max-parallel: 1' in direct_prepare
assert "run_direct_media_preparation_loop.py" in direct_prepare
assert "direct_media_candidate_attempts" in direct_prepare
assert 'ALLOW_REAL_THREADS_POST: "false"' in direct_prepare

assert "schedule:" not in clip_prepare
assert "account_production_enabled" in clip_prepare
assert "route_slot_id" in clip_prepare
assert "--limit 2" in clip_prepare
assert "--prepare-only" in clip_prepare
assert "--prepare-saved-media-queue" in clip_prepare
assert "run_hybrid_ready_pipeline.py" in clip_prepare
assert "--autonomous-low-risk" in clip_prepare
assert "--require-human-review" not in clip_prepare
assert "sync_publication_review.py" in clip_prepare
assert 'ALLOW_TRANSCRIPTION_API: "false"' in clip_prepare
assert 'ALLOW_REAL_THREADS_POST: "false"' in clip_prepare
assert 'ALLOW_REAL_X_POST: "false"' in clip_prepare

for workflow in (
    "direct-reference-media-night-scout.yml",
    "direct-reference-media-liver-manager.yml",
    "media-growth-post-night-scout.yml",
    "media-growth-post-liver-manager.yml",
):
    body = source(workflow)
    assert "manual publish requires exact queue_id" in body, workflow
    assert '--queue-id "${{ github.event.inputs.queue_id }}"' in body, workflow
    assert "--max-posts 1" in body or "--post-ready" in body, workflow
    assert 'ALLOW_REAL_X_POST: "false"' in body, workflow

assert "publish_media" in beauty
assert "publish_media requires exact queue_id" in beauty
assert "beauty_direct_media_review" in beauty
assert "beauty_clip_review" in beauty
assert '--queue-id "${{ github.event.inputs.queue_id }}" --max-posts 1' in beauty
assert 'ALLOW_REAL_X_POST: "false"' in beauty

print("PASS: bounded exact-queue media acceptance workflows")
