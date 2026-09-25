#!/usr/bin/env python3
"""Focused contracts for Xserver's bounded media-preparation runner."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from run_buffered_media_preparation_host import (  # noqa: E402
    MINIMUM_READY,
    _budget_allowed,
    child_environment,
    run_preparation,
    safe_summary,
    task_command,
    validate_runtime_config,
)
from run_production_readiness_acceptance import (  # noqa: E402
    publisher_usable_media_ids,
    text_ready_coverage,
)
from production_inventory import JST  # noqa: E402


def test_media_slots_do_not_reduce_text_coverage() -> None:
    covered, total = text_ready_coverage([
        {"post_type": "original_text", "missing": 0},
        {"post_type": "direct_reference_media", "missing": 1},
        {"post_type": "approved_source_clip", "missing": 1},
    ])
    assert (covered, total) == (1, 1)


def test_media_inventory_uses_publisher_hard_gate_and_distinct_assets() -> None:
    rows = []
    for index, asset in enumerate(("asset-a", "asset-a", "asset-b", "asset-c")):
        rows.append({
            "queue_id": f"queue-{index}",
            "account_id": "night_scout",
            "target_account_id": "night_scout",
            "platform": "threads",
            "status": "READY",
            "public_post_text": "独立した公開投稿本文",
            "validator_status": "PASS",
            "internal_leak_status": "PASS",
            "account_fit_status": "PASS",
            "hard_gate_status": "PASS",
            "media_readiness_status": "MEDIA_READY",
            "generation_mode": "direct_reference_media",
            "media_asset_id": asset,
            "media_url": f"https://media.example/{asset}.mp4",
        })

    def publisher(row: dict) -> dict:
        return {"status": "DRY_RUN" if row["media_asset_id"] != "asset-c" else "DRY_RUN_BLOCKED"}

    usable = publisher_usable_media_ids(
        rows,
        account="night_scout",
        route="direct_reference_media",
        publisher_check=publisher,
    )
    assert usable == {"asset-a", "asset-b"}


def test_recently_posted_assets_do_not_count_as_replenished_inventory() -> None:
    now = datetime(2026, 9, 25, 12, tzinfo=JST)
    row = {
        "queue_id": "q-recent", "account_id": "night_scout", "target_account_id": "night_scout",
        "platform": "threads", "status": "READY", "public_post_text": "別の新規本文です",
        "validator_status": "PASS", "internal_leak_status": "PASS", "account_fit_status": "PASS",
        "hard_gate_status": "PASS", "media_readiness_status": "MEDIA_READY",
        "generation_mode": "direct_reference_media", "media_asset_id": "asset-recent",
        "media_url": "https://media.example/recent.mp4",
    }
    posted = [{"account_id": "night_scout", "status": "POSTED", "real_post": "true",
               "media_asset_id": "asset-recent", "posted_at": (now - timedelta(hours=12)).isoformat()}]
    assert publisher_usable_media_ids([row], account="night_scout", route="direct_reference_media",
        publisher_check=lambda _row: {"status": "DRY_RUN"}, posted=posted, now=now) == set()
    old = [{**posted[0], "posted_at": (now - timedelta(days=8)).isoformat()}]
    assert publisher_usable_media_ids([row], account="night_scout", route="direct_reference_media",
        publisher_check=lambda _row: {"status": "DRY_RUN"}, posted=old, now=now) == {"asset-recent"}


def test_runtime_configuration_and_cloudinary_fail_closed() -> None:
    env = {
        "SPREADSHEET_ID": "placeholder",
        "GCP_SA_JSON_BASE64": "placeholder",
        "CLOUDINARY_CLOUD_NAME": "placeholder",
        "CLOUDINARY_API_KEY": "placeholder",
        "CLOUDINARY_API_SECRET": "placeholder",
        "GEMINI_API_KEY": "placeholder",
    }
    assert validate_runtime_config(ROOT, env) == []
    assert not _budget_allowed({"status": "PASS", "preparation_allowed": True, "cloudinary_status": "UNAVAILABLE"})
    assert _budget_allowed({"status": "PASS", "preparation_allowed": True, "cloudinary_status": "AVAILABLE"})
    assert MINIMUM_READY == 3


def test_preparation_commands_are_bounded_and_never_publish() -> None:
    base = {
        "PUBLISH_ENABLED": "true",
        "ALLOW_REAL_THREADS_POST": "true",
        "ALLOW_REAL_X_POST": "true",
        "ALLOW_MEDIA_POSTS": "true",
        "GITHUB_TOKEN": "not-forwarded",
        "THREADS_ACCESS_TOKEN_NIGHT_SCOUT": "not-forwarded",
        "BEAUTY_ACTIVATION_APPROVED": "true",
    }
    direct_env = child_environment(base, route="direct_reference_media")
    clip_env = child_environment(base, route="approved_source_clip")
    for child in (direct_env, clip_env):
        assert child["PUBLISH_ENABLED"] == "false"
        assert child["ALLOW_REAL_THREADS_POST"] == "false"
        assert child["ALLOW_REAL_X_POST"] == "false"
        assert child["ALLOW_MEDIA_POSTS"] == "false"
        assert "GITHUB_TOKEN" not in child
        assert "THREADS_ACCESS_TOKEN_NIGHT_SCOUT" not in child
        assert child["ALLOW_CLOUDINARY_UPLOAD"] == "true"
    assert direct_env["ALLOW_VIDEO_CUT"] == "false"
    assert clip_env["ALLOW_VIDEO_CUT"] == "true"

    direct = task_command({"account_id": "night_scout", "route": "direct_reference_media", "slot_id": "ns_1800_direct_media"}, ROOT, direct_env)
    clip = task_command({"account_id": "night_scout", "route": "approved_source_clip", "slot_id": "ns_2100_clip_media"}, ROOT, clip_env)
    direct_text, clip_text = " ".join(direct), " ".join(clip)
    assert "run_direct_media_preparation_loop.py" in direct_text
    assert "--confirm-preparation-loop" in direct
    assert "run_media_production_pipeline.py" in clip_text
    assert "--prepare-only" in clip and "--minimum-ready" in clip and "--confirm-production-media" in clip
    assert "--post-saved-media" not in clip_text
    assert "process_threads_queue.py" not in direct_text + clip_text


def test_safe_log_summary_never_includes_text_or_credentials() -> None:
    payload = {"status": "READY_INVENTORY_OK", "ready_count": 3,
               "reason": "https://user:token@example.invalid/private",
               "public_post_text": "private text", "GEMINI_API_KEY": "secret-value"}
    summary = safe_summary(payload)
    assert summary == {"status": "READY_INVENTORY_OK", "ready_count": 3}
    assert "private text" not in json.dumps(summary)
    assert "secret-value" not in json.dumps(summary)
    assert "https://" not in json.dumps(summary)


def test_started_youtube_provider_is_stopped_after_task_error() -> None:
    env = {
        "SPREADSHEET_ID": "present",
        "GCP_SA_JSON_BASE64": "present",
        "CLOUDINARY_CLOUD_NAME": "present",
        "CLOUDINARY_API_KEY": "present",
        "CLOUDINARY_API_SECRET": "present",
        "GEMINI_API_KEY": "present",
        "BEAUTY_ACTIVATION_APPROVED": "true",
    }
    state = {"budgets": 0, "provider_stopped": False}

    def fake_runner(command, **kwargs):
        if command[:2] == ["curl", "--fail"]:
            return subprocess.CompletedProcess(command, 1, "", "")
        if command[-1].endswith("start_youtube_pot_provider.sh"):
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[-1].endswith("stop_youtube_pot_provider.sh"):
            state["provider_stopped"] = True
            return subprocess.CompletedProcess(command, 0, "", "")
        if any("check_media_resource_budget.py" in str(part) for part in command):
            state["budgets"] += 1
            if state["budgets"] > 3:
                raise RuntimeError("simulated clip preparation failure")
            return subprocess.CompletedProcess(command, 0,
                '{"status":"PASS","preparation_allowed":true,"cloudinary_status":"AVAILABLE"}', "")
        if "run_direct_media_preparation_loop.py" in command:
            return subprocess.CompletedProcess(command, 0,
                '{"status":"READY","ready_media_count":3}', "")
        return subprocess.CompletedProcess(command, 0, "", "")

    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            run_preparation(root=ROOT, env=env, runner=fake_runner,
                            lock_path=Path(temp_dir) / "media-prep.lock")
        except RuntimeError as exc:
            assert "simulated" in str(exc)
        else:
            raise AssertionError("simulated preparation error was not propagated")
    assert state["provider_stopped"]


if __name__ == "__main__":
    tests = [
        test_media_slots_do_not_reduce_text_coverage,
        test_media_inventory_uses_publisher_hard_gate_and_distinct_assets,
        test_runtime_configuration_and_cloudinary_fail_closed,
        test_preparation_commands_are_bounded_and_never_publish,
        test_safe_log_summary_never_includes_text_or_credentials,
        test_started_youtube_provider_is_stopped_after_task_error,
    ]
    for test in tests:
        test()
    print(f"PASS: {len(tests)} buffered preparation/readiness contracts")
