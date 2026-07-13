#!/usr/bin/env python3
"""Read-only autonomous posting health check.

This command never posts, never mutates Sheets, and never prints secret values.
It is intended for local dry-runs and GitHub Actions summary diagnostics.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


WORKFLOWS = {
    "manual": ROOT / ".github/workflows/autonomous-growth-loop.yml",
    "night_scout": ROOT / ".github/workflows/autonomous-growth-loop-night-scout.yml",
    "liver_manager": ROOT / ".github/workflows/autonomous-growth-loop-liver-manager.yml",
    "production_aftercare": ROOT / ".github/workflows/production-autopilot-aftercare.yml",
    "media_prepare_liver_manager": ROOT / ".github/workflows/media-growth-production.yml",
    "media_prepare_night_scout": ROOT / ".github/workflows/media-growth-production-night-scout.yml",
    "media_post_liver_manager": ROOT / ".github/workflows/media-growth-post-liver-manager.yml",
    "media_post_night_scout": ROOT / ".github/workflows/media-growth-post-night-scout.yml",
}

EXPECTED_CRONS = {
    "night_scout": {"45 4 * * *", "45 6 * * *", "45 8 * * *", "45 15 * * *"},
    "liver_manager": {"45 0 * * *", "45 3 * * *", "45 6 * * *", "45 11 * * *"},
    "media_prepare_liver_manager": {"20 22 * * *"},
    "media_prepare_night_scout": {"20 2 * * *"},
    "media_post_liver_manager": {"45 8 * * *"},
    "media_post_night_scout": {"45 11 * * *"},
}


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _workflow_text(key: str) -> str:
    path = WORKFLOWS[key]
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _crons(text: str) -> set[str]:
    return set(re.findall(r'cron:\s*"([^"]+)"', text))


def _env_present(*names: str) -> bool:
    return any(bool(os.environ.get(name)) for name in names)


def _source_registry_sanity() -> dict[str, Any]:
    data = _json(ROOT / "config/source_accounts/default_sources.json")
    sources = list(data.get("sources", []))
    chi = [s for s in sources if s.get("source_id") == "src_ns_threads_user_chiishunin_s"]
    beauty_active = [
        s.get("source_id", "")
        for s in sources
        if "beauty_account" in s.get("target_account_ids", []) and str(s.get("active", "")).lower() == "true"
    ]
    x_fetch = [
        s.get("source_id", "")
        for s in sources
        if str(s.get("source_platform", "")).lower() == "x" and str(s.get("fetch_enabled", "")).lower() == "true"
    ]
    return {
        "source_count": len(sources),
        "chiishunin_s_present": bool(chi),
        "chiishunin_s_fetch_enabled": bool(chi and chi[0].get("fetch_enabled") is True),
        "beauty_active_count": len(beauty_active),
        "beauty_active_source_ids": beauty_active[:20],
        "x_fetch_enabled_count": len(x_fetch),
        "x_fetch_enabled_source_ids": x_fetch[:20],
    }


def _schema_sanity() -> dict[str, Any]:
    from sheets_client import TAB_DEFINITIONS

    required = {
        "queue": [
            "queue_id", "draft_id", "account_id", "platform", "status", "auto_publish",
            "generation_mode", "media_asset_id", "auto_ready_by", "quality_score", "risk_score",
            "source_video_id", "clip_candidate_id", "media_url", "media_status", "media_required",
        ],
        "posted_results": [
            "result_id", "queue_id", "draft_id", "account_id", "platform", "post_url",
            "posted_text", "status", "metrics_status", "real_post",
            "source_video_id", "clip_candidate_id",
        ],
        "source_videos": ["source_video_id", "source_id", "video_id", "canonical_video_url", "duplicate_key"],
    }
    missing = {
        tab: [col for col in cols if col not in TAB_DEFINITIONS.get(tab, [])]
        for tab, cols in required.items()
    }
    return {
        "required_tabs_present": {tab: tab in TAB_DEFINITIONS for tab in required},
        "missing_required_columns": {tab: cols for tab, cols in missing.items() if cols},
    }


def build_health(account_id: str) -> dict[str, Any]:
    config = _json(ROOT / "config/autonomous_mode.json")
    media_config = _json(ROOT / "config/media_growth_engine.json")
    workflow_results: dict[str, Any] = {}
    problems: list[str] = []
    for key, path in WORKFLOWS.items():
        text = _workflow_text(key)
        wf = {
            "exists": path.exists(),
            "has_schedule": "schedule:" in text,
            "has_workflow_dispatch": "workflow_dispatch:" in text,
            "has_permissions_contents_read": "contents: read" in text,
            "has_permissions_actions_read": "actions: read" in text,
            "has_concurrency": "concurrency:" in text and "cancel-in-progress: false" in text,
            "has_heartbeat": "Schedule heartbeat" in text and "github.workflow" in text and "date -u" in text,
            "has_dry_run_only_dispatch": "dry_run_only:" in text,
            "dry_run_only_skips_apply": "dry_run_only != 'true'" in text,
            "has_jitter": "random.randint(0, 1800)" in text,
            "has_apply_step": "--confirm-autonomous" in text or "--confirm-production-media" in text,
            "apply_env_scoped": 'PUBLISH_ENABLED: "true"' in text and 'ALLOW_REAL_THREADS_POST: "true"' in text,
            "x_post_false": 'ALLOW_REAL_X_POST: "false"' in text,
            "media_disabled": all(flag in text for flag in [
                'ALLOW_VIDEO_DOWNLOAD: "false"',
                'ALLOW_VIDEO_CUT: "false"',
                'ALLOW_CLOUDINARY_UPLOAD: "false"',
                'ALLOW_TRANSCRIPTION_API: "false"',
            ]),
            "crons": sorted(_crons(text)),
        }
        if key in EXPECTED_CRONS and set(wf["crons"]) != EXPECTED_CRONS[key]:
            problems.append(f"{key}:schedule_mismatch")
        if key == "manual" and wf["has_schedule"]:
            problems.append("manual_workflow_has_schedule")
        if key != "manual" and not wf["has_schedule"]:
            problems.append(f"{key}:schedule_missing")
        if not wf["has_permissions_contents_read"] or not wf["has_permissions_actions_read"]:
            problems.append(f"{key}:permissions_missing")
        if not wf["has_concurrency"]:
            problems.append(f"{key}:concurrency_missing")
        if not wf["has_heartbeat"]:
            problems.append(f"{key}:heartbeat_missing")
        if not wf["has_dry_run_only_dispatch"] or not wf["dry_run_only_skips_apply"]:
            problems.append(f"{key}:dry_run_only_missing_or_unsafe")
        workflow_results[key] = wf

    source = _source_registry_sanity()
    if not source["chiishunin_s_present"]:
        problems.append("chiishunin_s_source_missing")
    if source["beauty_active_count"]:
        problems.append("beauty_account_active_sources")
    if source["x_fetch_enabled_count"]:
        problems.append("x_fetch_enabled")
    if config.get("kill_switch"):
        problems.append("kill_switch_true")
    if not config.get("auto_post_enabled"):
        problems.append("auto_post_disabled")
    schema = _schema_sanity()
    if schema["missing_required_columns"]:
        problems.append("schema_missing_required_columns")

    return {
        "status": "PASS" if not problems else "WARN",
        "account_id": account_id,
        "dry_run": True,
        "workflow_files": workflow_results,
        "config": {
            "autonomous_mode_enabled": bool(config.get("autonomous_mode_enabled")),
            "auto_post_enabled": bool(config.get("auto_post_enabled")),
            "kill_switch": bool(config.get("kill_switch")),
            "daily_post_cap_per_account": config.get("daily_post_cap_per_account"),
            "max_posts_per_run": config.get("max_posts_per_run"),
            "cooldown_minutes": config.get("cooldown_minutes"),
            "allowed_accounts": config.get("allowed_accounts", []),
        },
        "secret_presence": {
            "sheets_id_present": _env_present("SNS_MASTER_SHEET_ID", "SPREADSHEET_ID"),
            "sheets_service_account_present": _env_present("SA_JSON_BASE64", "GCP_SA_JSON_BASE64"),
            "night_scout_threads_credentials_present": _env_present("THREADS_ACCESS_TOKEN_NIGHT_SCOUT") and _env_present("THREADS_USER_ID_NIGHT_SCOUT"),
            "liver_manager_threads_credentials_present": _env_present("THREADS_ACCESS_TOKEN_LIVER_MANAGER") and _env_present("THREADS_USER_ID_LIVER_MANAGER"),
            "cloudinary_credentials_present": all(_env_present(name) for name in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET")),
        },
        "sheets_schema_expected": schema,
        "source_registry": source,
        "queue_status_counts": {"status": "NOT_CHECKED_DRY_RUN_NO_SHEETS_READ"},
        "posted_results_recent_status": {"status": "NOT_CHECKED_DRY_RUN_NO_SHEETS_READ"},
        "validator_sanity": {"final_public_post_validator": "EXPECTED_IN_RUNNER_AND_WORKER"},
        "media_schedule": {
            "text_only_schedule_on": True,
            "media_schedule_on": bool(media_config.get("media_schedule_enabled")) and all(
                workflow_results.get(key, {}).get("has_schedule", False)
                for key in ("media_prepare_liver_manager", "media_prepare_night_scout", "media_post_liver_manager", "media_post_night_scout")
            ),
            "media_growth_engine_enabled": bool(media_config.get("media_growth_engine_enabled")),
            "source_video_discovery_apply_enabled": bool(media_config.get("source_video_discovery_apply_enabled")),
            "auto_save_discovered_videos": bool(media_config.get("auto_save_discovered_videos")),
            "auto_save_clip_candidates": bool(media_config.get("auto_save_clip_candidates")),
            "media_public_post_auto_enabled": bool(media_config.get("media_public_post_auto_enabled")),
            "download_enabled": bool(media_config.get("download_enabled")),
            "cut_enabled": bool(media_config.get("cut_enabled")),
            "upload_enabled": bool(media_config.get("upload_enabled")),
            "video_post_enabled": bool(media_config.get("video_post_enabled")),
            "subtitle_enabled": bool(media_config.get("subtitle_enabled")),
        },
        "problems": problems,
        "recommended_fixes": [] if not problems else [
            "Check listed workflow/config/source/schema items before the next scheduled run.",
            "If a scheduled run posts nothing, inspect health_summary.no_post_reason in the Actions log.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="read-only autonomous health check")
    parser.add_argument("--account-id", default="all", choices=["all", "night_scout", "liver_manager", "beauty_account"])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = build_health(args.account_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"PASS", "WARN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
