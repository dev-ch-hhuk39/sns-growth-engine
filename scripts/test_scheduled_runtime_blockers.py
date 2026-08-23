#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
JST = ZoneInfo("Asia/Tokyo")


def load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    guard = load("scheduled_execution_guard", "scripts/scheduled_execution_guard.py")
    policy = load("scheduled_caption_policy", "scripts/scheduled_caption_policy.py")

    within = guard.scheduled_window_decision(
        "ns_1800_direct_media",
        now=datetime(2026, 8, 6, 18, 12, tzinfo=JST),
        event_name="schedule",
    )
    assert within["status"] == "PASS"
    assert within["delay_minutes"] == 12

    early = guard.scheduled_window_decision(
        "ns_1800_direct_media",
        now=datetime(2026, 8, 6, 17, 45, tzinfo=JST),
        event_name="schedule",
    )
    assert early["status"] == "PASS"
    assert early["delay_minutes"] == -15

    delayed = guard.scheduled_window_decision(
        "ns_1800_direct_media",
        now=datetime(2026, 8, 6, 18, 18, tzinfo=JST),
        event_name="schedule",
    )
    assert delayed["status"] == "BLOCKED"
    assert delayed["publish_allowed"] is False

    manual = guard.scheduled_window_decision(
        "ns_1800_direct_media",
        now=datetime(2026, 8, 6, 23, 0, tzinfo=JST),
        event_name="workflow_dispatch",
    )
    assert manual["status"] == "PASS"
    assert manual["reason"] == "not_scheduled_event"

    old = os.environ.pop("GEMINI_API_KEY", None)
    try:
        assert guard.missing_required_secrets() == ["GEMINI_API_KEY"]
    finally:
        if old is not None:
            os.environ["GEMINI_API_KEY"] = old

    bad_night = (
        "夜職で担当や相談できる環境を選ぶとき、実際の話を判断材料として整理しておきたい。\n\n"
        "「[音楽]そこを僕たちエピグループが一括してもサポートをさせていただいております」という話があります。\n\n"
        "店を選ぶ前に確認してください。"
    )
    night = policy.normalize_scheduled_caption("night_scout", bad_night, media_origin="approved_source_clip")
    assert night["status"] == "PASS"
    assert "[音楽]" not in night["public_post_text"]
    assert "エピグループ" not in night["public_post_text"]
    assert "僕" in night["public_post_text"]
    assert "現役キャバ嬢" in night["public_post_text"]

    liver = policy.normalize_scheduled_caption(
        "liver_manager",
        "『初見が入ったら今の話題を一言で伝え、答えやすい質問を置く』という話があります。",
        media_origin="direct_reference",
    )
    assert liver["status"] == "PASS"
    assert "次の配信" in liver["public_post_text"]
    assert "現役キャバ嬢" not in liver["public_post_text"]
    assert liver["public_post_text"] != night["public_post_text"]

    normalizer = (ROOT / "scripts/normalize_scheduled_media_caption.py").read_text(encoding="utf-8")
    for queue_id in (
        "media_activation_liver_manager_approved_source_clip_c92d646a523bdbb5",
        "media_activation_liver_manager_direct_reference_media_177110184f553b45",
        "media_activation_night_scout_approved_source_clip_5698ff0b9340c2e7",
        "media_activation_night_scout_direct_reference_media_3921883bd6b80076",
    ):
        assert queue_id in normalizer

    workflow_paths = (
        ".github/workflows/autonomous-growth-loop-night-scout.yml",
        ".github/workflows/autonomous-growth-loop-liver-manager.yml",
        ".github/workflows/direct-reference-media-night-scout.yml",
        ".github/workflows/direct-reference-media-liver-manager.yml",
        ".github/workflows/media-growth-post-night-scout.yml",
        ".github/workflows/media-growth-post-liver-manager.yml",
    )
    for path in workflow_paths:
        text = (ROOT / path).read_text(encoding="utf-8")
        assert "Early runtime preflight" in text
        assert "GEMINI_API_KEY" in text
        assert "scheduled_execution_guard" in text
        assert "scheduled_publish_activation_gate.py --use-sheets >/dev/null 2>&1" not in text

    for path in workflow_paths[2:]:
        text = (ROOT / path).read_text(encoding="utf-8")
        assert "Normalize exact" in text
        assert "exit 2" in text
        assert "Runtime activation gate" in text

    hybrid = (ROOT / "scripts/run_hybrid_ai_queue_gate.py").read_text(encoding="utf-8")
    assert "FAILED_MISSING_GEMINI_API_KEY" in hybrid
    assert "SKIPPED_NO_GEMINI_API_KEY" not in hybrid

    ready = (ROOT / "scripts/run_hybrid_ready_pipeline.py").read_text(encoding="utf-8")
    assert 'return 0 if result["status"] == "READY" else 2' in ready

    print("PASS test_scheduled_runtime_blockers.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
