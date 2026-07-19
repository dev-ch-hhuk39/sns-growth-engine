#!/usr/bin/env python3
"""Run bounded OSS trend research and persist non-publishing evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

from config_loader import get_config
from reference.fetchers.last30days_fetcher import Last30DaysFetcher
from sheets_client import TAB_DEFINITIONS, SheetsClient

TOPICS_PATH = ROOT / "config" / "research_topics.json"
ALLOWED_ACCOUNTS = ("night_scout", "liver_manager")


def stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:20]
    return f"{prefix}_{digest}"


def platform_for_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "youtube" in host or "youtu.be" in host:
        return "youtube"
    if "tiktok" in host:
        return "tiktok"
    if "threads" in host:
        return "threads"
    if host in {"x.com", "twitter.com", "www.x.com", "www.twitter.com"}:
        return "x"
    return "web"


def agent_reach_doctor() -> dict[str, Any]:
    try:
        completed = subprocess.run(
            ["agent-reach", "doctor", "--json"],
            capture_output=True,
            text=True,
            timeout=90,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "UNAVAILABLE", "reason": type(exc).__name__, "channel_count": 0}
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {}
    channel_count = len(payload) if isinstance(payload, dict) else 0
    return {
        "status": "PASS" if completed.returncode == 0 and channel_count else "PARTIAL",
        "reason": "doctor_completed" if completed.returncode == 0 else "doctor_nonzero",
        "channel_count": channel_count,
    }


def _append_unique(client: SheetsClient, logical: str, identity: str, row: dict[str, Any]) -> bool:
    ws = client._ensure_tab(logical, TAB_DEFINITIONS[logical])
    headers = client._call_with_rate_limit_retry(f"headers:{logical}:research", lambda: ws.row_values(1))
    rows = client._call_with_rate_limit_retry(f"rows:{logical}:research", lambda: ws.get_all_records())
    if any(str(item.get(identity, "")) == str(row.get(identity, "")) for item in rows):
        return False
    client._call_with_rate_limit_retry(
        f"append:{logical}:research",
        lambda: ws.append_row([str(row.get(header, "")) for header in headers], value_input_option="USER_ENTERED"),
    )
    return True


def run(account_id: str, max_topics: int, max_results: int, *, apply: bool) -> dict[str, Any]:
    config = json.loads(TOPICS_PATH.read_text(encoding="utf-8"))
    accounts = list(ALLOWED_ACCOUNTS) if account_id == "all" else [account_id]
    selected = [(account, topic) for account in accounts for topic in config.get(account, [])[:max_topics]]
    result: dict[str, Any] = {
        "status": "PLAN_ONLY" if not apply else "APPLIED",
        "account_id": account_id,
        "selected_query_count": len(selected),
        "selected_queries": [{"account_id": account, "query": topic} for account, topic in selected],
        "agent_reach_doctor": {"status": "PLANNED", "channel_count": 0},
        "trend_signal_count": 0,
        "source_candidate_count": 0,
        "topic_opportunity_count": 0,
        "content_angle_count": 0,
        "warnings": [],
        "would_publish": False,
        "would_download": False,
    }
    if not apply:
        return result

    cfg = get_config()
    client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    now = datetime.now(timezone.utc).isoformat()
    day = now[:10]
    doctor = agent_reach_doctor()
    result["agent_reach_doctor"] = doctor
    doctor_row = {
        "provider_run_id": stable_id("pr", "agent_reach_doctor", day),
        "platform": "cross_channel",
        "capability": "research.backend_doctor",
        "provider_name": "agent_reach",
        "provider_version": "1.5.0-pinned",
        "status": doctor["status"],
        "reason": f"{doctor['reason']};channels={doctor['channel_count']}",
        "retryable": "true" if doctor["status"] != "PASS" else "false",
        "attempt_count": "1",
        "created_at": now,
    }
    _append_unique(client, "provider_runs", "provider_run_id", doctor_row)

    fetcher = Last30DaysFetcher()
    for account, topic in selected:
        source_id = stable_id("research", account, topic)
        fetched = fetcher.fetch(
            {"source_id": source_id, "source_platform": "query", "source_handle": topic, "rights_policy": "reference_only", "reuse_policy": "reference_only", "media_policy": "do_not_download"},
            target_account_id=account,
            mock=False,
            dry_run=False,
            confirm_fetch=True,
            max_items=max_results,
            query=topic,
            platforms=["threads", "youtube", "tiktok", "web"],
        )
        provider_row = {
            "provider_run_id": stable_id("pr", "last30days", account, topic, day),
            "source_id": source_id,
            "platform": "cross_channel",
            "capability": "research.trends",
            "provider_name": "last30days_skill",
            "provider_version": "3.16.0-pinned",
            "status": "PASS" if fetched.status == "OK" else fetched.status,
            "reason": str(fetched.message)[:240],
            "retryable": "true" if fetched.status in {"ERROR", "NOT_INSTALLED"} else "false",
            "attempt_count": "1",
            "created_at": now,
        }
        _append_unique(client, "provider_runs", "provider_run_id", provider_row)
        if fetched.status != "OK":
            result["warnings"].append({"account_id": account, "query": topic, "status": fetched.status})
            continue
        for item in fetched.items:
            raw = item.to_dict()
            evidence = list((raw.get("raw_payload_compact") or {}).get("evidence_items", []))
            signal_id = stable_id("trend", account, topic, raw.get("title", ""), day)
            trend = {
                "trend_signal_id": signal_id,
                "account_id": account,
                "platform": "cross_channel",
                "topic": raw.get("title") or raw.get("text", ""),
                "signal_summary": raw.get("description", ""),
                "source_count": str(len(evidence)),
                "window_days": "30",
                "collection_backend": "last30days_skill",
                "status": "WAITING_REVIEW",
                "created_at": now,
                "updated_at": now,
            }
            if _append_unique(client, "trend_signals", "trend_signal_id", trend):
                result["trend_signal_count"] += 1
            opportunity = {
                "topic_opportunity_id": stable_id("topic", signal_id),
                "account_id": account,
                "topic": trend["topic"],
                "summary": trend["signal_summary"],
                "source_count": trend["source_count"],
                "window_days": "30",
                "research_backend": "last30days_skill",
                "status": "WAITING_REVIEW",
                "created_at": now,
                "updated_at": now,
            }
            if _append_unique(client, "topic_opportunities", "topic_opportunity_id", opportunity):
                result["topic_opportunity_count"] += 1
            angle = {
                "content_angle_id": stable_id("angle", signal_id, "reader_facing_explainer"),
                "account_id": account,
                "topic": trend["topic"],
                "angle": "reader_facing_explainer",
                "evidence_summary": trend["signal_summary"],
                "research_backend": "last30days_skill",
                "status": "WAITING_REVIEW",
                "created_at": now,
                "updated_at": now,
            }
            if _append_unique(client, "content_angles", "content_angle_id", angle):
                result["content_angle_count"] += 1
            for evidence_item in evidence[:10]:
                url = str(evidence_item.get("url", "")).strip()
                if not url.startswith("https://"):
                    continue
                candidate = {
                    "source_candidate_id": stable_id("candidate", account, url),
                    "account_id": account,
                    "candidate_url": url,
                    "platform": platform_for_url(url),
                    "discovery_backend": "last30days_skill",
                    "reason": f"Evidence for: {trend['topic']}"[:240],
                    "status": "WAITING_REVIEW",
                    "created_at": now,
                    "updated_at": now,
                }
                if _append_unique(client, "source_candidates", "source_candidate_id", candidate):
                    result["source_candidate_count"] += 1
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="bounded Agent-Reach/last30days source research")
    parser.add_argument("--account-id", choices=["all", *ALLOWED_ACCOUNTS], default="all")
    parser.add_argument("--max-topics-per-account", type=int, default=1)
    parser.add_argument("--max-results", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-research", action="store_true")
    parser.add_argument("--use-sheets", action="store_true")
    args = parser.parse_args()
    if args.apply and (not args.confirm_research or not args.use_sheets):
        print(json.dumps({"status": "BLOCKED", "reason": "--apply requires --confirm-research and --use-sheets"}))
        return 1
    if args.apply and args.dry_run:
        print(json.dumps({"status": "BLOCKED", "reason": "choose --dry-run or --apply"}))
        return 1
    report = run(
        args.account_id,
        max(1, min(args.max_topics_per_account, 3)),
        max(1, min(args.max_results, 50)),
        apply=args.apply,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"PLAN_ONLY", "APPLIED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
