#!/usr/bin/env python3
"""Focused contracts for Xserver's bounded media-preparation runner."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from unittest.mock import patch
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from run_buffered_media_preparation_host import (  # noqa: E402
    MINIMUM_READY,
    _budget_allowed,
    child_environment,
    cleanup_stale_workspaces,
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
import run_media_production_pipeline as media_pipeline  # noqa: E402
import sheets_record_reader  # noqa: E402


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

    reuse_env = child_environment(base, route="approved_source_clip", reuse_only=True)
    assert reuse_env["PUBLISH_ENABLED"] == "false"
    assert reuse_env["ALLOW_VIDEO_DOWNLOAD"] == "false"
    assert reuse_env["ALLOW_VIDEO_CUT"] == "false"
    assert reuse_env["ALLOW_CLOUDINARY_UPLOAD"] == "false"
    assert reuse_env["ALLOW_LOCAL_TRANSCRIPTION"] == "false"
    reuse_command = task_command(
        {"account_id": "night_scout", "route": "approved_source_clip", "slot_id": "ns_2100_clip_media"},
        ROOT,
        reuse_env,
        reuse_uploaded_only=True,
    )
    assert "--reuse-uploaded-only" in reuse_command


def test_stale_cleanup_removes_only_expired_owned_workspaces() -> None:
    now = datetime.now().timestamp()
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        old_owned = root / "run-expired"
        old_owned.mkdir()
        (old_owned / ".sns-media-prep-owned").touch()
        old_time = now - (25 * 60 * 60)
        import os
        os.utime(old_owned, (old_time, old_time))

        unmarked = root / "run-unmarked"
        unmarked.mkdir()
        os.utime(unmarked, (old_time, old_time))
        recent = root / "run-active"
        recent.mkdir()
        (recent / ".sns-media-prep-owned").touch()

        assert cleanup_stale_workspaces(root, now=now) == 1
        assert not old_owned.exists()
        assert unmarked.exists()
        assert recent.exists()


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
            if state["budgets"] > 4:
                raise RuntimeError("simulated clip preparation failure")
            return subprocess.CompletedProcess(command, 0,
                '{"status":"PASS","preparation_allowed":true,"cloudinary_status":"AVAILABLE"}', "")
        if any("run_direct_media_preparation_loop.py" in str(part) for part in command):
            return subprocess.CompletedProcess(command, 0,
                '{"status":"READY","ready_media_count":3}', "")
        return subprocess.CompletedProcess(command, 0, "", "")

    with tempfile.TemporaryDirectory() as temp_dir:
        workspaces = Path(temp_dir) / "workspaces"
        try:
            run_preparation(root=ROOT, env=env, runner=fake_runner,
                            lock_path=Path(temp_dir) / "media-prep.lock", workspace_root=workspaces)
        except RuntimeError as exc:
            assert "simulated" in str(exc)
        else:
            raise AssertionError("simulated preparation error was not propagated")
        assert state["provider_stopped"]
        assert list(workspaces.iterdir()) == []


def test_successful_preparation_removes_run_workspace() -> None:
    env = {
        "SPREADSHEET_ID": "present", "GCP_SA_JSON_BASE64": "present",
        "CLOUDINARY_CLOUD_NAME": "present", "CLOUDINARY_API_KEY": "present",
        "CLOUDINARY_API_SECRET": "present", "GEMINI_API_KEY": "present",
        "BEAUTY_ACTIVATION_APPROVED": "true",
    }

    def fake_runner(command, **kwargs):
        if command[:2] == ["curl", "--fail"]:
            return subprocess.CompletedProcess(command, 0, "ok", "")
        if any("check_media_resource_budget.py" in str(part) for part in command):
            return subprocess.CompletedProcess(command, 0,
                '{"status":"PASS","preparation_allowed":true,"cloudinary_status":"AVAILABLE"}', "")
        if any("run_direct_media_preparation_loop.py" in str(part) for part in command):
            return subprocess.CompletedProcess(command, 0, '{"status":"READY","ready_media_count":3}', "")
        if any("run_media_production_pipeline.py" in str(part) for part in command):
            assert "--reuse-uploaded-only" in command
            return subprocess.CompletedProcess(command, 0,
                '{"status":"READY_INVENTORY_OK","ready_count":3,"minimum":3}', "")
        raise AssertionError(f"unexpected runner command: {command}")

    with tempfile.TemporaryDirectory() as temp_dir:
        workspaces = Path(temp_dir) / "workspaces"
        result = run_preparation(root=ROOT, env=env, runner=fake_runner,
            lock_path=Path(temp_dir) / "media-prep.lock", workspace_root=workspaces)
        assert result["status"] == "PASS"
        assert list(workspaces.iterdir()) == []


def test_xserver_80_percent_guard_blocks_only_heavy_clip_preparation() -> None:
    env = {
        "SPREADSHEET_ID": "present", "GCP_SA_JSON_BASE64": "present",
        "CLOUDINARY_CLOUD_NAME": "present", "CLOUDINARY_API_KEY": "present",
        "CLOUDINARY_API_SECRET": "present", "GEMINI_API_KEY": "present",
        "BEAUTY_ACTIVATION_APPROVED": "true",
    }
    state = {"budgets": 0, "provider_started": False}

    def fake_runner(command, **kwargs):
        if command[:2] == ["curl", "--fail"]:
            raise AssertionError("disk guard must run before the PO Token provider")
        if any("run_direct_media_preparation_loop.py" in str(part) for part in command):
            return subprocess.CompletedProcess(command, 0, '{"status":"READY","ready_media_count":3}', "")
        if any("run_media_production_pipeline.py" in str(part) for part in command):
            if "--reuse-uploaded-only" in command:
                return subprocess.CompletedProcess(command, 1,
                    '{"status":"MEDIA_INVENTORY_LOW","ready_count":1,"minimum":3}', "")
            raise AssertionError("heavy clip preparation must not run above the disk threshold")
        if any("check_media_resource_budget.py" in str(part) for part in command):
            state["budgets"] += 1
            if state["budgets"] <= 3:
                return subprocess.CompletedProcess(command, 0,
                    '{"status":"PASS","preparation_allowed":true,"cloudinary_status":"AVAILABLE"}', "")
            return subprocess.CompletedProcess(command, 2,
                '{"status":"PREPARATION_BLOCKED","preparation_allowed":false,'
                '"cloudinary_status":"AVAILABLE","disk_used_percent":83.62,'
                '"preparation_stop_reason":"disk_prepare_threshold_reached"}', "")
        if command[-1].endswith("start_youtube_pot_provider.sh"):
            state["provider_started"] = True
        return subprocess.CompletedProcess(command, 0, "", "")

    with tempfile.TemporaryDirectory() as temp_dir:
        workspaces = Path(temp_dir) / "workspaces"
        result = run_preparation(root=ROOT, env=env, runner=fake_runner,
            lock_path=Path(temp_dir) / "media-prep.lock", workspace_root=workspaces)
        clip_results = [row for row in result["tasks"] if row["route"] == "approved_source_clip"]
        assert len(clip_results) == 2
        assert all(row["reason"] == "disk_prepare_threshold_reached" for row in clip_results)
        assert state["provider_started"] is False
        assert list(workspaces.iterdir()) == []


def test_uploaded_only_clip_reuse_never_enters_physical_preparation() -> None:
    class FakeClient:
        pass

    calls = []

    def no_saved_asset_plan(**kwargs):
        calls.append(kwargs)
        return {"status": "NO_ELIGIBLE_MEDIA", "skipped_candidates": []}

    with (
        patch.object(sheets_record_reader, "enable_readonly_record_cache", lambda _client: None),
        patch.object(sheets_record_reader, "read_records_safely", lambda _client, _tab, **_kwargs: []),
        patch.object(media_pipeline, "build_plan", side_effect=no_saved_asset_plan),
        patch.object(media_pipeline, "execute", side_effect=AssertionError("physical media work is forbidden")),
    ):
        result = media_pipeline.maintain_ready_clip_inventory(
            FakeClient(), account_id="night_scout", slot_id="ns_2100_clip_media",
            minimum=3, reuse_uploaded_only=True,
        )

    assert result["status"] == "MEDIA_INVENTORY_LOW"
    assert any(row.get("status") == "DEFERRED_RESOURCE_DEPENDENT" for row in result["attempts"])
    assert all("prepare_only" not in call or not call.get("prepare_only") for call in calls)


if __name__ == "__main__":
    tests = [
        test_media_slots_do_not_reduce_text_coverage,
        test_media_inventory_uses_publisher_hard_gate_and_distinct_assets,
        test_runtime_configuration_and_cloudinary_fail_closed,
        test_preparation_commands_are_bounded_and_never_publish,
        test_stale_cleanup_removes_only_expired_owned_workspaces,
        test_safe_log_summary_never_includes_text_or_credentials,
        test_started_youtube_provider_is_stopped_after_task_error,
        test_successful_preparation_removes_run_workspace,
        test_xserver_80_percent_guard_blocks_only_heavy_clip_preparation,
        test_uploaded_only_clip_reuse_never_enters_physical_preparation,
    ]
    for test in tests:
        test()
    print(f"PASS: {len(tests)} buffered preparation/readiness contracts")
