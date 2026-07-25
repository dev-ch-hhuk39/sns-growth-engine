#!/usr/bin/env python3
import argparse
import json
import os
import sys
import subprocess
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
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return ""

def get_git_origin_main() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "origin/main"], text=True).strip()
    except Exception:
        return ""

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
    for env_var in safety_env_vars:
        val = str(os.environ.get(env_var, "")).strip().lower()
        if val in {"1", "true", "yes"}:
            safety_failed = True

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
        source_posts, source_post_media, media_permissions, provider_runs, backend_routing_history = [], [], [], [], []
        autonomous_health, resource_usage, content_slot_runs = [], [], []

    if read_errors:
        schema_read_error = True

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

    def _is_text_only_ready(r, acc_id):
        if str(r.get("platform", "")).lower() != "threads": return False
        if str(r.get("status", "")).upper() != "READY": return False
        if str(r.get("account_id", "")) != acc_id and str(r.get("target_account_id", "")) != acc_id: return False
        if str(r.get("media_required", "")).strip().lower() in {"1", "true", "yes"}: return False
        if str(r.get("media_asset_id", "")).strip(): return False
        if str(r.get("media_url", "")).strip(): return False
        if str(r.get("media_urls_json", "")).strip(): return False
        return True

    text_pipeline = {}
    target_accs = ["night_scout", "liver_manager"] if args.account_id == "all" else [args.account_id]

    for acc_id in target_accs:
        q_rows = [r for r in queue if str(r.get("account_id", "")) == acc_id or str(r.get("target_account_id", "")) == acc_id]
        ready_text_count = sum(1 for r in queue if _is_text_only_ready(r, acc_id))
        waiting_review_count = sum(1 for r in q_rows if str(r.get("status", "")).upper() == "WAITING_REVIEW")
        processing_count = sum(1 for r in q_rows if str(r.get("status", "")).upper() == "PROCESSING")
        posted_text_count = sum(1 for r in posted_results if str(r.get("account_id", "")) == acc_id and str(r.get("status", "")).upper() == "POSTED" and str(r.get("platform", "")).lower() == "threads" and not str(r.get("media_used", "")).strip().lower() in {"1", "true", "yes"})

        def _latest(records, acc_id, ts_keys):
            acc_recs = [r for r in records if str(r.get("account_id", "")) == acc_id]
            if not acc_recs: return {}
            def get_ts(r):
                for k in ts_keys:
                    if r.get(k): return str(r.get(k))
                return ""
            return max(acc_recs, key=get_ts)

        ah_allowed = {"run_id", "workflow_name", "mode", "ready_count", "checked_count", "approved_count", "rejected_count", "processed_count", "posted_count", "blocked_count", "no_post_reason", "apply_status", "last_error_redacted", "created_at"}
        ah = _latest(autonomous_health, acc_id, ["created_at", "finished_at"])
        latest_autonomous_health = {k: ah[k] for k in ah if k in ah_allowed}

        ru_allowed = {"checked_at", "status", "media_allowed", "preparation_allowed", "media_post_allowed", "preparation_stop_reason", "text_only_reason", "notes"}
        ru = _latest(resource_usage, acc_id, ["checked_at"])
        latest_resource_usage = {k: ru[k] for k in ru if k in ru_allowed}

        sr_allowed = {"slot_run_id", "schedule_date_jst", "slot_id", "status", "expected_post_type", "actual_post_type", "fallback_level", "no_post_reason", "claim_status", "lease_expires_at", "updated_at"}
        sr = _latest(content_slot_runs, acc_id, ["updated_at", "actual_started_at"])
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

    def _norm(u):
        if not u: return ""
        u = str(u).strip()
        u = re.sub(r"^http://", "https://", u)
        if not u.startswith("http"): u = "https://" + u
        u = u.split("?")[0].split("#")[0]
        u = re.sub(r"/+$", "", u)
        u = re.sub(r"^https://(www\.)?", "https://", u)
        return u.lower()

    dest_handles = {}
    for r in accounts:
        handle = str(r.get("threads_handle", "")).strip()
        if handle:
            dest_handles[str(r.get("account_id", ""))] = _norm("https://threads.net/@" + handle.lstrip("@"))

    all_sources = source_accounts + reference_sources
    liver_threads_source_classification = "MISSING"

    source_inventory = {}

    def _parse_targets(t_ids):
        if not t_ids: return []
        if isinstance(t_ids, list): return t_ids
        t = str(t_ids).strip()
        if t.startswith("["):
            try: return json.loads(t)
            except Exception: pass
        if "|" in t: return [x.strip() for x in t.split("|") if x.strip()]
        if "," in t: return [x.strip() for x in t.split(",") if x.strip()]
        return [t]

    for acc_id in target_accs:
        threads_source_accounts = []
        approved_video_sources = []
        excluded_destination_accounts = []

        for s in all_sources:
            t_ids = _parse_targets(s.get("target_account_ids")) + _parse_targets(s.get("target_account_id"))
            if acc_id not in t_ids: continue

            s_url = str(s.get("source_url", "")).strip()
            dest_url = dest_handles.get(acc_id, "")
            candidate = {k: s[k] for k in ["source_id", "source_platform", "source_url", "target_account_id", "target_account_ids", "active", "blocked", "candidate_status", "review_status", "fetch_enabled", "rights_policy", "use_policy", "can_reuse_media", "manual_only"] if k in s}

            if s_url and dest_url and _norm(s_url) == dest_url:
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
                if active and not blocked and s_url and rev:
                    approved_video_sources.append(candidate)

        sp_count = sum(1 for r in source_posts if str(r.get("target_account_id", "")) == acc_id)

        sp_by_id = {str(r.get("source_post_id", "")): r for r in source_posts if str(r.get("source_post_id", ""))}
        spm_count = sum(1 for r in source_post_media if str(sp_by_id.get(str(r.get("source_post_id", "")), {}).get("target_account_id", "")) == acc_id)

        source_inventory[acc_id] = {
            "threads_source_accounts": threads_source_accounts,
            "approved_video_sources": approved_video_sources,
            "excluded_destination_accounts": excluded_destination_accounts,
            "source_post_count": sp_count,
            "source_post_media_count": spm_count,
            "parent_integrity_failures": []
        }

    # Parent Integrity
    parent_integrity_failures = []
    media_tuples = set()

    for r in source_post_media:
        sp_id = str(r.get("source_post_id", ""))
        m_idx = str(r.get("media_index", ""))

        if not sp_id:
            parent_integrity_failures.append({"id": "MISSING_ID", "reason": "EMPTY_SOURCE_POST_ID", "account_id": ""})
            continue

        acc_id = str(sp_by_id.get(sp_id, {}).get("target_account_id", ""))

        if sp_id not in sp_by_id:
            parent_integrity_failures.append({"id": sp_id, "reason": "PARENT_NOT_FOUND", "account_id": acc_id})
        else:
            p = sp_by_id[sp_id]
            p_url = _norm(str(p.get("canonical_post_url", "")))
            c_url = _norm(str(r.get("canonical_post_url", "")))
            if p_url and c_url and p_url != c_url:
                parent_integrity_failures.append({"id": sp_id, "reason": "CANONICAL_POST_URL_MISMATCH", "account_id": acc_id})

        if (sp_id, m_idx) in media_tuples:
            parent_integrity_failures.append({"id": sp_id, "reason": "DUPLICATE_MEDIA_INDEX", "account_id": acc_id})
        media_tuples.add((sp_id, m_idx))

    for p_id, p in sp_by_id.items():
        try:
            acc_id = str(p.get("target_account_id", ""))
            mc = int(str(p.get("media_count", "")))
            actual = sum(1 for r in source_post_media if str(r.get("source_post_id", "")) == p_id)
            if mc != actual:
                parent_integrity_failures.append({"id": p_id, "reason": "MEDIA_COUNT_MISMATCH", "account_id": acc_id})
        except ValueError:
            pass

    # Deduplicate parent integrity failures
    deduped_failures = []
    seen_failures = set()
    for f in parent_integrity_failures:
        key = (f["id"], f["reason"], f["account_id"])
        if key not in seen_failures:
            seen_failures.add(key)
            deduped_failures.append(f)

    for f in deduped_failures:
        acc_id = f["account_id"]
        if acc_id in source_inventory:
            source_inventory[acc_id]["parent_integrity_failures"].append(f)

    # Permissions
    perm_allowed = {"permission_id", "source_id", "account_id", "usage_mode", "rights_status", "permission_status", "allow_download", "allow_cloudinary_storage", "allow_original_repost", "allow_transcription", "allow_analysis", "allow_cut", "allow_clip_repost", "allow_new_caption", "allow_edit", "evidence_type", "evidence_reference", "approved_by", "approved_at", "expires_at", "revoked", "revoked_at", "updated_at"}

    perm_groups = {}
    for i, r in enumerate(media_permissions):
        s_id = str(r.get("source_id", ""))
        if not s_id: continue
        if s_id not in perm_groups: perm_groups[s_id] = []
        perm_groups[s_id].append((i, r))

    permissions = {}
    for s_id, group in perm_groups.items():
        # sort by updated_at, approved_at, row index
        def _sort_key(item):
            idx, r = item
            upd = str(r.get("updated_at", "")) or "0"
            app = str(r.get("approved_at", "")) or "0"
            return (upd, app, idx)

        latest_idx, latest_r = max(group, key=_sort_key)

        valid = True
        invalid_reasons = []

        if str(latest_r.get("revoked", "")).lower() in {"1", "true", "yes"}:
            valid = False
            invalid_reasons.append("revoked")

        p_stat = str(latest_r.get("permission_status", "")).lower()
        if p_stat not in {"approved", "granted"}:
            valid = False
            invalid_reasons.append("permission_status not approved")

        r_stat = str(latest_r.get("rights_status", "")).lower()
        if r_stat not in {"allowed", "approved", "owned", "licensed", "approved_creator_clip", "approved_media", "own_media"}:
            valid = False
            invalid_reasons.append("rights_status not allowed")

        exp = str(latest_r.get("expires_at", "")).strip()
        if exp:
            try:
                if datetime.fromisoformat(exp.replace("Z", "+00:00")) < datetime.now(timezone.utc):
                    valid = False
                    invalid_reasons.append("expired")
            except Exception:
                valid = False
                invalid_reasons.append("malformed expires_at")

        if not str(latest_r.get("evidence_type", "")).strip():
            valid = False
            invalid_reasons.append("missing evidence_type")
        if not str(latest_r.get("evidence_reference", "")).strip():
            valid = False
            invalid_reasons.append("missing evidence_reference")

        permissions[s_id] = {
            "latest_record": {k: v for k, v in latest_r.items() if k in perm_allowed},
            "valid": valid,
            "invalid_reasons": invalid_reasons
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
    now_utc = datetime.now(timezone.utc)
    for r in content_slot_runs:
        if str(r.get("status", "")).upper() in {"RUNNING", "CLAIMED", "PROCESSING"}:
            if not str(r.get("post_url", "")) and not str(r.get("actual_posted_at", "")):
                exp = str(r.get("lease_expires_at", ""))
                if exp:
                    try:
                        if datetime.fromisoformat(exp.replace("Z", "+00:00")) < now_utc:
                            stale_slots.append(str(r.get("slot_run_id", "")))
                    except Exception:
                        pass

    unauth_media = []
    for r in queue:
        if str(r.get("status", "")).upper() == "READY" and not _is_text_only_ready(r, ""):
            q_id = str(r.get("queue_id", ""))
            reasons = []
            aid = str(r.get("media_asset_id", ""))

            if not aid: reasons.append("missing_media_asset_id")
            if aid not in [str(m.get("media_asset_id", "")) for m in media_assets]: reasons.append("asset_not_in_media_assets")
            if str(r.get("validator_status", "")).upper() != "PASS": reasons.append("validator_not_pass")
            if str(r.get("alignment_status", "")).upper() != "PASS": reasons.append("alignment_not_pass")

            claims = str(r.get("unsupported_claim_count", ""))
            try:
                if float(claims) != 0: reasons.append("claims_not_zero")
            except ValueError:
                reasons.append("claims_not_zero")

            pid = str(r.get("source_post_id", "")) or str(r.get("source_video_id", ""))
            if not pid: reasons.append("missing_source_post_id")

            s_id = str(sp_by_id.get(pid, {}).get("source_id", ""))
            if not s_id: reasons.append("cannot_resolve_source_id")

            perm = permissions.get(s_id, {})
            if not perm.get("valid"): reasons.append("invalid_permission")

            is_clip = False
            for k in ["clip_candidate_id", "source_video_id", "video_clip_id"]:
                if str(r.get(k, "")): is_clip = True
            if str(r.get("media_origin", "")) == "generated_clip" or "clip" in str(r.get("generation_mode", "")):
                is_clip = True

            if is_clip:
                if str(perm.get("latest_record", {}).get("allow_clip_repost", "")).lower() not in {"1", "true", "yes"}:
                    reasons.append("clip_repost_not_allowed")
            else:
                if str(perm.get("latest_record", {}).get("allow_original_repost", "")).lower() not in {"1", "true", "yes"}:
                    reasons.append("original_repost_not_allowed")

            if str(perm.get("latest_record", {}).get("allow_cloudinary_storage", "")).lower() not in {"1", "true", "yes"}:
                reasons.append("cloudinary_storage_not_allowed")

            if reasons:
                unauth_media.append({"queue_id": q_id, "reasons": reasons})

    ps_failed = sum(1 for r in queue if str(r.get("status", "")).upper() == "POSTED_SAVE_FAILED")

    integrity = {
        "duplicate_queue_ids": dup_q,
        "duplicate_slot_idempotency_keys": dup_i,
        "stale_inflight_slots": stale_slots,
        "posted_save_failed_count": ps_failed,
        "unauthorized_ready_media": unauth_media,
        "parent_integrity_failures": parent_integrity_failures
    }

    # Blockers & Overall Status
    blockers = {
        "liver_threads_source_url": "PASS" if liver_threads_source_classification == "FOUND_APPROVED" else "BLOCKED" if liver_threads_source_classification in {"MISSING", "FOUND_UNAPPROVED", "AMBIGUOUS"} else "FAIL",
        "night_threads_credentials": "PASS" if night_creds == "SET" else "BLOCKED",
        "liver_threads_credentials": "PASS" if liver_creds == "SET" else "BLOCKED"
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
    if parent_integrity_failures:
        status_reasons.append("PARENT_INTEGRITY_FAILURES")
    if missing_tabs:
        status_reasons.append("MISSING_TABS")
    if read_errors:
        status_reasons.append("READ_ERRORS")
    if safety_failed:
        status_reasons.append("SAFETY_FLAG_TRUE")
    if schema_read_error:
        status_reasons.append("SCHEMA_READ_ERROR")

    if status_reasons:
        overall = "FAIL"
    else:
        for k, v in blockers.items():
            if v == "BLOCKED":
                overall = "BLOCKED"
                status_reasons.append(k.upper() + "_BLOCKED")

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
