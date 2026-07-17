#!/usr/bin/env python3
"""Enforce free-tier media budgets without exposing credentials."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from config_loader import get_config  # noqa: E402
from sheets_client import TAB_DEFINITIONS, SheetsClient  # noqa: E402

CONFIG_FILE = ROOT / "config/media_growth_engine.json"
TRANSIENT_DIRS = (ROOT / "output/direct_media", ROOT / "output/downloads")


def _directory_bytes(path: Path) -> int:
    if not path.exists() or not path.is_dir():
        return 0
    total = 0
    for root, _, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                continue
    return total


def _cloudinary_usage() -> dict[str, Any]:
    try:
        import cloudinary.api  # type: ignore[import]

        usage = cloudinary.api.usage()
        percentages = []
        for key in ("credits", "storage", "bandwidth", "transformations"):
            item = usage.get(key) if isinstance(usage, dict) else None
            if not isinstance(item, dict):
                continue
            used = float(item.get("usage") or item.get("used") or 0)
            limit = float(item.get("limit") or 0)
            if limit > 0:
                percentages.append((used / limit) * 100)
        return {
            "status": "AVAILABLE" if percentages else "PARTIAL",
            "usage_percent": round(max(percentages), 2) if percentages else None,
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "UNAVAILABLE", "usage_percent": None, "error_type": type(exc).__name__}


def build_report(
    *,
    root: Path = ROOT,
    config: dict[str, Any] | None = None,
    disk_usage: Any | None = None,
    cloudinary: dict[str, Any] | None = None,
    temp_bytes: int | None = None,
    stored_media_count: int = 0,
    failed_retry_count: int = 0,
    whisper_processing_seconds: float = 0.0,
    gemini_status: str = "NOT_USED",
    gemini_request_count: int | None = None,
    gemini_error_count: int | None = None,
) -> dict[str, Any]:
    cfg = config or json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    limits = cfg.get("resource_limits", {})
    disk = disk_usage or shutil.disk_usage(root)
    used_percent = round((float(disk.used) / float(disk.total)) * 100, 2) if disk.total else 100.0
    cloud = cloudinary or {"status": "NOT_CHECKED", "usage_percent": None}
    cloud_percent = cloud.get("usage_percent")
    prepare_at = float(limits.get("disk_prepare_stop_percent", 80))
    text_only_at = float(limits.get("disk_text_only_percent", 90))
    cloud_text_at = float(limits.get("cloudinary_text_only_percent", 85))
    status = "PASS"
    preparation_reason = ""
    text_reason = ""
    if used_percent >= text_only_at:
        status, text_reason = "TEXT_ONLY", "disk_text_only_threshold_reached"
    elif cloud_percent is not None and float(cloud_percent) >= cloud_text_at:
        status, text_reason = "TEXT_ONLY", "cloudinary_free_tier_threshold_reached"
    elif used_percent >= prepare_at:
        status, preparation_reason = "PREPARATION_BLOCKED", "disk_prepare_threshold_reached"
    measured_temp = temp_bytes if temp_bytes is not None else sum(_directory_bytes(path) for path in TRANSIENT_DIRS)
    now = datetime.now(timezone.utc).isoformat()
    return {
        "resource_usage_id": f"resource_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "checked_at": now,
        "runner_name": os.environ.get("RUNNER_NAME", socket.gethostname()),
        "status": status,
        "media_allowed": status != "TEXT_ONLY",
        "preparation_allowed": status == "PASS",
        "media_post_allowed": status != "TEXT_ONLY",
        "disk_total_bytes": int(disk.total),
        "disk_used_bytes": int(disk.used),
        "disk_free_bytes": int(disk.free),
        "disk_used_percent": used_percent,
        "temp_bytes": int(measured_temp),
        "stored_media_count": int(stored_media_count),
        "failed_retry_count": int(failed_retry_count),
        "whisper_processing_seconds": round(float(whisper_processing_seconds), 3),
        "cloudinary_usage_percent": cloud_percent,
        "cloudinary_status": cloud.get("status", "NOT_CHECKED"),
        "gemini_status": gemini_status,
        "gemini_request_count": gemini_request_count,
        "gemini_error_count": gemini_error_count,
        "preparation_stop_reason": preparation_reason,
        "text_only_reason": text_reason,
        "notes": "Gemini is not used by this local generation path; unknown usage is not fabricated. No credential values are read into output.",
    }


def _sheets_counts(client: SheetsClient) -> tuple[int, int]:
    counts = {}
    for logical in ("media_assets", "source_post_media", "source_videos"):
        client._ensure_tab(logical, TAB_DEFINITIONS[logical])
        rows = client._call_with_rate_limit_retry(
            f"get_all_records:{logical}:resource_budget",
            lambda logical=logical: client._ws(logical).get_all_records(),
        )
        counts[logical] = [dict(row) for row in rows]
    failed = 0
    for logical in ("source_post_media", "source_videos"):
        for row in counts[logical]:
            try:
                failed += int(float(row.get("retry_count") or 0))
            except (TypeError, ValueError):
                continue
    return len(counts["media_assets"]), failed


def _save(client: SheetsClient, report: dict[str, Any]) -> None:
    ws = client._ensure_tab("resource_usage", TAB_DEFINITIONS["resource_usage"])
    headers = client._call_with_rate_limit_retry(
        "row_values:resource_usage",
        lambda: ws.row_values(1),
    )
    client._call_with_rate_limit_retry(
        "append_row:resource_usage",
        lambda: ws.append_row([str(report.get(key, "")) for key in headers], value_input_option="USER_ENTERED"),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="check free-tier media resource budget")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--check-cloudinary", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-resource-usage", action="store_true")
    parser.add_argument("--enforce", action="store_true")
    parser.add_argument("--purpose", choices=["prepare", "post"], default="prepare")
    args = parser.parse_args()
    if args.apply and not args.confirm_resource_usage:
        print(json.dumps({"status": "BLOCKED", "reason": "--apply requires --confirm-resource-usage"}))
        return 1
    client = None
    stored = retries = 0
    if args.use_sheets:
        cfg = get_config()
        client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
        stored, retries = _sheets_counts(client)
    cloud = _cloudinary_usage() if args.check_cloudinary else None
    report = build_report(cloudinary=cloud, stored_media_count=stored, failed_retry_count=retries)
    if args.apply and client:
        _save(client, report)
        report["saved_to_sheets"] = True
    else:
        report["saved_to_sheets"] = False
    print(json.dumps(report, ensure_ascii=False, indent=2))
    blocked_for_purpose = (
        not report["preparation_allowed"]
        if args.purpose == "prepare"
        else not report["media_post_allowed"]
    )
    return 2 if args.enforce and blocked_for_purpose else 0


if __name__ == "__main__":
    raise SystemExit(main())
