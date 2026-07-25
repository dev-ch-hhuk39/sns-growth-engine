#!/usr/bin/env python3
import argparse
import json
import os
import sys
import hashlib
from urllib.parse import urlsplit, urlunsplit
from datetime import datetime, timezone

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

CHILD_HASH_FIELDS = (
    "source_post_media_id",
    "source_post_id",
    "media_index",
    "canonical_post_url",
    "content_hash",
    "original_media_url",
    "cloudinary_public_id",
    "media_asset_id",
    "updated_at",
)

SLOT_HASH_FIELDS = (
    "slot_run_id",
    "account_id",
    "slot_id",
    "status",
    "claim_status",
    "lease_expires_at",
    "queue_id",
    "result_id",
    "post_url",
    "updated_at",
)

ALLOWED_RIGHTS_STATUSES = {
    "allowed",
    "approved",
    "owned",
    "licensed",
    "approved_creator_clip",
    "approved_media",
    "own_media",
}

def is_truthy(value) -> bool:
    return str(value).strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
    }

def safe_int(val, default=0):
    try:
        if val is None or val == "": return default
        return int(float(val))
    except (ValueError, TypeError):
        return default

def media_index_sort_key(value):
    if isinstance(value, int):
        return (0, value)
    return (1, str(value))

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

def canonicalize_threads_identity(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""

    if "://" in raw:
        return canonicalize_source_url(raw)

    handle = raw.lstrip("@")
    return canonicalize_source_url(
        f"https://threads.net/@{handle}"
    )

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

def build_failure_report(
    reason: str,
    *,
    implementation_head: str = "",
    origin_main: str = "",
    missing_tabs: list[str] | None = None,
    read_errors: list[dict] | None = None,
    sheets_verifier: dict | None = None,
) -> dict:
    return {
        "schema_version": 1,
        "mode": "READ_ONLY_REPAIR_PLAN",
        "implementation_head": implementation_head,
        "origin_main": origin_main,
        "overall_status": "FAIL",
        "status_reasons": [reason] if reason else [],
        "safety": {},
        "sheets_verifier": sheets_verifier or {
            "passed": 0,
            "total": 0,
            "failed_count": 0
        },
        "parent_repairs": [],
        "stale_slot_reviews": [],
        "external_blockers": [],
        "missing_tabs": missing_tabs or [],
        "read_errors": read_errors or []
    }

def classify_asset_relation(rows: list[dict]) -> str:
    if len(rows) < 2:
        return "DISTINCT_ASSET"
        
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            r1, r2 = rows[i], rows[j]
            h1 = str(r1.get("content_hash", ""))
            h2 = str(r2.get("content_hash", ""))
            if h1 and h2 and h1 == h2:
                return "SAME_ASSET"
            
            m1 = canonicalize_source_url(str(r1.get("original_media_url", "")))
            m2 = canonicalize_source_url(str(r2.get("original_media_url", "")))
            if m1 and m2 and m1 == m2:
                return "SAME_ASSET"
                
            c1 = str(r1.get("cloudinary_public_id", ""))
            c2 = str(r2.get("cloudinary_public_id", ""))
            if c1 and c2 and c1 == c2:
                return "SAME_ASSET"
                
            a1 = str(r1.get("media_asset_id", ""))
            a2 = str(r2.get("media_asset_id", ""))
            if a1 and a2 and a1 == a2:
                return "SAME_ASSET"
                
    sig_fields = ["content_hash", "original_media_url", "cloudinary_public_id", "media_asset_id"]
    for field in sig_fields:
        vals = set()
        all_present = True
        for r in rows:
            v = str(r.get(field, ""))
            if field == "original_media_url":
                v = canonicalize_source_url(v)
            if not v:
                all_present = False
                break
            vals.add(v)
        if all_present and len(vals) == len(rows):
            return "DISTINCT_ASSET"
            
    return "UNKNOWN"

def empty_parent_repair(
    source_post_id: str,
    blocker_code: str,
) -> dict:
    return {
        "source_post_id": source_post_id,
        "account_id": "",
        "declared_media_count": 0,
        "actual_child_count": 0,
        "unique_media_index_count": 0,
        "canonical_mismatch_child_ids": [],
        "duplicate_index_groups": [],
        "operations": [],
        "blocker_codes": [blocker_code],
        "apply_eligible": False,
        "parent_precondition_hash": "",
        "child_precondition_hashes": {},
    }

def plan_parent_repair(
    parent_id: str,
    parent_rows: list[dict],
    child_rows: list[dict],
) -> dict:
    if not parent_rows:
        return empty_parent_repair(
            parent_id,
            "PARENT_NOT_FOUND",
        )

    if len(parent_rows) > 1:
        return empty_parent_repair(
            parent_id,
            "MULTIPLE_PARENTS",
        )
        
    p = parent_rows[0]
    apply_eligible = True
    blocker_codes = set()
    ops = []
    
    p_canon = canonicalize_source_url(str(p.get("canonical_post_url", "")))
    if not p_canon:
        blocker_codes.add("PARENT_CANONICAL_URL_MISSING")
        apply_eligible = False
        
    canonical_mismatch_child_ids = []
    for c in child_rows:
        c_id = str(c.get("source_post_media_id", ""))
        if not c_id:
            blocker_codes.add("CHILD_ID_MISSING")
            apply_eligible = False
            continue
        c_canon_raw = str(c.get("canonical_post_url", ""))
        if not c_canon_raw:
            if p_canon:
                blocker_codes.add("CHILD_CANONICAL_URL_MISSING")
                apply_eligible = False
            continue
            
        c_canon = canonicalize_source_url(c_canon_raw)
        if p_canon and c_canon and p_canon != c_canon:
            canonical_mismatch_child_ids.append(c_id)
            ops.append({
                "operation": "SET_CHILD_CANONICAL_URL_FROM_PARENT",
                "source_post_media_id": c_id,
                "precondition": "PARENT_AND_CHILD_CANONICAL_URL_PRESENT"
            })
            
    used_indices = set()
    idx_groups = {}
    for c in child_rows:
        try:
            idx = int(str(c.get("media_index", "")))
            if idx < 0:
                blocker_codes.add("NEGATIVE_MEDIA_INDEX")
                apply_eligible = False
            else:
                used_indices.add(idx)
        except ValueError:
            idx = str(c.get("media_index", ""))
            blocker_codes.add("MALFORMED_MEDIA_INDEX")
            apply_eligible = False
            
        if idx not in idx_groups: idx_groups[idx] = []
        idx_groups[idx].append(c)
        
    duplicate_index_groups = []
    all_child_ids_seen = set()
    
    for idx in sorted(idx_groups.keys(), key=media_index_sort_key):
        items = idx_groups[idx]
        for it in items:
            cid = str(it.get("source_post_media_id", ""))
            if cid in all_child_ids_seen:
                blocker_codes.add("DUPLICATE_CHILD_ID")
                apply_eligible = False
            all_child_ids_seen.add(cid)
            
        if len(items) > 1:
            relation = classify_asset_relation(items)
            cids = [str(it.get("source_post_media_id", "")) for it in items]
            
            duplicate_index_groups.append({
                "media_index": idx,
                "child_ids": cids,
                "asset_relation": relation
            })
            
            if relation in {"SAME_ASSET", "UNKNOWN"}:
                blocker_codes.add("DUPLICATE_MEDIA_REQUIRES_MANUAL_DECISION")
                apply_eligible = False
            elif relation == "DISTINCT_ASSET":
                sorted_items = sorted(items, key=lambda x: (str(x.get("created_at", "")), str(x.get("source_post_media_id", ""))))
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

    try:
        declared = int(str(p.get("media_count", "")))
        if declared < 0:
            blocker_codes.add("NEGATIVE_PARENT_MEDIA_COUNT")
            apply_eligible = False
    except ValueError:
        declared = -1
        blocker_codes.add("MALFORMED_PARENT_MEDIA_COUNT")
        apply_eligible = False
        
    actual = len(child_rows)
    if apply_eligible and declared != actual:
        ops.append({
            "operation": "SET_PARENT_MEDIA_COUNT",
            "from": declared,
            "to": actual
        })
        
    ops.sort(key=lambda x: (
        0 if x["operation"] == "SET_CHILD_CANONICAL_URL_FROM_PARENT" else 
        1 if x["operation"] == "SET_MEDIA_INDEX" else 2,
        x.get("source_post_media_id", "")
    ))
        
    phash = generate_hash({k: p.get(k, "") for k in ["source_post_id", "target_account_id", "canonical_post_url", "media_count", "updated_at"]})
    chashes = {str(c.get("source_post_media_id", "")): generate_hash({k: c.get(k, "") for k in CHILD_HASH_FIELDS}) for c in child_rows if str(c.get("source_post_media_id", ""))}
    
    return {
        "source_post_id": parent_id,
        "account_id": str(p.get("target_account_id", "")),
        "declared_media_count": declared,
        "actual_child_count": actual,
        "unique_media_index_count": len(idx_groups),
        "canonical_mismatch_child_ids": sorted(canonical_mismatch_child_ids),
        "duplicate_index_groups": duplicate_index_groups,
        "operations": ops,
        "blocker_codes": sorted(list(blocker_codes)),
        "apply_eligible": apply_eligible,
        "parent_precondition_hash": phash,
        "child_precondition_hashes": chashes
    }

def plan_stale_slot_review(
    slot_run_id: str,
    slot_rows: list[dict],
    queue_by_id: dict[str, dict],
    result_by_id: dict[str, dict],
    *,
    now: datetime,
) -> dict:
    if not slot_rows:
        return {"slot_run_id": slot_run_id, "blocker_codes": ["SLOT_NOT_FOUND"], "recommendation": "MANUAL_REVIEW"}
    if len(slot_rows) > 1:
        return {"slot_run_id": slot_run_id, "blocker_codes": ["MULTIPLE_SLOTS"], "recommendation": "MANUAL_REVIEW"}
        
    s = slot_rows[0]
    qid = str(s.get("queue_id", ""))
    rid = str(s.get("result_id", ""))
    purl = str(s.get("post_url", ""))
    stat = str(s.get("status", "")).upper()
    cstat = str(s.get("claim_status", "")).upper()
    
    q_stat = str(queue_by_id.get(qid, {}).get("status", "")).upper() if qid else ""
    r_stat = str(result_by_id.get(rid, {}).get("status", "")).upper() if rid else ""
    
    expired = False
    blocker_codes = set()
    exp = str(s.get("lease_expires_at", ""))
    if exp:
        try:
            if not exp.endswith("Z") and "+" not in exp: exp += "Z"
            dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt < now:
                expired = True
        except Exception:
            blocker_codes.add("LEASE_TIMESTAMP_INVALID")
        
    has_evidence = False
    if purl: has_evidence = True
    if rid and r_stat in {"POSTED", "RECOVERED"}: has_evidence = True
    if qid and q_stat in {"POSTED", "POSTED_SAVE_FAILED"}: has_evidence = True
    if stat in {"POSTED_PRIMARY", "POSTED_FALLBACK", "BACKFILLED", "POSTED"}: has_evidence = True
    
    rec = "MANUAL_REVIEW"
    if "LEASE_TIMESTAMP_INVALID" in blocker_codes:
        rec = "MANUAL_REVIEW"
    elif has_evidence:
        rec = "NO_ACTION_POST_EVIDENCE_PRESENT"
    elif stat == "RECOVERY_REQUIRED":
        rec = "ALREADY_RECOVERY_REQUIRED"
    elif expired and stat in {"CLAIMED", "RUNNING"}:
        rec = "ELIGIBLE_TO_MARK_RECOVERY_REQUIRED"
    elif expired and cstat in {"CLAIMED", "RUNNING"}:
        rec = "ELIGIBLE_TO_MARK_RECOVERY_REQUIRED"
        
    precondition_hash = generate_hash({
        key: s.get(key, "")
        for key in SLOT_HASH_FIELDS
    })
        
    return {
        "slot_run_id": slot_run_id,
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
        "blocker_codes": sorted(list(blocker_codes)),
        "precondition_hash": precondition_hash
    }

def parse_target_account_ids(raw_val: str) -> set:
    if not raw_val:
        return set()
    v = raw_val.strip()
    if v.startswith("[") and v.endswith("]"):
        try:
            arr = json.loads(v)
            if isinstance(arr, list):
                return set(str(x).strip() for x in arr if str(x).strip())
        except Exception:
            pass
    if "|" in v:
        return set(x.strip() for x in v.split("|") if x.strip())
    if "," in v:
        return set(x.strip() for x in v.split(",") if x.strip())
    return {v}

def evaluate_external_blockers(
    source_accounts: list[dict],
    media_permissions: list[dict],
    accounts: list[dict],
    *,
    now: datetime,
) -> list[dict]:
    blockers = []
    
    dest_handles = set()
    for acc in accounts:
        h = str(acc.get("threads_handle", "")).strip()
        if h:
            dest_handles.add(canonicalize_threads_identity(h))
    
    liver_threads_found = False
    for a in source_accounts:
        t_id = str(a.get("target_account_id", ""))
        t_ids = parse_target_account_ids(str(a.get("target_account_ids", "")))
        plat = str(a.get("platform", "")).lower() or str(a.get("source_platform", "")).lower()
        
        if (t_id == "liver_manager" or "liver_manager" in t_ids) and "threads" in plat:
            act = is_truthy(a.get("active", ""))
            blk = is_truthy(a.get("blocked", ""))
            url = str(a.get("source_url", ""))
            rev = str(a.get("review_status", "")).upper()
            cand = str(a.get("candidate_status", "")).upper()
            
            c_url = canonicalize_source_url(url)
            if c_url in dest_handles:
                continue
                
            if act and not blk and url and (rev == "APPROVED" or cand == "APPROVED"):
                liver_threads_found = True
                break
                
    if not liver_threads_found:
        blockers.append({
            "code": "LIVER_THREADS_SOURCE_MISSING",
            "resolution": "USER_OR_OWNER_APPROVED_SOURCE_REQUIRED"
        })
        
    perm_rows = [p for p in media_permissions if str(p.get("source_id", "")) == "src_lm_yt_cand_001"]
    valid_perm = False
    if perm_rows:
        for i, r in enumerate(perm_rows):
            r["_original_index"] = i
            
        def perm_sort_key(r):
            u = str(r.get("updated_at", ""))
            a = str(r.get("approved_at", ""))
            return (u, a, r["_original_index"])
            
        latest = sorted(perm_rows, key=perm_sort_key)[-1]
        
        rev = is_truthy(latest.get("revoked", ""))
        p_stat = str(latest.get("permission_status", "")).lower()
        r_stat = str(latest.get("rights_status", "")).lower()
        ev_type = str(latest.get("evidence_type", ""))
        ev_ref = str(latest.get("evidence_reference", ""))
        
        expired = False
        malformed_lease = False
        exp = str(latest.get("expires_at", ""))
        if exp:
            try:
                if not exp.endswith("Z") and "+" not in exp: exp += "Z"
                dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt < now:
                    expired = True
            except Exception:
                malformed_lease = True
                expired = True
                
        if (not rev and p_stat in {"approved", "granted"} and 
            r_stat in ALLOWED_RIGHTS_STATUSES and not expired and not malformed_lease and 
            ev_type and ev_ref):
            valid_perm = True
            
    if not valid_perm:
        blockers.append({
            "code": "LIVER_PERMISSION_PARTIAL_COVERAGE",
            "source_id": "src_lm_yt_cand_001",
            "resolution": "VALID_PERMISSION_EVIDENCE_OR_SOURCE_DEACTIVATION_REQUIRED"
        })
        
    return blockers

def build_repair_plan(
    datasets: dict[str, list[dict]],
    *,
    verifier_result: dict,
    implementation_head: str,
    origin_main: str,
    now: datetime,
) -> dict:
    source_posts = datasets.get("source_posts", [])
    source_post_media = datasets.get("source_post_media", [])
    content_slot_runs = datasets.get("content_slot_runs", [])
    queue = datasets.get("queue", [])
    posted_results = datasets.get("posted_results", [])
    media_permissions = datasets.get("media_permissions", [])
    source_accounts = datasets.get("source_accounts", [])
    accounts = datasets.get("accounts", [])
    
    sheets_verifier = {
        "passed": safe_int(verifier_result.get("passed")),
        "total": safe_int(verifier_result.get("total")),
        "failed_count": len(verifier_result.get("failed", []))
    }
    
    parent_repairs = []
    for pid in TARGET_SOURCE_POST_IDS:
        p_rows = [r for r in source_posts if str(r.get("source_post_id", "")) == pid]
        c_rows = [r for r in source_post_media if str(r.get("source_post_id", "")) == pid]
        rep = plan_parent_repair(pid, p_rows, c_rows)
        parent_repairs.append(rep)
        
    stale_slot_reviews = []
    q_by_id = {str(r.get("queue_id", "")): r for r in queue}
    r_by_id = {str(r.get("result_id", "")): r for r in posted_results}
    for sid in TARGET_SLOT_RUN_IDS:
        s_rows = [r for r in content_slot_runs if str(r.get("slot_run_id", "")) == sid]
        rev = plan_stale_slot_review(sid, s_rows, q_by_id, r_by_id, now=now)
        stale_slot_reviews.append(rev)
        
    ext_blockers = evaluate_external_blockers(source_accounts, media_permissions, accounts, now=now)
    
    overall = "READY_FOR_REVIEW"
    
    if sheets_verifier["failed_count"] > 0:
        overall = "FAIL"
        
    blocking_codes = {
        "PARENT_NOT_FOUND", "MULTIPLE_PARENTS", "SLOT_NOT_FOUND", "MULTIPLE_SLOTS",
        "CHILD_ID_MISSING", "DUPLICATE_CHILD_ID"
    }
    
    for p in parent_repairs:
        if set(p.get("blocker_codes", [])) & blocking_codes:
            if overall != "FAIL": overall = "BLOCKED"
        if not p.get("parent_precondition_hash"):
            if overall != "FAIL": overall = "BLOCKED"
            
    for s in stale_slot_reviews:
        if set(s.get("blocker_codes", [])) & blocking_codes:
            if overall != "FAIL": overall = "BLOCKED"

    return {
        "schema_version": 1,
        "mode": "READ_ONLY_REPAIR_PLAN",
        "implementation_head": implementation_head,
        "origin_main": origin_main,
        "overall_status": overall,
        "status_reasons": ["SHEETS_VERIFIER_FAILED"] if sheets_verifier["failed_count"] > 0 else [],
        "safety": {},
        "sheets_verifier": sheets_verifier,
        "parent_repairs": parent_repairs,
        "stale_slot_reviews": stale_slot_reviews,
        "external_blockers": ext_blockers,
        "missing_tabs": [],
        "read_errors": []
    }

def _get_git_head() -> str:
    try:
        return os.popen("git rev-parse HEAD").read().strip()
    except Exception:
        return ""

def _get_git_origin_main() -> str:
    try:
        return os.popen("git rev-parse origin/main").read().strip()
    except Exception:
        return ""

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    head = _get_git_head()
    origin_main = _get_git_origin_main()

    if check_safety_flags():
        rep = build_failure_report("SAFETY_FLAG_TRUE", implementation_head=head, origin_main=origin_main)
        with open(args.output, "w") as f:
            json.dump(rep, f, indent=2, ensure_ascii=False)
        print(f"WP3C_SAFE_REPAIR_PLAN_JSON={json.dumps(rep, ensure_ascii=False)}")
        sys.exit(1)

    try:
        from config_loader import get_config
        from sheets_client import SheetsClient
        from recover_production_sheets_threads_first import verify_state
        
        cfg = get_config()
        client = SheetsClient(cfg.get("sheet_id", ""), cfg.get("sa_dict", {}), dry_run=True)
        prevent_writes(client)
    except Exception:
        rep = build_failure_report("UNEXPECTED_EXCEPTION", implementation_head=head, origin_main=origin_main)
        with open(args.output, "w") as f:
            json.dump(rep, f, indent=2, ensure_ascii=False)
        print(f"WP3C_SAFE_REPAIR_PLAN_JSON={json.dumps(rep, ensure_ascii=False)}")
        sys.exit(1)

    missing_tabs = []
    read_errors = []
    datasets = {}
    
    def fetch_records(name):
        try:
            ws = client._ws(name)
            prevent_writes(ws)
            return [dict(r) for r in ws.get_all_records()]
        except Exception as e:
            if "WorksheetNotFound" in type(e).__name__ or "WorksheetNotFound" in str(e):
                missing_tabs.append(name)
            else:
                read_errors.append({"tab": name, "error_type": type(e).__name__})
            return []

    tabs = [
        "source_posts", "source_post_media", "content_slot_runs",
        "queue", "posted_results", "media_permissions", "source_accounts", "accounts"
    ]
    for t in tabs:
        datasets[t] = fetch_records(t)
        
    try:
        verifier_data = verify_state(client)
    except Exception:
        rep = build_failure_report("UNEXPECTED_EXCEPTION", implementation_head=head, origin_main=origin_main)
        with open(args.output, "w") as f:
            json.dump(rep, f, indent=2, ensure_ascii=False)
        print(f"WP3C_SAFE_REPAIR_PLAN_JSON={json.dumps(rep, ensure_ascii=False)}")
        sys.exit(1)

    if missing_tabs or read_errors:
        rep = build_failure_report(
            "READ_ERROR", 
            implementation_head=head, 
            origin_main=origin_main,
            missing_tabs=missing_tabs,
            read_errors=read_errors
        )
        with open(args.output, "w") as f:
            json.dump(rep, f, indent=2, ensure_ascii=False)
        print(f"WP3C_SAFE_REPAIR_PLAN_JSON={json.dumps(rep, ensure_ascii=False)}")
        sys.exit(1)

    now = datetime.now(timezone.utc)
    rep = build_repair_plan(
        datasets,
        verifier_result=verifier_data,
        implementation_head=head,
        origin_main=origin_main,
        now=now
    )
    
    with open(args.output, "w") as f:
        json.dump(rep, f, indent=2, ensure_ascii=False)
    print(f"WP3C_SAFE_REPAIR_PLAN_JSON={json.dumps(rep, ensure_ascii=False)}")
    
    if rep["overall_status"] == "FAIL":
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()
