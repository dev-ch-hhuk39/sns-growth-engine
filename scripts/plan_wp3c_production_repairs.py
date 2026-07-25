#!/usr/bin/env python3
import argparse
import json
import os
import sys
import subprocess
import hashlib
from urllib.parse import urlsplit, urlunsplit
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, os.path.join(ROOT, "src"))

TARGET_SOURCE_POST_IDS = (
    "sp_src_lm_yt_user_001_UCzFzty7aEd4tw3NqCW6pkLQ",
    "sp_src_ns_threads_user_chiishunin_s_DbAmx0dEjy3",
    "sp_src_ns_threads_user_chiishunin_s_Da8Jwc6kiAf",
    "sp_src_ns_threads_required_002_DSSq-YaE6TC",
)

TARGET_SLOT_RUN_IDS = (
    "slot_20260722_liver_manager_lm_1000_original",
    "slot_20260724_liver_manager_lm_2100_pdca",
)

TARGET_PERMISSION_SOURCE_IDS = (
    "src_lm_yt_cand_001",
)

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

def generate_hash(obj: dict) -> str:
    s = json.dumps(obj, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def prevent_writes(obj):
    forbidden = [
        "_ensure_tab", "append_row", "append_rows", "update", "update_cell",
        "batch_update", "resize", "clear", "delete_rows", "setup_all", "seed", "save"
    ]
    def bomb(*args, **kwargs):
        raise Exception("WRITE BOMB TRIGGERED")
    for method in forbidden:
        if hasattr(obj, method):
            setattr(obj, method, bomb)
    return obj

def check_safety_flags():
    flags = [
        "PUBLISH_ENABLED", "ALLOW_REAL_THREADS_POST", "ALLOW_REAL_X_POST",
        "ALLOW_VIDEO_DOWNLOAD", "ALLOW_VIDEO_CUT", "ALLOW_CLOUDINARY_UPLOAD",
        "ALLOW_MEDIA_POSTS", "ALLOW_REAL_THREADS_VIDEO_POST", "ALLOW_TRANSCRIPTION_API"
    ]
    for f in flags:
        val = str(os.environ.get(f, "")).strip().lower()
        if val in {"1", "true", "yes"}:
            return True
    return False

def get_records(client, logical_name: str, missing_tabs: list, read_errors: list) -> list:
    try:
        ws = client._ws(logical_name)
        prevent_writes(ws)
        return [dict(r) for r in ws.get_all_records()]
    except Exception as e:
        if type(e).__name__ == "WorksheetNotFound" or "WorksheetNotFound" in str(e):
            missing_tabs.append(logical_name)
        else:
            read_errors.append({"tab": logical_name, "error_type": type(e).__name__})
        return []

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    for arg in sys.argv:
        if arg in ["--apply", "--confirm", "--write", "--repair", "--update"]:
            sys.stderr.write(f"Prohibited argument: {arg}\n")
            sys.exit(1)
            
    args, unknown = parser.parse_known_args()
    for arg in unknown:
        if arg in ["--apply", "--confirm", "--write", "--repair", "--update"]:
            sys.stderr.write(f"Prohibited argument: {arg}\n")
            sys.exit(1)

    if check_safety_flags():
        with open(args.output, "w") as f:
            json.dump({
                "schema_version": 1,
                "mode": "READ_ONLY_REPAIR_PLAN",
                "overall_status": "FAIL",
                "status_reasons": ["SAFETY_FLAG_TRUE"]
            }, f, indent=2)
        print(f"WP3C_SAFE_REPAIR_PLAN_JSON={json.dumps({'schema_version': 1, 'overall_status': 'FAIL'})}")
        sys.exit(0)

    from config_loader import get_config
    from sheets_client import SheetsClient
    from recover_production_sheets_threads_first import verify_state

    cfg = get_config()
    client = SheetsClient(cfg.get("sheet_id", ""), cfg.get("sa_dict", {}), dry_run=True)
    prevent_writes(client)

    missing_tabs = []
    read_errors = []
    
    try:
        source_posts = get_records(client, "source_posts", missing_tabs, read_errors)
        source_post_media = get_records(client, "source_post_media", missing_tabs, read_errors)
        content_slot_runs = get_records(client, "content_slot_runs", missing_tabs, read_errors)
        queue = get_records(client, "queue", missing_tabs, read_errors)
        posted_results = get_records(client, "posted_results", missing_tabs, read_errors)
        media_permissions = get_records(client, "media_permissions", missing_tabs, read_errors)
        source_accounts = get_records(client, "source_accounts", missing_tabs, read_errors)
        
        verifier_data = verify_state(client)
    except Exception as e:
        with open(args.output, "w") as f:
            json.dump({
                "schema_version": 1,
                "mode": "READ_ONLY_REPAIR_PLAN",
                "overall_status": "FAIL",
                "status_reasons": ["EXCEPTION", str(e)]
            }, f, indent=2)
        print(f"WP3C_SAFE_REPAIR_PLAN_JSON={json.dumps({'schema_version': 1, 'overall_status': 'FAIL'})}")
        sys.exit(0)

    if read_errors:
        with open(args.output, "w") as f:
            json.dump({
                "schema_version": 1,
                "mode": "READ_ONLY_REPAIR_PLAN",
                "overall_status": "FAIL",
                "status_reasons": ["READ_ERROR"]
            }, f, indent=2)
        print(f"WP3C_SAFE_REPAIR_PLAN_JSON={json.dumps({'schema_version': 1, 'overall_status': 'FAIL'})}")
        sys.exit(0)

    sheets_verifier = {
        "passed": verifier_data.get("passed", 0),
        "total": verifier_data.get("passed", 0) + len(verifier_data.get("failed", [])),
        "failed_count": len(verifier_data.get("failed", []))
    }

    if sheets_verifier["failed_count"] > 0:
        pass # fail conditions are combined later

    sp_by_id = {str(r.get("source_post_id", "")): r for r in source_posts}
    spm_by_sp_id = {}
    for r in source_post_media:
        pid = str(r.get("source_post_id", ""))
        if pid not in spm_by_sp_id:
            spm_by_sp_id[pid] = []
        spm_by_sp_id[pid].append(r)

    parent_repairs = []
    status_reasons = []
    if missing_tabs: status_reasons.append("MISSING_TABS")

    for pid in TARGET_SOURCE_POST_IDS:
        parents = [r for r in source_posts if str(r.get("source_post_id", "")) == pid]
        if not parents:
            status_reasons.append("PARENT_NOT_FOUND")
            continue
        if len(parents) > 1:
            status_reasons.append("MULTIPLE_PARENTS")
            continue
            
        p = parents[0]
        children = spm_by_sp_id.get(pid, [])
        
        apply_eligible = True
        blocker_codes = []
        ops = []
        
        p_canon = canonicalize_source_url(str(p.get("canonical_post_url", "")))
        if not p_canon:
            blocker_codes.append("PARENT_CANONICAL_URL_MISSING")
            apply_eligible = False
            
        canonical_mismatch_child_ids = []
        for c in children:
            c_id = str(c.get("source_post_media_id", ""))
            if not c_id:
                blocker_codes.append("CHILD_ID_MISSING")
                apply_eligible = False
                continue
            c_canon = canonicalize_source_url(str(c.get("canonical_post_url", "")))
            if p_canon and c_canon and p_canon != c_canon:
                canonical_mismatch_child_ids.append(c_id)
                ops.append({
                    "operation": "SET_CHILD_CANONICAL_URL_FROM_PARENT",
                    "source_post_media_id": c_id,
                    "precondition": "PARENT_AND_CHILD_CANONICAL_URL_PRESENT"
                })
        
        # Duplicate index
        idx_groups = {}
        for c in children:
            c_id = str(c.get("source_post_media_id", ""))
            try:
                idx = int(str(c.get("media_index", "")))
                if idx < 0:
                    blocker_codes.append("NEGATIVE_MEDIA_INDEX")
                    apply_eligible = False
            except ValueError:
                idx = str(c.get("media_index", ""))
                blocker_codes.append("MALFORMED_MEDIA_INDEX")
                apply_eligible = False
                
            if idx not in idx_groups: idx_groups[idx] = []
            idx_groups[idx].append(c)
            
        duplicate_index_groups = []
        all_child_ids_seen = set()
        child_id_duplicate = False
        
        for idx, items in idx_groups.items():
            for it in items:
                cid = str(it.get("source_post_media_id", ""))
                if cid in all_child_ids_seen: child_id_duplicate = True
                all_child_ids_seen.add(cid)
                
            if len(items) > 1:
                # determine asset relation
                relation = "DISTINCT_ASSET"
                h_vals = set(str(it.get("content_hash", "")) for it in items if str(it.get("content_hash", "")))
                m_vals = set(canonicalize_source_url(str(it.get("original_media_url", ""))) for it in items if str(it.get("original_media_url", "")))
                c_vals = set(str(it.get("cloudinary_public_id", "")) for it in items if str(it.get("cloudinary_public_id", "")))
                a_vals = set(str(it.get("media_asset_id", "")) for it in items if str(it.get("media_asset_id", "")))
                
                # Check for SAME_ASSET
                if (len(h_vals) == 1 and sum(1 for it in items if str(it.get("content_hash", ""))) == len(items)) or \
                   (len(m_vals) == 1 and sum(1 for it in items if str(it.get("original_media_url", ""))) == len(items)) or \
                   (len(c_vals) == 1 and sum(1 for it in items if str(it.get("cloudinary_public_id", ""))) == len(items)) or \
                   (len(a_vals) == 1 and sum(1 for it in items if str(it.get("media_asset_id", ""))) == len(items)):
                    relation = "SAME_ASSET"
                elif len(h_vals) > 1 or len(m_vals) > 1 or len(c_vals) > 1 or len(a_vals) > 1:
                    relation = "DISTINCT_ASSET"
                else:
                    relation = "UNKNOWN"
                    
                duplicate_index_groups.append({
                    "media_index": idx,
                    "child_ids": [str(it.get("source_post_media_id", "")) for it in items],
                    "asset_relation": relation
                })
                
                if relation in {"SAME_ASSET", "UNKNOWN"}:
                    blocker_codes.append("DUPLICATE_MEDIA_REQUIRES_MANUAL_DECISION")
                    apply_eligible = False
                elif relation == "DISTINCT_ASSET":
                    used_indices = set(k for k in idx_groups.keys() if isinstance(k, int))
                    
                    sorted_items = sorted(items, key=lambda x: (str(x.get("created_at", "")), str(x.get("source_post_media_id", ""))))
                    # Keep first as is, reassign rest
                    reassign = sorted_items[1:]
                    
                    for r_item in reassign:
                        nxt = 0
                        while nxt in used_indices:
                            nxt += 1
                        used_indices.add(nxt)
                        ops.append({
                            "operation": "SET_MEDIA_INDEX",
                            "source_post_media_id": str(r_item.get("source_post_media_id", "")),
                            "from": idx,
                            "to": nxt
                        })

        if child_id_duplicate:
            blocker_codes.append("DUPLICATE_CHILD_ID")
            apply_eligible = False

        try:
            declared = int(str(p.get("media_count", "")))
        except ValueError:
            declared = -1
            blocker_codes.append("MALFORMED_PARENT_MEDIA_COUNT")
            apply_eligible = False
            
        actual = len(children)
        if apply_eligible and declared != actual:
            ops.append({
                "operation": "SET_PARENT_MEDIA_COUNT",
                "from": declared,
                "to": actual
            })
            
        phash = generate_hash({k: p.get(k, "") for k in ["source_post_id", "target_account_id", "canonical_post_url", "media_count", "updated_at"]})
        chashes = {str(c.get("source_post_media_id", "")): generate_hash({k: c.get(k, "") for k in ["source_post_media_id", "source_post_id", "media_index", "canonical_post_url", "content_hash", "original_media_url", "cloudinary_public_id", "media_asset_id", "updated_at"]}) for c in children if str(c.get("source_post_media_id", ""))}
        
        parent_repairs.append({
            "source_post_id": pid,
            "account_id": str(p.get("target_account_id", "")),
            "declared_media_count": declared,
            "actual_child_count": actual,
            "unique_media_index_count": len(idx_groups),
            "canonical_mismatch_child_ids": canonical_mismatch_child_ids,
            "duplicate_index_groups": duplicate_index_groups,
            "operations": ops,
            "blocker_codes": blocker_codes,
            "apply_eligible": apply_eligible,
            "parent_precondition_hash": phash,
            "child_precondition_hashes": chashes
        })

    stale_slot_reviews = []
    q_by_id = {str(r.get("queue_id", "")): r for r in queue}
    res_by_id = {str(r.get("result_id", "")): r for r in posted_results}
    
    for sid in TARGET_SLOT_RUN_IDS:
        slots = [r for r in content_slot_runs if str(r.get("slot_run_id", "")) == sid]
        if not slots:
            status_reasons.append("SLOT_NOT_FOUND")
            continue
        if len(slots) > 1:
            status_reasons.append("MULTIPLE_SLOTS")
            continue
            
        s = slots[0]
        qid = str(s.get("queue_id", ""))
        rid = str(s.get("result_id", ""))
        purl = str(s.get("post_url", ""))
        stat = str(s.get("status", "")).upper()
        cstat = str(s.get("claim_status", "")).upper()
        
        q_stat = str(q_by_id.get(qid, {}).get("status", "")).upper() if qid else ""
        r_stat = str(res_by_id.get(rid, {}).get("status", "")).upper() if rid else ""
        
        now_utc = datetime.now(timezone.utc)
        expired = False
        exp = str(s.get("lease_expires_at", ""))
        if exp:
            try:
                if not exp.endswith("Z") and "+" not in exp: exp += "Z"
                if datetime.fromisoformat(exp.replace("Z", "+00:00")) < now_utc:
                    expired = True
            except Exception: pass
            
        has_evidence = False
        if purl: has_evidence = True
        if rid and r_stat in {"POSTED", "RECOVERED"}: has_evidence = True
        if qid and q_stat in {"POSTED", "POSTED_SAVE_FAILED"}: has_evidence = True
        if stat in {"POSTED_PRIMARY", "POSTED_FALLBACK", "BACKFILLED", "POSTED"}: has_evidence = True
        
        rec = "MANUAL_REVIEW"
        if has_evidence:
            rec = "NO_ACTION_POST_EVIDENCE_PRESENT"
        elif stat == "RECOVERY_REQUIRED":
            rec = "ALREADY_RECOVERY_REQUIRED"
        elif expired and stat in {"CLAIMED", "RUNNING"}:
            rec = "ELIGIBLE_TO_MARK_RECOVERY_REQUIRED"
        elif expired and cstat in {"CLAIMED", "RUNNING"}:
            rec = "ELIGIBLE_TO_MARK_RECOVERY_REQUIRED"
            
        stale_slot_reviews.append({
            "slot_run_id": sid,
            "account_id": str(s.get("account_id", "")),
            "slot_id": str(s.get("slot_id", "")),
            "status": stat,
            "claim_status": cstat,
            "lease_expired": expired,
            "has_queue_id": bool(qid),
            "linked_queue_status": q_stat,
            "has_result_id": bool(rid),
            "linked_result_status": r_stat,
            "has_post_url": bool(purl),
            "recommendation": rec,
            "blocker_codes": [],
            "precondition_hash": generate_hash({k: s.get(k, "") for k in sorted(s.keys())})
        })

    ext_blockers = [
        {
            "code": "LIVER_THREADS_SOURCE_MISSING",
            "resolution": "USER_OR_OWNER_APPROVED_SOURCE_REQUIRED"
        },
        {
            "code": "LIVER_PERMISSION_PARTIAL_COVERAGE",
            "source_id": "src_lm_yt_cand_001",
            "resolution": "VALID_PERMISSION_EVIDENCE_OR_SOURCE_DEACTIVATION_REQUIRED"
        }
    ]

    try:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception: head = ""
    try:
        orig = subprocess.check_output(["git", "rev-parse", "origin/main"], text=True).strip()
    except Exception: orig = ""

    overall = "READY_FOR_REVIEW"
    if status_reasons or sheets_verifier["failed_count"] > 0 or missing_tabs or read_errors:
        overall = "BLOCKED"
    if check_safety_flags() or sheets_verifier["failed_count"] > 0:
        overall = "FAIL"

    # specific block conditions
    if any(p["parent_precondition_hash"] == "" for p in parent_repairs):
        overall = "BLOCKED"
    if len(parent_repairs) != len(TARGET_SOURCE_POST_IDS):
        overall = "BLOCKED"
    if len(stale_slot_reviews) != len(TARGET_SLOT_RUN_IDS):
        overall = "BLOCKED"

    report = {
        "schema_version": 1,
        "mode": "READ_ONLY_REPAIR_PLAN",
        "implementation_head": head,
        "origin_main": orig,
        "overall_status": overall,
        "status_reasons": status_reasons,
        "safety": {},
        "sheets_verifier": sheets_verifier,
        "parent_repairs": parent_repairs,
        "stale_slot_reviews": stale_slot_reviews,
        "external_blockers": ext_blockers,
        "missing_tabs": missing_tabs,
        "read_errors": read_errors
    }

    with open(args.output, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"WP3C_SAFE_REPAIR_PLAN_JSON={json.dumps(report, ensure_ascii=False)}")
    sys.exit(0)

if __name__ == "__main__":
    main()
