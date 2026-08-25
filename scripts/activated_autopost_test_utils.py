#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/autonomous_mode.json"
MEDIA_CONFIG = ROOT / "config/media_growth_engine.json"
CONTENT_MIX = ROOT / "config/content_mix/default_mix.json"
WORKFLOWS = ROOT / ".github/workflows"

TEXT_WORKFLOWS = {
    "night_scout": WORKFLOWS / "autonomous-growth-loop-night-scout.yml",
    "liver_manager": WORKFLOWS / "autonomous-growth-loop-liver-manager.yml",
}
MEDIA_PUBLISH_WORKFLOWS = {
    "night_scout_direct": WORKFLOWS / "direct-reference-media-night-scout.yml",
    "night_scout_clip": WORKFLOWS / "media-growth-post-night-scout.yml",
    "liver_manager_direct": WORKFLOWS / "direct-reference-media-liver-manager.yml",
    "liver_manager_clip": WORKFLOWS / "media-growth-post-liver-manager.yml",
}
MEDIA_PREPARATION_WORKFLOWS = {
    "direct": WORKFLOWS / "direct-media-preparation.yml",
    "night_scout_clip": WORKFLOWS / "media-growth-production-night-scout.yml",
    "liver_manager_clip": WORKFLOWS / "media-growth-production.yml",
    "night_scout_clip_prepare": WORKFLOWS / "media-growth-production-night-scout.yml",
    "liver_manager_clip_prepare": WORKFLOWS / "media-growth-production.yml",
}
MEDIA_PREP_WORKFLOWS = MEDIA_PREPARATION_WORKFLOWS


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def workflow(path: Path) -> tuple[str, dict]:
    text = path.read_text(encoding="utf-8")
    return text, yaml.safe_load(text)


def schedules(path: Path) -> set[str]:
    _text, data = workflow(path)
    on = data.get("on") or data.get(True) or {}
    return {str(row["cron"]) for row in on.get("schedule", [])}


def assert_activation_config() -> None:
    """Dedicated media automation may run without granting media to text runner."""

    cfg = load_json(CONFIG)
    media = load_json(MEDIA_CONFIG)
    assert cfg["scheduled_prepare_enabled"] is True
    assert cfg["scheduled_publish_enabled"] is True
    assert cfg["production_publish_activation_approved"] is True
    assert cfg["pre_activation_queue_archive_required"] is True
    assert cfg["pre_activation_queue_archive_completed"] is True

    # Generic autonomous loop is deliberately text-only.
    assert cfg["allow_media_posts"] is False
    assert cfg["allow_video_download"] is False
    assert cfg["allow_video_cut"] is False
    assert cfg["allow_cloudinary_upload"] is False

    # Dedicated registered-source media pipeline is active.
    assert media["production_autopilot_enabled"] is True
    assert media["download_enabled"] is True
    assert media["cut_enabled"] is True
    assert media["upload_enabled"] is True
    assert media["video_post_enabled"] is True
    assert media["media_schedule_enabled"] is True
    assert media["media_public_post_auto_enabled"] is True
    assert media["require_permission_evidence"] is True

    # Activation must not weaken the existing safety/account boundaries.
    assert cfg["allow_third_party_media"] is False
    assert cfg["allow_unknown_rights"] is False
    assert cfg["allow_transcription_api"] is False
    assert cfg["kill_switch"] is False
    assert "threads" in cfg["allowed_platforms_for_post"]
    assert "x" in cfg["blocked_platforms_for_post"]
    assert "x" in cfg["blocked_platforms_for_fetch"]
    assert set(cfg["allowed_accounts"]) == {
        "night_scout",
        "liver_manager",
        "beauty_account",
    }


def assert_all_slot_schedules() -> None:
    assert schedules(TEXT_WORKFLOWS["night_scout"]) == {"45 4 * * *", "45 6 * * *", "45 15 * * *"}
    assert schedules(TEXT_WORKFLOWS["liver_manager"]) == {"45 0 * * *", "45 3 * * *", "45 11 * * *"}
    assert schedules(MEDIA_PUBLISH_WORKFLOWS["night_scout_direct"]) == {"45 8 * * *"}
    assert schedules(MEDIA_PUBLISH_WORKFLOWS["night_scout_clip"]) == {"45 11 * * *"}
    assert schedules(MEDIA_PUBLISH_WORKFLOWS["liver_manager_direct"]) == {"45 6 * * *"}
    assert schedules(MEDIA_PUBLISH_WORKFLOWS["liver_manager_clip"]) == {"45 8 * * *"}


def assert_text_workflow_contract(account_id: str) -> None:
    path = TEXT_WORKFLOWS[account_id]
    text, _data = workflow(path)
    assert "Schedule heartbeat" in text
    assert "Early runtime preflight" in text
    assert "scheduled_execution_guard" in text
    assert "Resolve autonomous execution mode" in text
    assert "RUN_AUTONOMOUS_APPLY" in text
    assert 'PUBLISH_ENABLED: "false"' in text
    assert 'ALLOW_REAL_THREADS_POST: "false"' in text
    assert 'ALLOW_REAL_X_POST: "false"' in text
    assert 'ALLOW_VIDEO_DOWNLOAD: "false"' in text
    assert 'ALLOW_VIDEO_CUT: "false"' in text
    assert 'ALLOW_CLOUDINARY_UPLOAD: "false"' in text
    assert "run_scheduled_text_slot_pipeline.py" in text
    assert "GEMINI_API_KEY" in text
    assert "ref: ${{ github.sha }}" in text
    assert "actions: read" in text


def assert_media_publish_contract(path: Path, slot_id: str) -> None:
    text, _data = workflow(path)
    assert "workflow_dispatch:" in text
    assert "schedule:" in text
    assert "Schedule heartbeat" in text
    assert "Early runtime preflight" in text
    assert "scheduled_execution_guard" in text
    assert "scheduled_publish_activation_gate.py --use-sheets" in text
    assert "Runtime activation gate" in text
    assert "run_hybrid_ready_pipeline.py" in text
    assert "selected_queue_id" in text
    assert '--queue-id "$qid"' in text
    assert slot_id in text
    assert 'PUBLISH_ENABLED: "false"' in text
    assert 'ALLOW_REAL_THREADS_POST: "false"' in text
    assert 'ALLOW_REAL_X_POST: "true"' not in text
    assert "--fallback-to-text" not in text
    assert "exit 2" in text


def assert_media_preparation_contract(path: Path, slot_id: str) -> None:
    text, _data = workflow(path)
    assert "workflow_dispatch:" in text
    assert "schedule:" in text
    assert "Schedule heartbeat" in text
    assert slot_id in text
    assert 'PUBLISH_ENABLED: "false"' in text
    assert 'ALLOW_REAL_THREADS_POST: "false"' in text


def assert_no_waiting_review_publication() -> None:
    for path in (*TEXT_WORKFLOWS.values(), *MEDIA_PUBLISH_WORKFLOWS.values()):
        text = path.read_text(encoding="utf-8")
        assert "process_threads_queue.py" in text or "run_direct_reference_media_pipeline.py" in text
        assert "WAITING_REVIEW" not in text or "Create exact WAITING_REVIEW" in text
