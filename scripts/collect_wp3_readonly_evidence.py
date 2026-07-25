#!/usr/bin/env python3
import argparse
import json
import os
import sys
import subprocess
from urllib.parse import urlsplit, urlunsplit
import re
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, os.path.join(ROOT, "src"))

from config_loader import get_config
from sheets_client import SheetsClient
from recover_production_sheets_threads_first import (
    _refresh_ws_cache,
    credential_status,
    verify_state,
)

try:
    from gspread.exceptions import WorksheetNotFound
except ImportError:
    class WorksheetNotFound(Exception): pass

JST = timezone(timedelta(hours=9))

def now_iso() -> str:
    return datetime.now(JST).replace(microsecond=0).isoformat()

def get_git_head() -> str:
    try: return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception: return ""

def get_git_origin_main() -> str:
    try: return subprocess.check_output(["git", "rev-parse", "origin/main"], text=True).strip()
    except Exception: return ""

def get_records(client, logical_name: str, missing_tabs: list, read_errors: list) -> list:
    try:
        ws = client._ws(logical_name)
        return [dict(r) for r in ws.get_all_records()]
    except Exception as e:
        if type(e).__name__ == "WorksheetNotFound" or "WorksheetNotFound" in str(e):
            missing_tabs.append(logical_name)
        else:
            read_errors.append({"tab": logical_name, "error_type": type(e).__name__})
        return []

def parse_target_account_ids(value) -> list[str]:
    if not value: return []
    if isinstance(value, list): return value
    t = str(value).strip()
    if t.startswith("["):
        try: return json.loads(t)
        except Exception: pass
    if "|" in t: return [x.strip() for x in t.split("|") if x.strip()]
    if "," in t: return [x.strip() for x in t.split(",") if x.strip()]
    return [t]


def canonicalize_source_url(value: str) -> str:
    if not value:
        return ""

    raw = str(value).strip()

    if "://" not in raw:
        raw = "https://" + raw.lstrip("/")

    parsed = urlsplit(raw)

    scheme = "https"
    host = parsed.netloc.lower()

    if host.startswith("www."):
        host = host[4:]

    if host in {"threads.com", "threads.net"}:
        host = "threads.net"

    path = parsed.path.rstrip("/")

    if host == "threads.net":
        path = path.lower()

    return urlunsplit((scheme, host, path, "", ""))

def canonicalize_threads_url(value: str) -> str:
    if not value: return ""
    v = str(value).strip()
    if not v.startswith("http") and not v.startswith("@"):
        v = "@" + v
    if v.startswith("@"):
        v = "https://threads.net/" + v
    v = re.sub(r"^http://", "https://", v)
    v = re.sub(r"^https://(www\.)?threads\.(com|net)/", "https://threads.net/", v)
    v = v.split("?")[0].split("#")[0]
    v = re.sub(r"/+$", "", v)
    return v.lower()

def is_text_only_ready(row: dict, account_id: str) -> bool:
    if str(row.get("platform", "")).lower() != "threads": return False
    if str(row.get("status", "")).upper() != "READY": return False
    if account_id and str(row.get("account_id", "")) != account_id and str(row.get("target_account_id", "")) != account_id: return False
    if is_media_ready(row): return False
    return True

def is_media_ready(row: dict) -> bool:
    if str(row.get("media_required", "")).strip().lower() in {"1", "true", "yes"}: return True
    if str(row.get("media_asset_id", "")).strip(): return True
    if str(row.get("media_url", "")).strip(): return True
    if str(row.get("media_urls_json", "")).strip(): return True
    if str(row.get("source_post_id", "")).strip(): return True
    if str(row.get("source_video_id", "")).strip(): return True
    if str(row.get("clip_candidate_id", "")).strip(): return True
    if str(row.get("video_clip_id", "")).strip(): return True
    if str(row.get("media_origin", "")).strip(): return True
    ms = str(row.get("media_strategy", "")).strip().lower()
    if ms and ms not in {"none", "text_only"}: return True
    return False

def select_latest_permission(rows: list[dict]) -> dict | None:
    if not rows: return None
    def _sort_key(r):
        idx = rows.index(r)
        upd = str(r.get("updated_at", "")) or "0"
        app = str(r.get("approved_at", "")) or "0"
        return (upd, app, idx)
    return max(rows, key=_sort_key)

def evaluate_permission(row: dict | None, now: datetime) -> dict:
    if not row:
        return {"valid": False, "invalid_reasons": ["MISSING_PERMISSION"]}

    valid = True
    invalid_reasons = []

    if str(row.get("revoked", "")).lower() in {"1", "true", "yes"}:
        valid = False
        invalid_reasons.append("REVOKED")

    p_stat = str(row.get("permission_status", "")).lower()
    if p_stat not in {"approved", "granted"}:
        valid = False
        if "REVOKED" not in invalid_reasons:
            invalid_reasons.append("PERMISSION_STATUS_NOT_APPROVED")

    r_stat = str(row.get("rights_status", "")).lower()
    if r_stat not in {"allowed", "approved", "owned", "licensed", "approved_creator_clip", "approved_media", "own_media"}:
        valid = False
        invalid_reasons.append("RIGHTS_STATUS_NOT_ALLOWED")

    exp = str(row.get("expires_at", "")).strip()
    if exp:
        try:
            if not exp.endswith("Z") and "+" not in exp:
                exp = exp + "Z"
            exp_dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
            if exp_dt <= now:
                valid = False
                invalid_reasons.append("EXPIRED")
        except Exception:
            valid = False
            invalid_reasons.append("MALFORMED_EXPIRES_AT")

    if not str(row.get("evidence_type", "")).strip():
        valid = False
        invalid_reasons.append("MISSING_EVIDENCE_TYPE")
    if not str(row.get("evidence_reference", "")).strip():
        valid = False
        invalid_reasons.append("MISSING_EVIDENCE_REFERENCE")

    perm_allowed = {"permission_id", "source_id", "account_id", "usage_mode", "rights_status", "permission_status", "allow_download", "allow_cloudinary_storage", "allow_original_repost", "allow_transcription", "allow_analysis", "allow_cut", "allow_clip_repost", "allow_new_caption", "allow_edit", "evidence_type", "evidence_reference", "approved_by", "approved_at", "expires_at", "revoked", "revoked_at", "updated_at"}
    return {
        "latest_record": {k: v for k, v in row.items() if k in perm_allowed},
        "valid": valid,
        "invalid_reasons": invalid_reasons
    }

def build_source_indexes(source_posts: list[dict], source_videos: list[dict]) -> dict:
    return {
        "source_post_by_id": {str(r.get("source_post_id", "")): r for r in source_posts if str(r.get("source_post_id", ""))},
        "source_video_by_id": {str(r.get("source_video_id", "")): r for r in source_videos if str(r.get("source_video_id", ""))}
    }

def resolve_queue_source_id(row: dict, indexes: dict, media_asset: dict | None) -> str:
    # 1. queueの明示的なsource_id
    if str(row.get("source_id", "")).strip():
        return str(row.get("source_id", "")).strip()
    # 2. source_post_idからsource_posts.source_id
    spid = str(row.get("source_post_id", "")).strip()
    if spid and spid in indexes["source_post_by_id"]:
        if str(indexes["source_post_by_id"][spid].get("source_id", "")).strip():
            return str(indexes["source_post_by_id"][spid].get("source_id", "")).strip()
    # 3. source_video_idからsource_videos.source_id
    svid = str(row.get("source_video_id", "")).strip()
    if svid and svid in indexes["source_video_by_id"]:
        if str(indexes["source_video_by_id"][svid].get("source_id", "")).strip():
            return str(indexes["source_video_by_id"][svid].get("source_id", "")).strip()
    # 4. media assetの明示的なsource_id
    if media_asset and str(media_asset.get("source_id", "")).strip():
        return str(media_asset.get("source_id", "")).strip()
    # 5. media assetのreference_post_idからsource post
    if media_asset:
        rpid = str(media_asset.get("reference_post_id", "")).strip()
        if rpid and rpid in indexes["source_post_by_id"]:
            if str(indexes["source_post_by_id"][rpid].get("source_id", "")).strip():
                return str(indexes["source_post_by_id"][rpid].get("source_id", "")).strip()
    # 6. media assetのsource_video_idからsource video
    if media_asset:
        rsvid = str(media_asset.get("source_video_id", "")).strip()
        if rsvid and rsvid in indexes["source_video_by_id"]:
            if str(indexes["source_video_by_id"][rsvid].get("source_id", "")).strip():
                return str(indexes["source_video_by_id"][rsvid].get("source_id", "")).strip()
    return ""

def evaluate_ready_media_row(row: dict, media_assets: dict, permissions: dict, indexes: dict) -> list[str]:
    reasons = []
    aid = str(row.get("media_asset_id", "")).strip()
    asset = None

    if not aid:
        reasons.append("MISSING_MEDIA_ASSET_ID")
    else:
        if aid in media_assets:
            asset = media_assets[aid]
        else:
            reasons.append("ASSET_NOT_FOUND")

    if str(row.get("validator_status", "")).upper() != "PASS": reasons.append("VALIDATOR_NOT_PASS")
    if str(row.get("alignment_status", "")).upper() != "PASS": reasons.append("ALIGNMENT_NOT_PASS")

    claims = str(row.get("unsupported_claim_count", ""))
    try:
        if float(claims) != 0: reasons.append("UNSUPPORTED_CLAIMS")
    except ValueError:
        reasons.append("UNSUPPORTED_CLAIMS")

    s_id = resolve_queue_source_id(row, indexes, asset)
    if not s_id:
        reasons.append("SOURCE_ID_UNRESOLVED")
        reasons.append("PERMISSION_INVALID")
    else:
        perm = permissions.get(s_id, {})
        if not perm or not perm.get("valid"):
            reasons.append("PERMISSION_INVALID")

        is_clip = False
        for k in ["clip_candidate_id", "source_video_id", "video_clip_id"]:
            if str(row.get(k, "")): is_clip = True
        if str(row.get("media_origin", "")) == "generated_clip" or "clip" in str(row.get("generation_mode", "")):
            is_clip = True

        if is_clip:
            if str(perm.get("latest_record", {}).get("allow_clip_repost", "")).lower() not in {"1", "true", "yes"}:
                reasons.append("CLIP_REPOST_NOT_ALLOWED")
        else:
            if str(perm.get("latest_record", {}).get("allow_original_repost", "")).lower() not in {"1", "true", "yes"}:
                reasons.append("ORIGINAL_REPOST_NOT_ALLOWED")

        # Cloudinary判定
        use_cloudinary = False
        if asset:
            if str(asset.get("storage_provider", "")).lower() == "cloudinary": use_cloudinary = True
            if str(asset.get("cloudinary_public_id", "")).strip(): use_cloudinary = True
            surl = str(asset.get("storage_url", "")).lower()
            if "cloudinary.com" in surl: use_cloudinary = True
            murl = str(asset.get("media_url", "")).lower()
            if "cloudinary.com" in murl: use_cloudinary = True

        if use_cloudinary:
            if str(perm.get("latest_record", {}).get("allow_cloudinary_storage", "")).lower() not in {"1", "true", "yes"}:
                reasons.append("CLOUDINARY_STORAGE_NOT_ALLOWED")

    return reasons

def collect_parent_integrity_failures(source_post_media: list[dict], sp_by_id: dict) -> list[dict]:
    failures = []
    media_tuples = set()
    for r in source_post_media:
        sp_id = str(r.get("source_post_id", ""))
        m_idx = str(r.get("media_index", ""))
        if not sp_id:
            failures.append({"id": "MISSING_ID", "reason": "EMPTY_SOURCE_POST_ID", "account_id": ""})
            continue
        acc_id = str(sp_by_id.get(sp_id, {}).get("target_account_id", ""))
        if sp_id not in sp_by_id:
            failures.append({"id": sp_id, "reason": "PARENT_NOT_FOUND", "account_id": acc_id})
        else:
            p = sp_by_id[sp_id]
            p_url = canonicalize_source_url(str(p.get("canonical_post_url", "")))
            c_url = canonicalize_source_url(str(r.get("canonical_post_url", "")))
            if p_url and c_url and p_url != c_url:
                failures.append({"id": sp_id, "reason": "CANONICAL_POST_URL_MISMATCH", "account_id": acc_id})

        if (sp_id, m_idx) in media_tuples:
            failures.append({"id": sp_id, "reason": "DUPLICATE_MEDIA_INDEX", "account_id": acc_id})
        media_tuples.add((sp_id, m_idx))

    for p_id, p in sp_by_id.items():
        try:
            acc_id = str(p.get("target_account_id", ""))
            mc = int(str(p.get("media_count", "")))
            actual = sum(1 for r in source_post_media if str(r.get("source_post_id", "")) == p_id)
            if mc != actual:
                failures.append({"id": p_id, "reason": "MEDIA_COUNT_MISMATCH", "account_id": acc_id})
        except ValueError:
            pass

    deduped = []
    seen = set()
    for f in failures:
        k = (f["id"], f["reason"], f["account_id"])
        if k not in seen:
            seen.add(k)
            deduped.append(f)
    return deduped

def select_latest_record(rows: list[dict], account_id: str, timestamp_keys: list[str]) -> dict:
    acc_recs = [r for r in rows if str(r.get("account_id", "")) == account_id]
    if not acc_recs: return {}
    def get_ts(r):
        for k in timestamp_keys:
            if r.get(k): return str(r.get(k))
        return ""
    return max(acc_recs, key=get_ts)

def run_collector(args):
    if args.account_id not in {"all", "night_scout", "liver_manager"}:
        sys.stderr.write("argparse error: account-id must be all, night_scout, or liver_manager\n")
        sys.exit(2)

    safety_env_vars = [
        "PUBLISH_ENABLED", "ALLOW_REAL_THREADS_POST", "ALLOW_REAL_X_POST",
        "ALLOW_VIDEO_DOWNLOAD", "ALLOW_VIDEO_CUT", "ALLOW_CLOUDINARY_UPLOAD",
        "ALLOW_MEDIA_POSTS", "ALLOW_REAL_THREADS_VIDEO_POST", "ALLOW_TRANSCRIPTION_API"
    ]

    safety = {
        "publish_enabled": False, "allow_real_threads_post": False, "allow_real_x_post": False,
        "allow_video_download": False, "allow_video_cut": False, "allow_cloudinary_upload": False,
        "allow_media_posts": False, "allow_real_threads_video_post": False, "allow_transcription_api": False,
        "sheets_write_enabled": False
    }

    safety_failed = False
    failed_flags = []
    for env_var in safety_env_vars:
        val = str(os.environ.get(env_var, "")).strip().lower()
        if val in {"1", "true", "yes"}:
            safety_failed = True
            failed_flags.append(env_var)
            if env_var.lower() in safety:
                safety[env_var.lower()] = True

    if safety_failed:
        report = {
            "schema_version": 1,
            "generated_at": now_iso(),
            "mode": "READ_ONLY",
            "implementation_head": get_git_head(),
            "origin_main": get_git_origin_main(),
            "safety": safety,
            "sheets_verifier": {"passed": 0, "failed": [], "total": 0, "warnings": {}, "counts": {}},
            "credentials": {},
            "text_pipeline": {},
            "source_inventory": {},
            "permissions": {},
            "permission_requirements": {},
            "provider_routing": {},
            "integrity": {
                "duplicate_queue_ids": [],
                "duplicate_slot_idempotency_keys": [],
                "stale_inflight_slots": [],
                "posted_save_failed_count": 0,
                "unauthorized_ready_media": [],
                "parent_integrity_failures": []
            },
            "blockers": {},
            "overall_status": "FAIL",
            "status_reasons": ["SAFETY_FLAG_TRUE"],
            "read_errors": [],
            "missing_tabs": [],
            "safety_violation_flags": failed_flags
        }
        with open(args.output, "w") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        return 0

    cfg = get_config()
    client = SheetsClient(cfg.get("sheet_id", ""), cfg.get("sa_dict", {}), dry_run=True)

    missing_tabs = []
    read_errors = []
    schema_read_error = False

    try:
        _refresh_ws_cache(client)
        accounts = get_records(client, "accounts", missing_tabs, read_errors)
        queue = get_records(client, "queue", missing_tabs, read_errors)
        posted_results = get_records(client, "posted_results", missing_tabs, read_errors)
        media_assets = get_records(client, "media_assets", missing_tabs, read_errors)
        source_accounts = get_records(client, "source_accounts", missing_tabs, read_errors)
        reference_sources = get_records(client, "reference_sources", missing_tabs, read_errors)
        source_posts = get_records(client, "source_posts", missing_tabs, read_errors)
        source_post_media = get_records(client, "source_post_media", missing_tabs, read_errors)
        source_videos = get_records(client, "source_videos", missing_tabs, read_errors)
        media_permissions = get_records(client, "media_permissions", missing_tabs, read_errors)
        provider_runs = get_records(client, "provider_runs", missing_tabs, read_errors)
        backend_routing_history = get_records(client, "backend_routing_history", missing_tabs, read_errors)
        autonomous_health = get_records(client, "autonomous_health", missing_tabs, read_errors)
        resource_usage = get_records(client, "resource_usage", missing_tabs, read_errors)
        content_slot_runs = get_records(client, "content_slot_runs", missing_tabs, read_errors)
        verifier_data = verify_state(client)
    except Exception as e:
        schema_read_error = True
        read_errors.append({"tab": "ALL", "error_type": type(e).__name__})
        verifier_data = {"passed": 0, "failed": [], "total": 0, "warnings": {}, "counts": {}}
        accounts, queue, posted_results, media_assets, source_accounts, reference_sources = [], [], [], [], [], []
        source_posts, source_post_media, source_videos, media_permissions, provider_runs, backend_routing_history = [], [], [], [], [], []
        autonomous_health, resource_usage, content_slot_runs = [], [], []

    if read_errors: schema_read_error = True

    sheets_verifier = {
        "passed": verifier_data.get("passed", 0),
        "failed": verifier_data.get("failed", []),
        "total": verifier_data.get("passed", 0) + len(verifier_data.get("failed", [])),
        "warnings": verifier_data.get("warnings", {}),
        "counts": verifier_data.get("counts", {})
    }

    creds = credential_status()
    night_creds = creds.get("threads", {}).get("night_scout", {}).get("publish_credentials", "MISSING")
    liver_creds = creds.get("threads", {}).get("liver_manager", {}).get("publish_credentials", "MISSING")
    cloudinary = creds.get("cloudinary", {})

    credentials = {
        "night_scout Threads publish credentials": "PRESENT" if night_creds == "SET" else "MISSING",
        "liver_manager Threads publish credentials": "PRESENT" if liver_creds == "SET" else "MISSING",
        "Cloudinary cloud_name": "PRESENT" if cloudinary.get("cloud_name") == "SET" else "MISSING",
        "Cloudinary api_key": "PRESENT" if cloudinary.get("api_key") == "SET" else "MISSING",
        "Cloudinary api_secret": "PRESENT" if cloudinary.get("api_secret") == "SET" else "MISSING"
    }

    media_by_id = {
        str(r.get("media_id") or r.get("media_asset_id") or "").strip(): r
        for r in media_assets
        if str(r.get("media_id") or r.get("media_asset_id") or "").strip()
    }

    indexes = build_source_indexes(source_posts, source_videos)

    now_utc = datetime.now(timezone.utc)

    # Permissions
    perm_groups = {}
    for r in media_permissions:
        s_id = str(r.get("source_id", ""))
        if not s_id: continue
        if s_id not in perm_groups: perm_groups[s_id] = []
        perm_groups[s_id].append(r)

    permissions = {}
    for s_id, group in perm_groups.items():
        latest_r = select_latest_permission(group)
        permissions[s_id] = evaluate_permission(latest_r, now_utc)

    text_pipeline = {}
    target_accs = ["night_scout", "liver_manager"] if args.account_id == "all" else [args.account_id]

    for acc_id in target_accs:
        q_rows = [r for r in queue if str(r.get("account_id", "")) == acc_id or str(r.get("target_account_id", "")) == acc_id]
        ready_text_count = 0
        for r in q_rows:
            a_id = str(r.get("target_account_id") or r.get("account_id") or "").strip()
            if is_text_only_ready(r, a_id):
                ready_text_count += 1

        waiting_review_count = sum(1 for r in q_rows if str(r.get("status", "")).upper() == "WAITING_REVIEW")
        processing_count = sum(1 for r in q_rows if str(r.get("status", "")).upper() == "PROCESSING")
        posted_text_count = sum(1 for r in posted_results if str(r.get("account_id", "")) == acc_id and str(r.get("status", "")).upper() == "POSTED" and str(r.get("platform", "")).lower() == "threads" and not str(r.get("media_used", "")).strip().lower() in {"1", "true", "yes"})

        ah_allowed = {"run_id", "workflow_name", "mode", "ready_count", "checked_count", "approved_count", "rejected_count", "processed_count", "posted_count", "blocked_count", "no_post_reason", "apply_status", "last_error_redacted", "created_at"}
        ah = select_latest_record(autonomous_health, acc_id, ["created_at", "finished_at"])
        latest_autonomous_health = {k: ah[k] for k in ah if k in ah_allowed}

        ru_allowed = {"checked_at", "status", "media_allowed", "preparation_allowed", "media_post_allowed", "preparation_stop_reason", "text_only_reason", "notes"}
        ru = select_latest_record(resource_usage, acc_id, ["checked_at"])
        latest_resource_usage = {k: ru[k] for k in ru if k in ru_allowed}

        sr_allowed = {"slot_run_id", "schedule_date_jst", "slot_id", "status", "expected_post_type", "actual_post_type", "fallback_level", "no_post_reason", "claim_status", "lease_expires_at", "updated_at"}
        sr = select_latest_record(content_slot_runs, acc_id, ["updated_at", "actual_started_at"])
        latest_slot_state = {k: sr[k] for k in sr if k in sr_allowed}

        no_post_reasons = {}
        for r in content_slot_runs:
            if str(r.get("account_id", "")) == acc_id:
                reason = str(r.get("no_post_reason", "")).strip()
                if reason:
                    no_post_reasons[reason] = no_post_reasons.get(reason, 0) + 1

        text_pipeline[acc_id] = {
            "ready_text_count": ready_text_count,
            "waiting_review_count": waiting_review_count,
            "processing_count": processing_count,
            "posted_text_count": posted_text_count,
            "latest_autonomous_health": latest_autonomous_health,
            "latest_resource_usage": latest_resource_usage,
            "latest_slot_state": latest_slot_state,
            "no_post_reasons": no_post_reasons
        }

    dest_handles = {}
    for r in accounts:
        handle = str(r.get("threads_handle", "")).strip()
        if handle:
            dest_handles[str(r.get("account_id", ""))] = canonicalize_threads_url(handle)

    all_sources = source_accounts + reference_sources
    liver_threads_source_classification = "MISSING"

    source_targets_by_source_id: dict[str, set[str]] = {}
    for s in all_sources:
        s_id = str(s.get("source_id", ""))
        if s_id:
            if s_id not in source_targets_by_source_id:
                source_targets_by_source_id[s_id] = set()
            for t in parse_target_account_ids(s.get("target_account_ids")) + parse_target_account_ids(s.get("target_account_id")):
                source_targets_by_source_id[s_id].add(t)

    source_inventory = {}
    all_pi_failures = collect_parent_integrity_failures(source_post_media, indexes["source_post_by_id"])

    for acc_id in target_accs:
        threads_source_accounts = []
        approved_video_sources = []
        video_sources_unapproved = []
        excluded_destination_accounts = []

        for s in all_sources:
            t_ids = parse_target_account_ids(s.get("target_account_ids")) + parse_target_account_ids(s.get("target_account_id"))
            if acc_id not in t_ids: continue

            s_url = str(s.get("source_url", "")).strip()
            dest_url = dest_handles.get(acc_id, "")
            candidate = {k: s[k] for k in ["source_id", "source_platform", "source_url", "target_account_id", "target_account_ids", "active", "blocked", "candidate_status", "review_status", "fetch_enabled", "rights_policy", "use_policy", "can_reuse_media", "manual_only"] if k in s}

            if s_url and dest_url and canonicalize_threads_url(s_url) == dest_url:
                excluded_destination_accounts.append(candidate)
                continue

            plat = str(s.get("platform", "")).lower() or str(s.get("source_platform", "")).lower()
            if plat == "threads":
                threads_source_accounts.append(candidate)
                if acc_id == "liver_manager" and s_url:
                    active = str(s.get("active", "")).strip().lower() in {"1", "true", "yes"}
                    blocked = str(s.get("blocked", "")).strip().lower() in {"1", "true", "yes"}
                    if active and not blocked and (str(s.get("review_status", "")).upper() == "APPROVED" or str(s.get("candidate_status", "")).upper() == "APPROVED"):
                        liver_threads_source_classification = "FOUND_APPROVED"
                    else:
                        if liver_threads_source_classification == "MISSING":
                            if not active or blocked:
                                liver_threads_source_classification = "FOUND_UNAPPROVED"
                            else:
                                liver_threads_source_classification = "AMBIGUOUS"

            if plat in {"youtube", "tiktok"}:
                active = str(s.get("active", "")).strip().lower() in {"1", "true", "yes"}
                blocked = str(s.get("blocked", "")).strip().lower() in {"1", "true", "yes"}
                rev = str(s.get("review_status", "")).upper() == "APPROVED" or str(s.get("candidate_status", "")).upper() == "APPROVED"
                s_id = str(s.get("source_id", ""))
                perm = permissions.get(s_id, {})
                valid_perm = perm.get("valid", False)
                allow_an = str(perm.get("latest_record", {}).get("allow_analysis", "")).strip().lower() in {"1", "true", "yes"}
                allow_tr = str(perm.get("latest_record", {}).get("allow_transcription", "")).strip().lower() in {"1", "true", "yes"}

                reasons = []
                if not active: reasons.append("NOT_ACTIVE")
                if blocked: reasons.append("BLOCKED")
                if not s_url: reasons.append("MISSING_URL")
                if not rev: reasons.append("NOT_APPROVED")
                if not valid_perm: reasons.append("INVALID_PERMISSION")
                if not allow_an: reasons.append("ANALYSIS_NOT_ALLOWED")
                if not allow_tr: reasons.append("TRANSCRIPTION_NOT_ALLOWED")

                if not reasons:
                    approved_video_sources.append(candidate)
                else:
                    video_sources_unapproved.append({
                        "source_id": s_id,
                        "reason_codes": reasons
                    })

        sp_count = sum(1 for r in source_posts if str(r.get("target_account_id", "")) == acc_id)
        spm_count = sum(1 for r in source_post_media if str(indexes["source_post_by_id"].get(str(r.get("source_post_id", "")), {}).get("target_account_id", "")) == acc_id)
        sv_count = sum(1 for r in source_videos if str(r.get("account_id", "")) == acc_id or (str(r.get("source_id", "")) and acc_id in source_targets_by_source_id.get(str(r.get("source_id", "")), set())))

        source_inventory[acc_id] = {
            "threads_source_accounts": threads_source_accounts,
            "approved_video_sources": approved_video_sources,
            "video_sources_unapproved": video_sources_unapproved,
            "excluded_destination_accounts": excluded_destination_accounts,
            "source_post_count": sp_count,
            "source_post_media_count": spm_count,
            "source_video_count": sv_count,
            "parent_integrity_failures": [f for f in all_pi_failures if f["account_id"] == acc_id]
        }

    # Provider Routing
    max_rows = args.max_provider_rows
    prov_allowed = {"source_id", "source_post_id", "source_video_id", "platform", "capability", "provider_name", "provider_version", "backend_name", "primary_backend", "selected_backend", "fallback_used", "status", "reason", "retryable", "attempt_count", "duration_ms", "created_at"}

    pr_rows = [{k: r[k] for k in r if k in prov_allowed} for r in sorted(provider_runs, key=lambda x: str(x.get("created_at", "")), reverse=True)[:max_rows]]
    bh_rows = [{k: r[k] for k in r if k in prov_allowed} for r in sorted(backend_routing_history, key=lambda x: str(x.get("created_at", "")), reverse=True)[:max_rows]]

    provider_routing = {
        "provider_runs": pr_rows,
        "backend_routing_history": bh_rows
    }

    # Integrity
    q_ids = [str(r.get("queue_id", "")) for r in queue if str(r.get("queue_id", ""))]
    dup_q = list(set(x for x in q_ids if q_ids.count(x) > 1))

    i_keys = [str(r.get("idempotency_key", "")) for r in content_slot_runs if str(r.get("idempotency_key", ""))]
    dup_i = list(set(x for x in i_keys if i_keys.count(x) > 1))

    stale_slots = []
    for r in content_slot_runs:
        if str(r.get("status", "")).upper() in {"RUNNING", "CLAIMED", "PROCESSING"}:
            if not str(r.get("post_url", "")) and not str(r.get("actual_posted_at", "")):
                exp = str(r.get("lease_expires_at", ""))
                if exp:
                    try:
                        if not exp.endswith("Z") and "+" not in exp: exp += "Z"
                        if datetime.fromisoformat(exp.replace("Z", "+00:00")) < now_utc:
                            stale_slots.append(str(r.get("slot_run_id", "")))
                    except Exception:
                        pass

    unauth_media = []
    for r in queue:
        if str(r.get("status", "")).upper() == "READY":
            a_id = str(r.get("target_account_id") or r.get("account_id") or "").strip()
            if is_text_only_ready(r, a_id):
                continue

            if is_media_ready(r):
                reasons = evaluate_ready_media_row(r, media_by_id, permissions, indexes)
                if reasons:
                    unauth_media.append({"queue_id": str(r.get("queue_id", "")), "reasons": reasons})

    ps_failed = sum(1 for r in queue if str(r.get("status", "")).upper() == "POSTED_SAVE_FAILED")

    integrity = {
        "duplicate_queue_ids": dup_q,
        "duplicate_slot_idempotency_keys": dup_i,
        "stale_inflight_slots": stale_slots,
        "posted_save_failed_count": ps_failed,
        "unauthorized_ready_media": unauth_media,
        "parent_integrity_failures": all_pi_failures
    }

    permission_requirements = {
        "night_scout": {"required_source_ids": [], "valid_source_ids": [], "missing_or_invalid_source_ids": [], "status": "BLOCKED"},
        "liver_manager": {"required_source_ids": [], "valid_source_ids": [], "missing_or_invalid_source_ids": [], "status": "BLOCKED"}
    }

    for acc_id in ["night_scout", "liver_manager"]:
        req_ids = set()
        for s in all_sources:
            t_ids = parse_target_account_ids(s.get("target_account_ids")) + parse_target_account_ids(s.get("target_account_id"))
            if acc_id not in t_ids: continue
            active = str(s.get("active", "")).strip().lower() in {"1", "true", "yes"}
            blocked = str(s.get("blocked", "")).strip().lower() in {"1", "true", "yes"}
            s_url = str(s.get("source_url", "")).strip()
            plat = str(s.get("platform", "")).lower() or str(s.get("source_platform", "")).lower()
            can_reuse = str(s.get("can_reuse_media", "")).strip().lower() in {"1", "true", "yes"}
            rev = str(s.get("review_status", "")).upper() == "APPROVED" or str(s.get("candidate_status", "")).upper() == "APPROVED"
            s_id = str(s.get("source_id", ""))
            if s_id and active and not blocked and s_url and (plat in {"youtube", "tiktok"} or can_reuse) and rev:
                req_ids.add(s_id)

        for r in queue:
            if str(r.get("status", "")).upper() == "READY":
                a_id = str(r.get("target_account_id") or r.get("account_id") or "").strip()
                if a_id == acc_id or (not a_id and acc_id in parse_target_account_ids(r.get("target_account_ids", ""))):
                    aid = str(r.get("media_asset_id", "")).strip()
                    asset = media_by_id.get(aid) if aid else None
                    q_s_id = resolve_queue_source_id(r, indexes, asset)
                    if q_s_id:
                        req_ids.add(q_s_id)

        valid_ids = []
        missing_ids = []
        for sid in req_ids:
            if permissions.get(sid, {}).get("valid"):
                valid_ids.append(sid)
            else:
                missing_ids.append(sid)

        status = "PASS" if valid_ids else "BLOCKED"
        if len(req_ids) == 0:
            status = "BLOCKED"

        permission_requirements[acc_id] = {
            "required_source_ids": sorted(list(req_ids)),
            "valid_source_ids": sorted(valid_ids),
            "missing_or_invalid_source_ids": sorted(missing_ids),
            "status": status
        }

    # Blockers & Overall Status
    blockers = {
        "liver_threads_source_url": "PASS" if liver_threads_source_classification == "FOUND_APPROVED" else "BLOCKED" if liver_threads_source_classification in {"MISSING", "FOUND_UNAPPROVED", "AMBIGUOUS"} else "FAIL",
        "night_threads_credentials": "PASS" if night_creds == "SET" else "BLOCKED",
        "liver_threads_credentials": "PASS" if liver_creds == "SET" else "BLOCKED",
        "permission_ledger": "PASS" if (permission_requirements["night_scout"]["status"] == "PASS" and permission_requirements["liver_manager"]["status"] == "PASS") else "BLOCKED",
        "sheets_verifier": "PASS" if sheets_verifier["passed"] == 63 and not sheets_verifier["failed"] else "BLOCKED"
    }

    overall = "PASS"
    status_reasons = []

    if sheets_verifier["passed"] != 63 or sheets_verifier["failed"] or sheets_verifier["total"] != 63:
        status_reasons.append("SHEETS_VERIFIER_FAILED")
    if ps_failed > 0:
        status_reasons.append("POSTED_SAVE_FAILED")
    if dup_q:
        status_reasons.append("DUPLICATE_QUEUE_IDS")
    if dup_i:
        status_reasons.append("DUPLICATE_SLOT_IDEMPOTENCY_KEYS")
    if unauth_media:
        status_reasons.append("UNAUTHORIZED_READY_MEDIA")
    if all_pi_failures:
        status_reasons.append("PARENT_INTEGRITY_FAILURES")
    if missing_tabs:
        status_reasons.append("MISSING_TABS")
    if read_errors:
        status_reasons.append("READ_ERRORS")
    if schema_read_error:
        status_reasons.append("SCHEMA_READ_ERROR")

    if liver_threads_source_classification == "MISSING":
        status_reasons.append("LIVER_THREADS_SOURCE_MISSING")
    elif liver_threads_source_classification == "FOUND_UNAPPROVED":
        status_reasons.append("LIVER_THREADS_SOURCE_UNAPPROVED")
    elif liver_threads_source_classification == "AMBIGUOUS":
        status_reasons.append("LIVER_THREADS_SOURCE_AMBIGUOUS")

    if blockers["night_threads_credentials"] == "BLOCKED":
        status_reasons.append("NIGHT_THREADS_CREDENTIALS_MISSING")
    if blockers["liver_threads_credentials"] == "BLOCKED":
        status_reasons.append("LIVER_THREADS_CREDENTIALS_MISSING")

    if permission_requirements["night_scout"]["status"] == "BLOCKED":
        status_reasons.append("REQUIRED_PERMISSION_MISSING_NIGHT_SCOUT")
    if permission_requirements["liver_manager"]["status"] == "BLOCKED":
        status_reasons.append("REQUIRED_PERMISSION_MISSING_LIVER_MANAGER")

    # unique reasons and determine overall
    unique_reasons = []
    for r in status_reasons:
        if r not in unique_reasons:
            unique_reasons.append(r)

    status_reasons = unique_reasons

    if status_reasons:
        if any(r in ["SHEETS_VERIFIER_FAILED", "POSTED_SAVE_FAILED", "DUPLICATE_QUEUE_IDS", "DUPLICATE_SLOT_IDEMPOTENCY_KEYS", "UNAUTHORIZED_READY_MEDIA", "PARENT_INTEGRITY_FAILURES", "MISSING_TABS", "READ_ERRORS", "SCHEMA_READ_ERROR"] for r in status_reasons):
            overall = "FAIL"
        else:
            overall = "BLOCKED"

    report = {
        "schema_version": 1,
        "generated_at": now_iso(),
        "mode": "READ_ONLY",
        "implementation_head": get_git_head(),
        "origin_main": get_git_origin_main(),
        "safety": safety,
        "sheets_verifier": sheets_verifier,
        "credentials": credentials,
        "text_pipeline": text_pipeline,
        "source_inventory": source_inventory,
        "permissions": permissions,
        "permission_requirements": permission_requirements,
        "provider_routing": provider_routing,
        "integrity": integrity,
        "blockers": blockers,
        "overall_status": overall,
        "status_reasons": status_reasons,
        "liver_threads_source_classification": liver_threads_source_classification,
        "read_errors": read_errors,
        "missing_tabs": missing_tabs
    }

    with open(args.output, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    return 0

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--account-id", default="all")
    parser.add_argument("--max-provider-rows", type=int, default=20)
    args = parser.parse_args()
    try:
        run_collector(args)
    except SystemExit as e:
        sys.exit(e.code)
    except Exception as e:
        sys.exit(1)

if __name__ == "__main__":
    main()
