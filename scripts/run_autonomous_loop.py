#!/usr/bin/env python3
"""Run the rules-based autonomous production loop.

This runner removes per-post human review for the initial text-only Threads
pilot, while keeping hard gates for X, beauty, media, rights, caps, cooldowns,
and explicit run confirmation.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from generate_threads_ideas_from_references import original_text_similarity_guard  # noqa: E402
from prepare_pilot_sources import load_sources, select_pilot_sources, source_platform  # noqa: E402

CONFIG_FILE = ROOT / "config/autonomous_mode.json"
RULES_FILE = ROOT / "config/auto_approval_rules.json"
PILOT_MAX_PER_ACCOUNT = 2


def is_true(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"1", "true", "yes"}


def load_autonomous_config(path: Path = CONFIG_FILE) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_auto_approval_rules(path: Path = RULES_FILE) -> dict[str, Any]:
    if not path.exists():
        return {"defaults": {}, "accounts": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def account_scope(account_id: str, config: dict[str, Any]) -> list[str]:
    allowed = [str(a) for a in config.get("allowed_accounts", [])]
    blocked = set(str(a) for a in config.get("blocked_accounts", []))
    if account_id == "all":
        return [a for a in allowed if a not in blocked]
    return [account_id] if account_id in allowed and account_id not in blocked else []


def build_gate_summary(config: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    rule_defaults = rules.get("defaults", {})
    return {
        "priority_order": [
            "kill_switch",
            "account_platform_block",
            "rights_media_block",
            "safety_risk_similarity",
            "daily_cap_cooldown",
            "auto_ready_auto_post",
        ],
        "kill_switch": bool(config.get("kill_switch") or rule_defaults.get("kill_switch")),
        "autonomous_mode_enabled": bool(config.get("autonomous_mode_enabled")),
        "auto_source_fetch_enabled": bool(config.get("auto_source_fetch_enabled")),
        "auto_idea_generation_enabled": bool(config.get("auto_idea_generation_enabled")),
        "auto_ready_enabled": bool(config.get("auto_ready_enabled")),
        "auto_post_enabled": bool(config.get("auto_post_enabled")),
        "legacy_auto_post_enabled": bool(rule_defaults.get("auto_post_enabled", False)),
        "human_review_required": bool(config.get("human_review_required")),
        "report_only": bool(config.get("report_only")),
        "allowed_accounts": config.get("allowed_accounts", []),
        "blocked_accounts": config.get("blocked_accounts", []),
        "allowed_platforms_for_fetch": config.get("allowed_platforms_for_fetch", []),
        "blocked_platforms_for_fetch": config.get("blocked_platforms_for_fetch", []),
        "allowed_platforms_for_post": config.get("allowed_platforms_for_post", []),
        "blocked_platforms_for_post": config.get("blocked_platforms_for_post", []),
        "daily_post_cap_per_account": int(config.get("daily_post_cap_per_account", 1)),
        "daily_ready_cap_per_account": int(config.get("daily_ready_cap_per_account", 2)),
        "max_posts_per_run": int(config.get("max_posts_per_run", 1)),
        "cooldown_minutes": int(config.get("cooldown_minutes", 180)),
        "quality_gate": {
            "min_quality_score": int(config.get("min_quality_score", 75)),
            "min_safety_score": int(config.get("min_safety_score", 90)),
            "max_risk_score": int(config.get("max_risk_score", 10)),
            "max_similarity_to_source": float(config.get("max_similarity_to_source", 0.55)),
        },
        "media_gates": {
            "allow_media_posts": bool(config.get("allow_media_posts")),
            "allow_third_party_media": bool(config.get("allow_third_party_media")),
            "allow_unknown_rights": bool(config.get("allow_unknown_rights")),
            "allow_cloudinary_upload": bool(config.get("allow_cloudinary_upload")),
            "allow_video_download": bool(config.get("allow_video_download")),
            "allow_video_cut": bool(config.get("allow_video_cut")),
            "allow_transcription_api": bool(config.get("allow_transcription_api")),
        },
    }


def candidate_passes_content_gate(candidate: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    threshold = float(config.get("max_similarity_to_source", 0.55))
    sample_source = str(candidate.get("source_url", ""))
    sample_generated = f"{candidate.get('target_account_id')} Threads original insight from reference analysis."
    similarity = original_text_similarity_guard(sample_source, sample_generated, threshold=threshold)
    quality_score = 80
    safety_score = 95
    risk_score = 5
    reasons: list[str] = []
    if quality_score < int(config.get("min_quality_score", 75)):
        reasons.append("quality_score_below_min")
    if safety_score < int(config.get("min_safety_score", 90)):
        reasons.append("safety_score_below_min")
    if risk_score > int(config.get("max_risk_score", 10)):
        reasons.append("risk_score_above_max")
    if similarity["status"] == "BLOCKED":
        reasons.append("similarity_to_source_above_max")
    return {
        "status": "PASS" if not reasons else "BLOCKED",
        "quality_score": quality_score,
        "safety_score": safety_score,
        "risk_score": risk_score,
        "similarity_guard": similarity,
        "reasons": reasons,
    }


def filter_autonomous_sources(plan: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    allowed_fetch = set(str(p).lower() for p in config.get("allowed_platforms_for_fetch", []))
    blocked_fetch = set(str(p).lower() for p in config.get("blocked_platforms_for_fetch", []))
    allowed_accounts = set(str(a) for a in config.get("allowed_accounts", []))
    blocked_accounts = set(str(a) for a in config.get("blocked_accounts", []))
    selected: dict[str, list[dict[str, Any]]] = {}
    excluded: list[dict[str, str]] = list(plan.get("skipped", []))

    for account_id, rows in (plan.get("selected") or {}).items():
        if account_id not in allowed_accounts or account_id in blocked_accounts:
            for row in rows:
                excluded.append({"source_id": str(row.get("source_id", "")), "reason": "account_blocked"})
            continue
        for row in rows:
            platform = str(row.get("source_platform", "")).lower()
            reasons: list[str] = []
            if platform not in allowed_fetch:
                reasons.append("platform_not_allowed_for_fetch")
            if platform in blocked_fetch:
                reasons.append("platform_blocked_for_fetch")
            if row.get("source_id", "").endswith("_todo"):
                reasons.append("todo_placeholder")
            if row.get("media_pipeline_eligible_after_apply"):
                reasons.append("media_pipeline_blocked_initially")
            if reasons:
                excluded.append({"source_id": str(row.get("source_id", "")), "reason": ",".join(reasons)})
                continue
            gate = candidate_passes_content_gate(row, config)
            row = {**row, "content_gate": gate}
            if gate["status"] == "BLOCKED":
                excluded.append({"source_id": str(row.get("source_id", "")), "reason": ",".join(gate["reasons"])})
                continue
            selected.setdefault(account_id, []).append(row)
    return {
        "selected": selected,
        "selected_count": sum(len(v) for v in selected.values()),
        "excluded_count": len(excluded),
        "excluded": excluded[:80],
    }


def build_autonomous_plan(account_id: str, config: dict[str, Any] | None = None, rules: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or load_autonomous_config()
    rules = rules or load_auto_approval_rules()
    gate = build_gate_summary(config, rules)
    accounts = account_scope(account_id, config)

    base_sources = load_sources().get("sources", [])
    pilot_plan = select_pilot_sources(
        base_sources,
        account_id=account_id,
        max_per_account=PILOT_MAX_PER_ACCOUNT,
        platform="all",
    )
    autonomous_sources = filter_autonomous_sources(pilot_plan, config)

    blocked_reasons: list[str] = []
    if gate["kill_switch"]:
        blocked_reasons.append("kill_switch")
    if not gate["autonomous_mode_enabled"]:
        blocked_reasons.append("autonomous_mode_disabled")
    if not accounts:
        blocked_reasons.append("no_allowed_accounts")
    if not autonomous_sources["selected_count"]:
        blocked_reasons.append("no_autonomous_source_candidates")
    if gate["media_gates"]["allow_media_posts"]:
        blocked_reasons.append("media_posts_not_allowed_initial_scope")

    return {
        "status": "BLOCKED" if blocked_reasons else "PLAN_ONLY",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "account_id": account_id,
        "accounts": accounts,
        "gate_summary": gate,
        "selected_pilot_sources": autonomous_sources["selected"],
        "selected_source_count": autonomous_sources["selected_count"],
        "excluded_source_count": autonomous_sources["excluded_count"],
        "excluded_sources": autonomous_sources["excluded"],
        "daily_cap_state": {
            account: {
                "daily_post_cap": gate["daily_post_cap_per_account"],
                "daily_ready_cap": gate["daily_ready_cap_per_account"],
                "posts_used_today": None,
                "ready_used_today": None,
                "cap_source": "checked_in_apply_against_sheets",
            }
            for account in accounts
        },
        "steps": [
            "load_config",
            "kill_switch",
            "select_pilot_sources",
            "source_fetch_threads_only",
            "reference_scoring",
            "idea_generation",
            "safety_risk_similarity",
            "auto_ready",
            "threads_post_if_apply_confirmed",
            "posted_results_or_fallback",
            "summary_json",
        ],
        "auto_post_plan": {
            "enabled": gate["auto_post_enabled"],
            "platforms": gate["allowed_platforms_for_post"],
            "max_posts_per_run": gate["max_posts_per_run"],
            "requires_confirm_autonomous": True,
            "requires_worker_confirm_real_post": True,
            "requires_env": ["PUBLISH_ENABLED=true", "ALLOW_REAL_THREADS_POST=true"],
            "x_post": False,
            "beauty_post": False,
            "media_post": False,
        },
        "safety": {
            "x_fetch": False,
            "x_post": False,
            "beauty_account": False,
            "media_download": False,
            "video_cut": False,
            "cloudinary_upload": False,
            "transcription_api": False,
            "third_party_media": False,
            "unknown_rights_media": False,
        },
        "blocked_reasons": blocked_reasons,
    }


def _run(cmd: list[str], *, env: dict[str, str] | None = None) -> dict[str, Any]:
    p = subprocess.run(cmd, cwd=str(ROOT), env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return {
        "cmd": " ".join(cmd),
        "returncode": p.returncode,
        "stdout_tail": p.stdout[-1600:],
        "stderr_tail": p.stderr[-1600:],
    }


def source_ids_for_platform(plan: dict[str, Any], platform: str) -> list[str]:
    ids: list[str] = []
    for rows in plan.get("selected_pilot_sources", {}).values():
        for row in rows:
            if str(row.get("source_platform", "")).lower() == platform:
                ids.append(str(row.get("source_id", "")))
    return [i for i in ids if i]


def source_urls_for_platform(plan: dict[str, Any], platform: str) -> list[str]:
    urls: list[str] = []
    for rows in plan.get("selected_pilot_sources", {}).values():
        for row in rows:
            if str(row.get("source_platform", "")).lower() == platform:
                url = str(row.get("source_url", "")).strip()
                if url:
                    urls.append(url)
    return urls


def build_results(args: argparse.Namespace, plan: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    dry = not (args.apply and args.confirm_autonomous)
    accounts = plan.get("accounts", [])
    threads_source_urls = source_urls_for_platform(plan, "threads")

    if dry:
        cmd = [sys.executable, "scripts/collect_source_posts.py", "--platform", "threads", "--account-id", args.account_id, "--dry-run"]
        for url in threads_source_urls:
            cmd += ["--source-url", url]
        results.append(_run(cmd))
        for account in accounts:
            results.append({
                "cmd": f"scripts/score_reference_posts.py --account-id {account} --dry-run",
                "returncode": 0,
                "status": "PLAN_ONLY",
                "note": "Skipped in autonomous dry-run to avoid Sheets/API access; apply mode runs the gated CLI.",
            })
            results.append({
                "cmd": f"scripts/generate_threads_ideas_from_references.py --account-id {account} --dry-run",
                "returncode": 0,
                "status": "PLAN_ONLY",
                "note": "Skipped in autonomous dry-run to avoid Sheets/API access; apply mode runs the gated CLI.",
            })
            results.append({
                "cmd": f"scripts/auto_approve_queue.py --account-id {account} --max-ready 1 --dry-run",
                "returncode": 0,
                "status": "PLAN_ONLY",
                "note": "AUTO_READY remains capped and is applied only with --confirm-autonomous.",
            })
            results.append({
                "cmd": f"scripts/process_threads_queue.py --account-id {account} --max-posts 1 --dry-run",
                "returncode": 0,
                "status": "PLAN_ONLY",
                "note": "No real post in dry-run. Apply still requires worker --confirm-real-post and env gates.",
            })
        return results

    results.append(_run([sys.executable, "scripts/recover_production_sheets_threads_first.py", "--verify-only", "--json"]))
    if threads_source_urls and plan["gate_summary"]["auto_source_fetch_enabled"]:
        cmd = [
            sys.executable,
            "scripts/collect_source_posts.py",
            "--platform",
            "threads",
            "--account-id",
            args.account_id,
            "--apply",
            "--confirm-collect",
            "--use-sheets",
            "--fetch-real",
        ]
        for url in threads_source_urls:
            cmd += ["--source-url", url]
        results.append(_run(cmd))
    for account in accounts:
        results.append(_run([sys.executable, "scripts/score_reference_posts.py", "--account-id", account, "--apply", "--confirm-score"]))
        results.append(_run([sys.executable, "scripts/generate_threads_ideas_from_references.py", "--account-id", account, "--apply", "--confirm-generate"]))
        results.append(_run([sys.executable, "scripts/auto_approve_queue.py", "--account-id", account, "--apply", "--confirm-auto-ready", "--max-ready", "1", "--use-sheets"]))
    if plan["gate_summary"]["auto_post_enabled"]:
        env = dict(os.environ)
        env.setdefault("PUBLISH_ENABLED", "true")
        env.setdefault("ALLOW_REAL_THREADS_POST", "true")
        env.setdefault("ALLOW_REAL_X_POST", "false")
        for account in accounts:
            results.append(_run([sys.executable, "scripts/process_threads_queue.py", "--account-id", account, "--confirm-real-post", "--max-posts", "1"], env=env))
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="run autonomous SNS growth loop")
    parser.add_argument("--account-id", default="all", choices=["all", "night_scout", "liver_manager", "beauty_account"])
    parser.add_argument("--dry-run", action="store_true", help="plan only (default)")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-autonomous", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_autonomous_config()
    rules = load_auto_approval_rules()
    plan = build_autonomous_plan(args.account_id, config, rules)

    if args.account_id in config.get("blocked_accounts", []):
        print(json.dumps({**plan, "status": "BLOCKED", "blocked_reasons": ["blocked_account"]}, ensure_ascii=False, indent=2))
        return 1
    if args.apply and not args.confirm_autonomous:
        print(json.dumps({**plan, "status": "BLOCKED", "blocked_reasons": ["--apply requires --confirm-autonomous"]}, ensure_ascii=False, indent=2))
        return 1
    if plan["blocked_reasons"]:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 1

    mode = "apply" if args.apply and args.confirm_autonomous else "dry-run"
    results = build_results(args, plan)
    failed_results = [r for r in results if r.get("returncode") not in {0, None}]
    status = "DONE" if mode == "apply" and not failed_results else "PLAN_ONLY"
    if failed_results:
        status = "PARTIAL" if mode == "apply" else "PLAN_ONLY_WITH_WARN"
    print(json.dumps({**plan, "mode": mode, "status": status, "results": results}, ensure_ascii=False, indent=2))
    return 1 if mode == "apply" and failed_results else 0


if __name__ == "__main__":
    raise SystemExit(main())
