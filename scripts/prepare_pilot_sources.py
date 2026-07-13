#!/usr/bin/env python3
"""Plan a tiny production source-fetch pilot without enabling it by default."""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCES_FILE = ROOT / "config/source_accounts/default_sources.json"
ALLOWED_ACCOUNTS = {"night_scout", "liver_manager"}
ALLOWED_PLATFORMS = {"threads", "youtube", "tiktok"}
APPROVED_MEDIA_RIGHTS = {"owned", "licensed", "approved_creator_clip"}
REFERENCE_FETCH_RIGHTS = {"reference_only", "third_party_reference_only", *APPROVED_MEDIA_RIGHTS}


def is_true(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"1", "true", "yes"}


def load_sources() -> dict[str, Any]:
    return json.loads(SOURCES_FILE.read_text(encoding="utf-8"))


def targets_for(source: dict[str, Any]) -> list[str]:
    targets = source.get("target_account_ids") or [source.get("target_account_id") or source.get("account_id")]
    return [str(t) for t in targets if t]


def source_platform(source: dict[str, Any]) -> str:
    return str(source.get("source_platform") or source.get("platform") or "").lower()


def source_url(source: dict[str, Any]) -> str:
    return str(source.get("source_url") or source.get("url") or source.get("canonical_url") or "").strip()


def exclusion_reason(source: dict[str, Any], *, account_id: str, platform: str) -> str:
    targets = targets_for(source)
    src_platform = source_platform(source)
    url = source_url(source)
    source_id = str(source.get("source_id", ""))
    if source.get("current_status") in {"needs_human_url", "needs_rights_review"} or source_id.endswith("_todo"):
        return "todo_placeholder"
    if not url:
        return "missing_real_url"
    # Explicitly enabled Threads reference sources are safe, bounded
    # collection candidates even when the historical registry labelled their
    # acquisition method manual_url.
    reference_autopilot = is_true(source.get("reference_autopilot_enabled"))
    if is_true(source.get("manual_only")) and not reference_autopilot:
        return "manual_only_reference_source"
    if any(t == "beauty_account" for t in targets):
        return "beauty_excluded"
    if account_id != "all" and account_id not in targets:
        return "account_not_targeted"
    if src_platform == "x":
        return "x_disabled"
    if platform != "all" and src_platform != platform:
        return "platform_mismatch"
    if src_platform not in ALLOWED_PLATFORMS:
        return "platform_not_allowed_for_pilot"
    if src_platform == "tiktok" and "/video/" not in url:
        return "tiktok_requires_individual_video_url"
    rights_status = str(source.get("rights_status") or source.get("rights_policy") or "unknown").lower()
    if rights_status not in REFERENCE_FETCH_RIGHTS:
        return "rights_not_ready_for_pilot"
    return ""


def build_candidate(source: dict[str, Any], account_id: str) -> dict[str, Any]:
    rights_status = str(source.get("rights_status") or source.get("rights_policy") or "third_party_reference_only").lower()
    return {
        "source_id": source.get("source_id", ""),
        "source_url": source_url(source),
        "source_platform": source_platform(source),
        "target_account_id": account_id,
        "rights_status": rights_status,
        "fetch_enabled_after_apply": True,
        "manual_only_after_apply": False,
        "media_download": False,
        "clip_enabled_after_apply": False,
        "media_pipeline_eligible_after_apply": rights_status in APPROVED_MEDIA_RIGHTS and is_true(source.get("clip_enabled")),
        "usage_scope": source.get("usage_scope") or "reference_analysis",
        "notes": "Pilot fetch candidate only. No X, beauty, TODO, media download, cut, upload, or post.",
    }


def select_pilot_sources(
    sources: list[dict[str, Any]],
    *,
    account_id: str = "all",
    max_per_account: int = 2,
    platform: str = "all",
) -> dict[str, Any]:
    selected: dict[str, list[dict[str, Any]]] = {acct: [] for acct in sorted(ALLOWED_ACCOUNTS)}
    skipped: list[dict[str, str]] = []
    platform_priority = {"threads": 0, "youtube": 1, "tiktok": 2}
    ordered = sorted(
        sources,
        key=lambda s: (platform_priority.get(source_platform(s), 9), str(s.get("priority", 999)), str(s.get("source_id", ""))),
    )
    for source in ordered:
        src_targets = [t for t in targets_for(source) if t in ALLOWED_ACCOUNTS]
        if account_id != "all":
            src_targets = [t for t in src_targets if t == account_id]
        if not src_targets:
            reason = exclusion_reason(source, account_id=account_id, platform=platform) or "no_allowed_account_target"
            skipped.append({"source_id": str(source.get("source_id", "")), "reason": reason})
            continue
        for acct in src_targets:
            reason = exclusion_reason(source, account_id=acct, platform=platform)
            if reason:
                skipped.append({"source_id": str(source.get("source_id", "")), "reason": reason})
                continue
            if len(selected[acct]) >= max_per_account:
                skipped.append({"source_id": str(source.get("source_id", "")), "reason": "account_candidate_limit"})
                continue
            selected[acct].append(build_candidate(source, acct))
    selected = {acct: rows for acct, rows in selected.items() if account_id == "all" or acct == account_id}
    return {
        "status": "PLAN_ONLY",
        "selected": selected,
        "candidate_count": sum(len(v) for v in selected.values()),
        "skipped_count": len(skipped),
        "skipped": skipped[:50],
        "safety": {
            "x_fetch": False,
            "beauty_account": False,
            "todo_placeholders": False,
            "media_download": False,
            "auto_post": False,
            "real_post": False,
        },
    }


def apply_pilot_sources(data: dict[str, Any], selected: dict[str, list[dict[str, Any]]]) -> int:
    selected_ids = {row["source_id"] for rows in selected.values() for row in rows}
    count = 0
    now = datetime.now(timezone.utc).isoformat()
    for source in data.get("sources", []):
        if source.get("source_id") in selected_ids:
            source["fetch_enabled"] = True
            source["manual_only"] = False
            source["pilot_enabled"] = True
            source["pilot_enabled_at"] = now
            count += 1
    SOURCES_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="prepare tiny pilot source set")
    parser.add_argument("--account-id", default="all", choices=["all", "night_scout", "liver_manager"])
    parser.add_argument("--max-per-account", type=int, default=2)
    parser.add_argument("--platform", default="all", choices=["all", "threads", "youtube", "tiktok"])
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-pilot", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data = load_sources()
    plan = select_pilot_sources(
        data.get("sources", []),
        account_id=args.account_id,
        max_per_account=max(1, args.max_per_account),
        platform=args.platform,
    )
    if not args.apply:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    if not args.confirm_pilot:
        print(json.dumps({**plan, "status": "BLOCKED", "blocked_reasons": ["--apply requires --confirm-pilot"]}, ensure_ascii=False, indent=2))
        return 1
    applied = apply_pilot_sources(data, plan["selected"])
    print(json.dumps({**plan, "status": "APPLIED", "applied_count": applied}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
