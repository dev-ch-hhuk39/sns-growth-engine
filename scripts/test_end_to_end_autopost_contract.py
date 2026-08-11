#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def schedules(path: str) -> list[str]:
    data = yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))
    trigger = data.get("on") or data.get(True)
    return [str(row["cron"]) for row in trigger.get("schedule", [])]


def main() -> int:
    auto = json.loads((ROOT / "config/autonomous_mode.json").read_text())
    assert auto["scheduled_prepare_enabled"] is True
    assert auto["scheduled_publish_enabled"] is True
    assert auto["production_publish_activation_approved"] is True
    assert auto["pre_activation_queue_archive_required"] is True
    assert isinstance(auto["pre_activation_queue_archive_completed"], bool)
    assert auto["daily_post_cap_per_account"] == 5
    assert auto["cooldown_minutes"] <= 90
    assert auto["allow_media_posts"] is False

    mix = json.loads(
        (ROOT / "config/content_mix/default_mix.json").read_text()
    )["operational_threads_slot_mix"]
    for account in ("night_scout", "liver_manager"):
        assert sum(mix[account].values()) == 100
        assert mix[account] == {
            "new_text_generation": 5,
            "reference_text_generation": 30,
            "pdca_text_generation": 10,
            "direct_reference_media": 50,
            "approved_source_clip": 5,
        }

    expected = {
        ".github/workflows/autonomous-growth-loop-night-scout.yml": [
            "2 5 * * *",
            "2 7 * * *",
            "2 16 * * *",
        ],
        ".github/workflows/autonomous-growth-loop-liver-manager.yml": [
            "4 1 * * *",
            "4 4 * * *",
            "4 12 * * *",
        ],
        ".github/workflows/direct-reference-media-night-scout.yml": ["2 9 * * *"],
        ".github/workflows/direct-reference-media-liver-manager.yml": ["4 7 * * *"],
        ".github/workflows/media-growth-post-night-scout.yml": ["2 12 * * *"],
        ".github/workflows/media-growth-post-liver-manager.yml": ["4 9 * * *"],
        ".github/workflows/direct-media-preparation.yml": [],
        ".github/workflows/media-growth-production.yml": ["30 6 * * *"],
        ".github/workflows/media-growth-production-night-scout.yml": ["30 9 * * *"],
    }
    for path, cron_rows in expected.items():
        assert schedules(path) == cron_rows, path

    assert schedules(".github/workflows/hybrid-ai-gate-night-scout.yml") == []
    assert schedules(".github/workflows/hybrid-ai-gate-liver-manager.yml") == []

    posting_workflows = (
        ".github/workflows/autonomous-growth-loop-night-scout.yml",
        ".github/workflows/autonomous-growth-loop-liver-manager.yml",
        ".github/workflows/direct-reference-media-night-scout.yml",
        ".github/workflows/direct-reference-media-liver-manager.yml",
        ".github/workflows/media-growth-post-night-scout.yml",
        ".github/workflows/media-growth-post-liver-manager.yml",
    )
    for path in posting_workflows:
        text = (ROOT / path).read_text()
        assert "run_hybrid_ready_pipeline.py" in text or "run_scheduled_text_slot_pipeline.py" in text
        assert "GEMINI_API_KEY" in text
        assert 'selected_queue_id' in text or "run_scheduled_text_slot_pipeline.py" in text
        assert '--queue-id "$qid"' in text or "run_scheduled_text_slot_pipeline.py" in text

    for path, slot in (
        (".github/workflows/media-growth-production.yml", "lm_1800_clip_media"),
        (".github/workflows/media-growth-production-night-scout.yml", "ns_2100_clip_media"),
    ):
        text = (ROOT / path).read_text()
        assert f"--slot-id {slot}" in text
        assert "--prepare-only" in text

    direct_prepare = (ROOT / ".github/workflows/direct-media-preparation.yml").read_text()
    assert "normalize_unreviewed_slot_candidates.py" in direct_prepare

    gate_runner = (ROOT / "scripts/run_hybrid_ai_queue_gate.py").read_text()
    assert "eligible = eligible[:max_candidates]" in gate_runner
    auto_ready = (ROOT / "scripts/auto_approve_queue.py").read_text()
    assert 'parser.add_argument("--queue-id", action="append"' in auto_ready
    assert "and not args.stop_before_post" in (
        ROOT / "scripts/run_autonomous_loop.py"
    ).read_text()
    media_runner = (ROOT / "scripts/run_media_production_pipeline.py").read_text()
    assert "def prepare_saved_media_queue" in media_runner
    assert '"status": "WAITING_REVIEW"' in media_runner
    activation = (ROOT / "scripts/scheduled_publish_activation_gate.py").read_text()
    assert "pre_activation_queue_archive_not_completed" in activation
    print("PASS test_end_to_end_autopost_contract.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
