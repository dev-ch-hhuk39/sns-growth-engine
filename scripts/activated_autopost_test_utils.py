from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

TEXT_WORKFLOWS = {
    "night_scout": ROOT / ".github/workflows/autonomous-growth-loop-night-scout.yml",
    "liver_manager": ROOT / ".github/workflows/autonomous-growth-loop-liver-manager.yml",
}
MEDIA_PUBLISH_WORKFLOWS = {
    "night_scout_direct": ROOT / ".github/workflows/direct-reference-media-night-scout.yml",
    "night_scout_clip": ROOT / ".github/workflows/media-growth-post-night-scout.yml",
    "liver_manager_direct": ROOT / ".github/workflows/direct-reference-media-liver-manager.yml",
    "liver_manager_clip": ROOT / ".github/workflows/media-growth-post-liver-manager.yml",
}
MEDIA_PREP_WORKFLOWS = {
    "night_scout_clip_prepare": ROOT / ".github/workflows/media-growth-production-night-scout.yml",
    "liver_manager_clip_prepare": ROOT / ".github/workflows/media-growth-production.yml",
    "direct_prepare": ROOT / ".github/workflows/direct-media-preparation.yml",
}


def workflow(path: Path) -> tuple[str, dict]:
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    return text, data


def crons(path: Path) -> list[str]:
    _text, data = workflow(path)
    trigger = data.get("on") or data.get(True) or {}
    return [str(row["cron"]) for row in trigger.get("schedule", [])]


def autonomous_config() -> dict:
    return json.loads((ROOT / "config/autonomous_mode.json").read_text(encoding="utf-8"))


def assert_activation_config() -> None:
    cfg = autonomous_config()
    assert cfg["scheduled_prepare_enabled"] is True
    assert cfg["scheduled_publish_enabled"] is True
    assert cfg["production_publish_activation_approved"] is True
    assert cfg["pre_activation_queue_archive_required"] is True
    assert cfg["pre_activation_queue_archive_completed"] is True
    assert cfg["kill_switch"] is False
    # Generic text autonomous execution remains media-disabled. Dedicated
    # workflows provide media gates only at the exact posting step.
    assert cfg["allow_media_posts"] is False


def assert_all_slot_schedules() -> None:
    expected = {
        TEXT_WORKFLOWS["night_scout"]: ["2 5 * * *", "2 7 * * *", "2 16 * * *"],
        TEXT_WORKFLOWS["liver_manager"]: ["4 1 * * *", "4 4 * * *", "4 12 * * *"],
        MEDIA_PUBLISH_WORKFLOWS["night_scout_direct"]: ["2 9 * * *"],
        MEDIA_PUBLISH_WORKFLOWS["night_scout_clip"]: ["2 12 * * *"],
        MEDIA_PUBLISH_WORKFLOWS["liver_manager_direct"]: ["4 7 * * *"],
        MEDIA_PUBLISH_WORKFLOWS["liver_manager_clip"]: ["4 9 * * *"],
        MEDIA_PREP_WORKFLOWS["night_scout_clip_prepare"]: ["30 9 * * *"],
        MEDIA_PREP_WORKFLOWS["liver_manager_clip_prepare"]: ["30 6 * * *"],
        MEDIA_PREP_WORKFLOWS["direct_prepare"]: ["30 5 * * *"],
    }
    for path, rows in expected.items():
        assert crons(path) == rows, (path.name, crons(path), rows)


def assert_text_workflow_contract(account_id: str) -> None:
    path = TEXT_WORKFLOWS[account_id]
    text, _data = workflow(path)
    assert "Schedule heartbeat" in text
    assert "Diagnose schedule delay" in text
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
    assert "Diagnose schedule delay" in text
    assert "scheduled_publish_activation_gate.py --use-sheets" in text
    assert "run_hybrid_ready_pipeline.py" in text
    assert "selected_queue_id" in text
    assert '--queue-id "$qid"' in text
    assert slot_id in text
    assert 'PUBLISH_ENABLED: "false"' in text
    assert 'ALLOW_REAL_THREADS_POST: "false"' in text
    assert 'ALLOW_REAL_X_POST: "true"' not in text
    assert "--fallback-to-text" not in text


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
        assert "--status WAITING_REVIEW" not in text
        assert "run_hybrid_ready_pipeline.py" in text
        assert '--queue-id "$qid"' in text or "run_scheduled_text_slot_pipeline.py" in text
