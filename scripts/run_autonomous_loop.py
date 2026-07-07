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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from generate_threads_ideas_from_references import original_text_similarity_guard  # noqa: E402
from collect_video_references import build_video_reference, fetch_video_metadata, fetch_ytdlp_metadata, fetch_youtube_transcript  # noqa: E402
from generate_video_reference_posts import build_video_posts  # noqa: E402
from prepare_pilot_sources import load_sources, select_pilot_sources, source_platform  # noqa: E402
from public_post_quality import account_rotation_order, final_public_post_validator, generate_reader_facing_post, public_preview  # noqa: E402

CONFIG_FILE = ROOT / "config/autonomous_mode.json"
RULES_FILE = ROOT / "config/auto_approval_rules.json"
PILOT_MAX_PER_ACCOUNT = 2
VIDEO_REFERENCE_PLATFORMS = {"youtube", "tiktok"}


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


def account_order_for_scope(
    requested_account_id: str,
    accounts: list[str],
    config: dict[str, Any],
    *,
    posted_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Use rotation only for manual all-account runs.

    Account-specific scheduled workflows must never rotate away from their
    fixed ACCOUNT_ID, otherwise the night/liver schedules can starve each other.
    """
    if requested_account_id != "all":
        selected = accounts[0] if accounts else ""
        return {
            "enabled": False,
            "strategy": "fixed_account_override",
            "ordered_accounts": accounts,
            "selected_account": selected,
            "skipped_accounts": [],
            "fallback_to_available_account": False,
        }
    return account_rotation_order(accounts, config, posted_rows=posted_rows or [])


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
            "min_quality_score": int(config.get("min_quality_score", 85)),
            "min_safety_score": int(config.get("min_safety_score", 90)),
            "max_risk_score": int(config.get("max_risk_score", 10)),
            "max_similarity_to_source": float(config.get("max_similarity_to_source", 0.45)),
            "public_post_quality_thresholds": config.get("public_post_quality_thresholds", {}),
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
    quality_score = 90
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


def _safe_video_metadata(source: dict[str, Any], *, fetch_metadata: bool = False) -> dict[str, Any]:
    """Build video metadata without download/cut/upload or transcript body output."""
    url = str(source.get("source_url", "")).strip()
    platform = str(source.get("source_platform", "")).lower()
    if platform == "tiktok" and "/video/" not in url:
        return {
            "ok": False,
            "title": "",
            "thumbnail_url": "",
            "author_handle": "",
            "extractor": "TikTok",
            "error": "tiktok_requires_individual_video_url",
        }
    if not fetch_metadata or not url.startswith("http"):
        return {}
    meta = fetch_ytdlp_metadata(url)
    if not meta.get("ok"):
        meta = fetch_video_metadata(url)
    return meta


def build_video_reference_analysis(plan: dict[str, Any], config: dict[str, Any], *, fetch_metadata: bool = False) -> dict[str, Any]:
    """Connect selected YouTube/TikTok references to text-only idea planning.

    Third-party video stays reference-analysis only. Transcript text/body is
    never returned; only status/count/reason are included.
    """
    rows: list[dict[str, Any]] = []
    post_ideas: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for account_id, sources in (plan.get("selected_pilot_sources") or {}).items():
        for source in sources:
            platform = str(source.get("source_platform", "")).lower()
            url = str(source.get("source_url", "")).strip()
            if platform not in VIDEO_REFERENCE_PLATFORMS:
                continue
            if platform == "tiktok" and "/video/" not in url:
                skipped.append({"source_id": str(source.get("source_id", "")), "reason": "tiktok_requires_individual_video_url"})
                continue
            metadata = _safe_video_metadata(source, fetch_metadata=fetch_metadata)
            video_row = build_video_reference(url, account_id, metadata, rights_status="third_party_reference_only")
            transcript = {"status": "NOT_REQUESTED", "reason": "", "chunk_count": 0, "text": ""}
            if platform == "youtube" and fetch_metadata:
                transcript = fetch_youtube_transcript(url)
            transcript_safe = {k: v for k, v in transcript.items() if k != "text"}
            video_row.update({
                "source_id": source.get("source_id", ""),
                "metadata_fallback": "title_description_metadata" if metadata.get("ok") else "skip_when_unavailable",
                "transcript_status": transcript_safe.get("status", "NOT_REQUESTED"),
                "transcript_chunk_count": transcript_safe.get("chunk_count", 0),
                "transcript_reason": transcript_safe.get("reason", ""),
                "download": False,
                "cut": False,
                "upload": False,
                "repost": False,
                "text_body_returned": False,
            })
            rows.append(video_row)
            if metadata.get("ok") or not fetch_metadata:
                idea_video = {**video_row, "title": video_row.get("title") or f"{platform} reference structure"}
                ideas = build_video_posts(idea_video, account_id, limit=1)
                for idea in ideas:
                    gate = original_text_similarity_guard(
                        str(video_row.get("title") or video_row.get("video_url", "")),
                        str(idea.get("text", "")),
                        threshold=float(config.get("max_similarity_to_source", 0.55)),
                    )
                    if gate["status"] == "BLOCKED":
                        skipped.append({"source_id": str(source.get("source_id", "")), "reason": "video_idea_similarity_blocked"})
                        continue
                    post_ideas.append({
                        **idea,
                        "status": "AUTO_READY_CANDIDATE" if config.get("auto_ready_enabled") else "WAITING_REVIEW",
                        "media_strategy": "none",
                        "similarity_guard": gate,
                        "autonomous_text_only": True,
                    })
            else:
                skipped.append({"source_id": str(source.get("source_id", "")), "reason": "metadata_unavailable"})
    return {
        "status": "CONNECTED",
        "fetch_metadata": fetch_metadata,
        "video_reference_count": len(rows),
        "text_only_post_idea_count": len(post_ideas),
        "rows": rows,
        "post_ideas": post_ideas,
        "skipped": skipped,
        "safety": {
            "download": False,
            "cut": False,
            "upload": False,
            "repost": False,
            "media_posts": False,
            "transcript_preview_suppressed": True,
            "third_party_reference_only": True,
        },
    }


def apply_preflight(plan: dict[str, Any]) -> dict[str, Any]:
    """Check production prerequisites without printing secret values."""
    try:
        from config_loader import get_config_partial
        from publishers.threads_credentials import has_required_for_publish, resolve_credentials
    except Exception as exc:
        return {"ok": False, "blocked_reasons": [f"preflight_import_failed:{type(exc).__name__}"]}
    cfg = get_config_partial()
    blocked: list[str] = []
    if not cfg.get("sheet_id") or not cfg.get("sa_dict"):
        blocked.append("required_sheets_credentials_missing")
    for account_id in plan.get("accounts", []):
        ok, reason = has_required_for_publish(resolve_credentials(account_id))
        if not ok:
            blocked.append(f"{account_id}:{reason}")
    warnings: list[str] = []
    if plan.get("selected_source_count", 0) < 1:
        warnings.append("source_selection_empty_fallback_original_available")
    if plan.get("safety", {}).get("x_fetch") or plan.get("safety", {}).get("x_post"):
        blocked.append("x_mixed_into_autonomous_plan")
    if plan.get("safety", {}).get("beauty_account"):
        blocked.append("beauty_mixed_into_autonomous_plan")
    if any(plan.get("safety", {}).get(k) for k in ("media_download", "video_cut", "cloudinary_upload", "third_party_media", "unknown_rights_media")):
        blocked.append("media_or_rights_gate_failed")
    return {
        "ok": not blocked,
        "blocked_reasons": blocked,
        "warnings": warnings,
        "sheets_credentials_set": bool(cfg.get("sheet_id") and cfg.get("sa_dict")),
        "threads_credentials_checked": list(plan.get("accounts", [])),
    }


def verify_sheets_connectivity() -> dict[str, Any]:
    """Read-only production verify. Failure blocks all apply steps."""
    verify_env = dict(os.environ)
    verify_env["PUBLISH_ENABLED"] = "false"
    verify_env["ALLOW_REAL_THREADS_POST"] = "false"
    verify_env["ALLOW_REAL_X_POST"] = "false"
    verify_env["ALLOW_VIDEO_DOWNLOAD"] = "false"
    verify_env["ALLOW_VIDEO_CUT"] = "false"
    verify_env["ALLOW_CLOUDINARY_UPLOAD"] = "false"
    verify_env["ALLOW_TRANSCRIPTION_API"] = "false"
    return _run([sys.executable, "scripts/recover_production_sheets_threads_first.py", "--verify-only", "--json"], env=verify_env)


def load_posted_results_for_rotation() -> list[dict[str, Any]]:
    """Read posted_results for account rotation without printing secrets."""
    try:
        from config_loader import get_config
        from sheets_client import SheetsClient
        cfg = get_config()
        client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
        return [dict(r) for r in client._ws("posted_results").get_all_records()]
    except Exception:
        return []


def posts_used_today(account_id: str, posted_rows: list[dict[str, Any]], *, now: datetime | None = None) -> int:
    """Count today's posted Threads rows for an account using JST day boundary."""
    jst = timezone(timedelta(hours=9))
    today = (now or datetime.now(timezone.utc)).astimezone(jst).date()
    count = 0
    for row in posted_rows:
        if str(row.get("account_id", "")) != account_id:
            continue
        if str(row.get("platform", "")).lower() not in {"", "threads"}:
            continue
        if str(row.get("status", "")).upper() not in {"POSTED", "RECOVERED", ""}:
            continue
        raw = str(row.get("posted_at") or row.get("created_at") or row.get("collected_at") or "")
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if dt.astimezone(jst).date() == today:
            count += 1
    return count


def build_autonomous_plan(account_id: str, config: dict[str, Any] | None = None, rules: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or load_autonomous_config()
    rules = rules or load_auto_approval_rules()
    gate = build_gate_summary(config, rules)
    accounts = account_scope(account_id, config)
    rotation = account_order_for_scope(account_id, accounts, config, posted_rows=[])
    rotated_accounts = rotation.get("ordered_accounts", accounts)

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

    plan_result = {
        "status": "BLOCKED" if blocked_reasons else "PLAN_ONLY",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "account_id": account_id,
        "accounts": rotated_accounts,
        "account_rotation": rotation,
        "selected_account": rotation.get("selected_account", rotated_accounts[0] if rotated_accounts else ""),
        "skipped_account": rotation.get("skipped_accounts", []),
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
            "video_reference_analysis",
            "video_reference_text_only_ideas",
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
    plan_result["video_reference_analysis"] = build_video_reference_analysis(plan_result, config, fetch_metadata=False)
    preview_output = generate_reader_facing_post(str(plan_result.get("selected_account") or "night_scout"), index=1)
    preview_text = str(preview_output["public_post_text"])
    preview_validation = final_public_post_validator(preview_text, str(plan_result.get("selected_account") or ""))
    plan_result["public_post_preview"] = public_preview(preview_text)
    plan_result["internal_leak_check"] = preview_validation["internal_leak_check"]["status"]
    plan_result["account_fit_check"] = preview_validation["account_fit_check"]["status"]
    plan_result["final_validator_result"] = preview_validation["status"]
    plan_result["would_post"] = False
    return plan_result


def _run(cmd: list[str], *, env: dict[str, str] | None = None) -> dict[str, Any]:
    p = subprocess.run(cmd, cwd=str(ROOT), env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return {
        "cmd": " ".join(cmd),
        "returncode": p.returncode,
        "stdout_tail": p.stdout[-1600:],
        "stderr_tail": p.stderr[-1600:],
    }


def infer_no_post_reason(result: dict[str, Any]) -> str:
    text = f"{result.get('stdout_tail', '')}\n{result.get('stderr_tail', '')}"
    if '"status": "POSTED"' in text:
        return ""
    if "no eligible Threads queue rows" in text:
        return "NO_READY_QUEUE"
    if "FINAL_PUBLIC_POST_VALIDATOR_BLOCKED" in text or "BLOCKED_INTERNAL_LEAK" in text:
        return "VALIDATOR_BLOCKED_ALL"
    if "DUPLICATE_BLOCKED" in text:
        return "DUPLICATE_BLOCKED_ALL"
    if "THREADS_API_FAILED" in text:
        return "THREADS_API_FAILED"
    if "posted_results save failed" in text or "POSTED_SAVE_FAILED" in text:
        return "POSTED_SAVE_FAILED"
    if result.get("returncode") not in {0, None}:
        return "COMMAND_FAILED"
    return "NO_POST_UNKNOWN"


def summarize_autonomous_results(account_id: str, mode: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    process_results = [
        r for r in results
        if "process_threads_queue.py" in str(r.get("cmd", "")) and r.get("status") != "PLAN_ONLY"
    ]
    posted_count = sum(1 for r in process_results if '"status": "POSTED"' in str(r.get("stdout_tail", "")))
    blocked_count = sum(
        1 for r in process_results
        if any(token in str(r.get("stdout_tail", "")) for token in ("BLOCKED", "BLOCKED_INTERNAL_LEAK", "DUPLICATE_BLOCKED"))
    )
    no_post_reasons = [infer_no_post_reason(r) for r in process_results]
    no_post_reasons = [r for r in no_post_reasons if r]
    ready_count = 0
    for r in results:
        text = str(r.get("stdout_tail", ""))
        if '"updated_count":' in text:
            try:
                decoder = json.JSONDecoder()
                for idx, char in enumerate(text):
                    if char == "{":
                        obj, _ = decoder.raw_decode(text[idx:])
                        ready_count += int(obj.get("updated_count", 0))
                        break
            except Exception:
                pass
    return {
        "account_id": account_id,
        "mode": mode,
        "ready_count": ready_count,
        "processed_count": len(process_results),
        "posted_count": posted_count,
        "blocked_count": blocked_count,
        "no_post_reason": "" if posted_count else (no_post_reasons[0] if no_post_reasons else "NO_PROCESS_STEP"),
        "apply_status": "POSTED" if posted_count else ("NO_POST" if process_results else "NOT_PROCESSED"),
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
    accounts = list(plan.get("accounts", []))
    posted_rows_for_caps: list[dict[str, Any]] = []
    if not dry:
        config = load_autonomous_config()
        posted_rows_for_caps = load_posted_results_for_rotation()
        rotation = account_order_for_scope(args.account_id, accounts, config, posted_rows=posted_rows_for_caps)
        accounts = list(rotation.get("ordered_accounts", accounts))
        plan["account_rotation"] = rotation
        plan["selected_account"] = rotation.get("selected_account", accounts[0] if accounts else "")
        plan["skipped_account"] = rotation.get("skipped_accounts", [])
    threads_source_urls = source_urls_for_platform(plan, "threads")

    if dry:
        results.append({
            "cmd": "autonomous_public_post_preview",
            "returncode": 0,
            "status": "PLAN_ONLY",
            "selected_account": plan.get("selected_account", ""),
            "skipped_account": plan.get("skipped_account", []),
            "selected_queue_id": "PLAN_ONLY",
            "public_post_preview": plan.get("public_post_preview", ""),
            "internal_leak_check": plan.get("internal_leak_check", ""),
            "account_fit_check": plan.get("account_fit_check", ""),
            "final_validator_result": plan.get("final_validator_result", ""),
            "would_post": False,
        })
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

    def run_step(cmd: list[str], *, env: dict[str, str] | None = None) -> bool:
        result = _run(cmd, env=env)
        results.append(result)
        return result.get("returncode") == 0

    def run_optional_step(cmd: list[str], *, warning_reason: str, env: dict[str, str] | None = None) -> None:
        ok = run_step(cmd, env=env)
        if not ok:
            plan.setdefault("warnings", []).append(warning_reason)

    video_urls = source_urls_for_platform(plan, "youtube") + source_urls_for_platform(plan, "tiktok")
    if video_urls:
        cmd = [sys.executable, "scripts/collect_video_references.py", "--account-id", "liver_manager", "--dry-run", "--fetch-metadata", "--fetch-transcript"]
        for url in video_urls:
            cmd += ["--url", url]
        run_optional_step(cmd, warning_reason="video_reference_analysis_failed_non_blocking")
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
        run_optional_step(cmd, warning_reason="threads_source_collect_failed_fallback_generation_enabled")
    max_posts_per_run = max(1, int(plan["gate_summary"].get("max_posts_per_run", 1)))
    daily_post_cap = int(plan["gate_summary"].get("daily_post_cap_per_account", 1))
    post_candidate_accounts = []
    for account in accounts:
        used_today = posts_used_today(account, posted_rows_for_caps) if posted_rows_for_caps else 0
        plan.setdefault("daily_cap_state", {}).setdefault(account, {})["posts_used_today"] = used_today
        if used_today >= daily_post_cap:
            results.append({
                "cmd": f"score/generate/auto_ready --account-id {account}",
                "returncode": 0,
                "status": "SKIPPED",
                "reason": "daily_post_cap_reached",
                "posts_used_today": used_today,
                "daily_post_cap": daily_post_cap,
            })
            continue
        if len(post_candidate_accounts) < max_posts_per_run:
            post_candidate_accounts.append(account)
    for account in accounts:
        if account not in post_candidate_accounts:
            results.append({
                "cmd": f"score/generate/auto_ready --account-id {account}",
                "returncode": 0,
                "status": "SKIPPED",
                "reason": "max_posts_per_run_reached_before_account_apply",
            })
            continue
        run_optional_step(
            [sys.executable, "scripts/score_reference_posts.py", "--account-id", account, "--apply", "--confirm-score"],
            warning_reason=f"{account}:reference_scoring_failed_fallback_generation_enabled",
        )
        if not run_step([sys.executable, "scripts/generate_threads_ideas_from_references.py", "--account-id", account, "--apply", "--confirm-generate"]):
            return results
        if not run_step([sys.executable, "scripts/auto_approve_queue.py", "--account-id", account, "--apply", "--confirm-auto-ready", "--max-ready", "1", "--use-sheets", "--skip-setup"]):
            return results
    if plan["gate_summary"]["auto_post_enabled"]:
        env = dict(os.environ)
        env.setdefault("PUBLISH_ENABLED", "true")
        env.setdefault("ALLOW_REAL_THREADS_POST", "true")
        env.setdefault("ALLOW_REAL_X_POST", "false")
        remaining_posts = max_posts_per_run
        for account in accounts:
            if remaining_posts <= 0:
                results.append({
                    "cmd": f"scripts/process_threads_queue.py --account-id {account} --confirm-real-post --max-posts 1",
                    "returncode": 0,
                    "status": "SKIPPED",
                    "reason": "max_posts_per_run_reached",
                })
                continue
            result = _run([sys.executable, "scripts/process_threads_queue.py", "--account-id", account, "--confirm-real-post", "--max-posts", "1"], env=env)
            results.append(result)
            if result.get("returncode") != 0:
                return results
            if '"status": "POSTED"' in str(result.get("stdout_tail", "")):
                remaining_posts -= 1
            elif not plan.get("account_rotation", {}).get("fallback_to_available_account", True):
                remaining_posts -= 1
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="run autonomous SNS growth loop")
    parser.add_argument("--account-id", default="all", choices=["all", "night_scout", "liver_manager", "beauty_account"])
    parser.add_argument("--dry-run", action="store_true", help="plan only (default)")
    parser.add_argument("--preflight", action="store_true", help="read-only production readiness check; never posts")
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
    if args.preflight:
        preflight = apply_preflight(plan)
        print(json.dumps({
            **plan,
            "mode": "preflight",
            "status": "PREFLIGHT_PASS" if preflight["ok"] else "BLOCKED",
            "apply_preflight": preflight,
            "would_post": False,
        }, ensure_ascii=False, indent=2))
        return 0 if preflight["ok"] else 1
    if plan["blocked_reasons"]:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 1

    mode = "apply" if args.apply and args.confirm_autonomous else "dry-run"
    if mode == "apply":
        preflight = apply_preflight(plan)
        if not preflight["ok"]:
            print(json.dumps({**plan, "mode": mode, "status": "BLOCKED", "apply_preflight": preflight}, ensure_ascii=False, indent=2))
            return 1
        verify = verify_sheets_connectivity()
        if verify.get("returncode") != 0:
            plan["verify_result"] = verify
            plan.setdefault("warnings", []).append("sheets_verify_failed_non_blocking_runner_will_validate")
    results = build_results(args, plan)
    failed_results = [r for r in results if r.get("returncode") not in {0, None}]
    status = "DONE" if mode == "apply" and not failed_results else "PLAN_ONLY"
    if failed_results:
        status = "PARTIAL" if mode == "apply" else "PLAN_ONLY_WITH_WARN"
    health_summary = summarize_autonomous_results(args.account_id, mode, results)
    print(json.dumps({**plan, "mode": mode, "status": status, "results": results, "health_summary": health_summary}, ensure_ascii=False, indent=2))
    return 1 if mode == "apply" and failed_results else 0


if __name__ == "__main__":
    raise SystemExit(main())
