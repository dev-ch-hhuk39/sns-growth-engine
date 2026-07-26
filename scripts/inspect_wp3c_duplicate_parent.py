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

TARGET_SOURCE_POST_ID = "sp_src_lm_yt_user_001_UCzFzty7aEd4tw3NqCW6pkLQ"

COMPARISON_FIELDS = (
    "source_post_id",
    "target_account_id",
    "account_id",
    "source_account_id",
    "platform",
    "source_platform",
    "canonical_post_url",
    "media_count",
    "post_type",
    "status",
    "created_at",
    "updated_at",
)

REQUIRED_FIELDS = (
    "source_post_id",
    "canonical_post_url",
    "media_count",
)

def safe_int(val, default=0):
    try:
        if val is None or val == "": return default
        return int(float(val))
    except (ValueError, TypeError):
        return default

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
        "mode": "READ_ONLY_DUPLICATE_PARENT_INSPECTION",
        "implementation_head": implementation_head,
        "origin_main": origin_main,
        "overall_status": "FAIL",
        "status_reasons": [reason] if reason else [],
        "sheets_verifier": sheets_verifier or {
            "passed": 0,
            "total": 0,
            "failed_count": 0
        },
        "target_source_post_id": TARGET_SOURCE_POST_ID,
        "parent_candidate_count": 0,
        "parent_candidates": [],
        "child_summary": {},
        "recommended_keep_sheet_row_number": None,
        "manual_delete_candidate_sheet_row_numbers": [],
        "apply_operations": [],
        "missing_tabs": missing_tabs or [],
        "read_errors": read_errors or []
    }

def inspect_duplicate_parent(
    source_posts_rows: list[tuple[int, dict]],
    source_post_media_rows: list[tuple[int, dict]],
    *,
    verifier_result: dict,
    implementation_head: str,
    origin_main: str,
) -> dict:
    
    from plan_wp3c_production_repairs import normalize_sheets_verifier
    sheets_verifier = normalize_sheets_verifier(verifier_result)
    
    if not sheets_verifier.get("count_consistent"):
        rep = build_failure_report("SHEETS_VERIFIER_COUNT_INCONSISTENT", implementation_head=implementation_head, origin_main=origin_main, sheets_verifier=sheets_verifier)
        return rep
    
    if sheets_verifier["failed_count"] > 0:
        rep = build_failure_report("SHEETS_VERIFIER_FAILED", implementation_head=implementation_head, origin_main=origin_main, sheets_verifier=sheets_verifier)
        return rep
        
    parents = [r for r in source_posts_rows if str(r[1].get("source_post_id", "")) == TARGET_SOURCE_POST_ID]
    children = [r for r in source_post_media_rows if str(r[1].get("source_post_id", "")) == TARGET_SOURCE_POST_ID]
    
    if len(parents) < 2:
        overall = "BLOCKED"
        reasons = ["NOT_ENOUGH_PARENTS"]
        return {
            "schema_version": 1,
            "mode": "READ_ONLY_DUPLICATE_PARENT_INSPECTION",
            "implementation_head": implementation_head,
            "origin_main": origin_main,
            "overall_status": overall,
            "status_reasons": reasons,
            "sheets_verifier": sheets_verifier,
            "target_source_post_id": TARGET_SOURCE_POST_ID,
            "parent_candidate_count": len(parents),
            "parent_candidates": [],
            "child_summary": {},
            "recommended_keep_sheet_row_number": None,
            "manual_delete_candidate_sheet_row_numbers": [],
            "apply_operations": [],
            "missing_tabs": [],
            "read_errors": []
        }
        
    child_count = len(children)
    child_ids = []
    media_indices = []
    duplicate_child_ids = 0
    missing_child_ids = 0
    malformed_media_indices = 0
    negative_media_indices = 0
    
    for _, c in children:
        cid = str(c.get("source_post_media_id", ""))
        if not cid:
            missing_child_ids += 1
        else:
            if cid in child_ids:
                duplicate_child_ids += 1
            child_ids.append(cid)
            
        try:
            idx = int(str(c.get("media_index", "")))
            if idx < 0:
                negative_media_indices += 1
            else:
                media_indices.append(idx)
        except ValueError:
            malformed_media_indices += 1
            
    unique_child_id_count = len(set(child_ids))
    unique_media_index_count = len(set(media_indices))
    
    seen_indices = set()
    dup_indices = set()
    for idx in media_indices:
        if idx in seen_indices:
            dup_indices.add(idx)
        seen_indices.add(idx)
        
    child_summary = {
        "child_count": child_count,
        "unique_child_id_count": unique_child_id_count,
        "child_id_duplicate_count": duplicate_child_ids,
        "media_indexes": sorted(list(set(media_indices))),
        "unique_media_index_count": unique_media_index_count,
        "duplicate_media_indexes": sorted(list(dup_indices)),
        "missing_child_id_count": missing_child_ids,
        "malformed_media_index_count": malformed_media_indices,
        "negative_media_index_count": negative_media_indices
    }
    
    candidates = []
    
    for i, (r_idx, p) in enumerate(parents):
        p_canon = canonicalize_source_url(str(p.get("canonical_post_url", "")))
        
        req_count = 0
        for f in REQUIRED_FIELDS:
            if str(p.get(f, "")).strip():
                req_count += 1
        if str(p.get("target_account_id", "")).strip() or str(p.get("account_id", "")).strip():
            req_count += 1
            
        matching_count = 0
        mismatch_ids = []
        for _, c in children:
            c_canon = canonicalize_source_url(str(c.get("canonical_post_url", "")))
            if c_canon and p_canon:
                if c_canon == p_canon:
                    matching_count += 1
                else:
                    cid = str(c.get("source_post_media_id", ""))
                    if cid:
                        mismatch_ids.append(cid)
                        
        p_hash_obj = {k: str(p.get(k, "")) for k in COMPARISON_FIELDS}
        p_hash = generate_hash(p_hash_obj)
        
        candidates.append({
            "candidate_number": i + 1,
            "sheet_row_number": r_idx,
            "source_post_id": str(p.get("source_post_id", "")),
            "account_id": str(p.get("target_account_id", "")) or str(p.get("account_id", "")),
            "declared_media_count": safe_int(p.get("media_count", "")),
            "has_canonical_post_url": bool(str(p.get("canonical_post_url", "")).strip()),
            "canonical_identity_hash": generate_hash({"url": p_canon}) if p_canon else "",
            "has_updated_at": bool(str(p.get("updated_at", "")).strip()),
            "required_field_presence_count": req_count,
            "parent_precondition_hash": p_hash,
            "canonical_matching_child_count": matching_count,
            "canonical_mismatching_child_ids": sorted(mismatch_ids),
            "material_difference_fields": [],
            "recommended_disposition": "",
            "blocker_codes": []
        })
        
    for i, c1 in enumerate(candidates):
        for j, c2 in enumerate(candidates):
            if i != j:
                p1 = parents[i][1]
                p2 = parents[j][1]
                for f in COMPARISON_FIELDS:
                    if str(p1.get(f, "")) != str(p2.get(f, "")) and f not in c1["material_difference_fields"]:
                        c1["material_difference_fields"].append(f)
                        
        c1["material_difference_fields"].sort()
        
    keep_idx = -1
    overall = "READY_FOR_MANUAL_DECISION"
    
    if len(candidates) == 2:
        c1 = candidates[0]
        c2 = candidates[1]
        
        if c1["parent_precondition_hash"] == c2["parent_precondition_hash"] and not c1["material_difference_fields"] and not c2["material_difference_fields"]:
            if c1["sheet_row_number"] < c2["sheet_row_number"]:
                c1["recommended_disposition"] = "KEEP_CANDIDATE"
                c2["recommended_disposition"] = "EXACT_DUPLICATE_MANUAL_DELETE_CANDIDATE"
                keep_idx = 0
            else:
                c2["recommended_disposition"] = "KEEP_CANDIDATE"
                c1["recommended_disposition"] = "EXACT_DUPLICATE_MANUAL_DELETE_CANDIDATE"
                keep_idx = 1
        else:
            c1_match_all = (c1["canonical_matching_child_count"] == child_count and child_count > 0)
            c2_match_all = (c2["canonical_matching_child_count"] == child_count and child_count > 0)
            
            if c1_match_all and not c2_match_all:
                c1["recommended_disposition"] = "KEEP_CANDIDATE"
                c2["recommended_disposition"] = "MANUAL_DELETE_CANDIDATE"
                keep_idx = 0
            elif c2_match_all and not c1_match_all:
                c2["recommended_disposition"] = "KEEP_CANDIDATE"
                c1["recommended_disposition"] = "MANUAL_DELETE_CANDIDATE"
                keep_idx = 1
            else:
                if c1["required_field_presence_count"] > c2["required_field_presence_count"]:
                    c1["recommended_disposition"] = "KEEP_CANDIDATE"
                    c2["recommended_disposition"] = "MANUAL_DELETE_CANDIDATE"
                    keep_idx = 0
                elif c2["required_field_presence_count"] > c1["required_field_presence_count"]:
                    c2["recommended_disposition"] = "KEEP_CANDIDATE"
                    c1["recommended_disposition"] = "MANUAL_DELETE_CANDIDATE"
                    keep_idx = 1
                else:
                    c1["recommended_disposition"] = "MANUAL_DECISION_REQUIRED"
                    c2["recommended_disposition"] = "MANUAL_DECISION_REQUIRED"
                    c1["blocker_codes"].append("DUPLICATE_PARENT_AMBIGUOUS")
                    c2["blocker_codes"].append("DUPLICATE_PARENT_AMBIGUOUS")
    else:
        for c in candidates:
            c["recommended_disposition"] = "MANUAL_DECISION_REQUIRED"
            c["blocker_codes"].append("DUPLICATE_PARENT_AMBIGUOUS")
            
    manual_delete_rows = []
    keep_row = None
    
    if keep_idx >= 0:
        keep_row = candidates[keep_idx]["sheet_row_number"]
        for i, c in enumerate(candidates):
            if i != keep_idx:
                manual_delete_rows.append(c["sheet_row_number"])
                
    return {
        "schema_version": 1,
        "mode": "READ_ONLY_DUPLICATE_PARENT_INSPECTION",
        "implementation_head": implementation_head,
        "origin_main": origin_main,
        "overall_status": overall,
        "status_reasons": [],
        "sheets_verifier": sheets_verifier,
        "target_source_post_id": TARGET_SOURCE_POST_ID,
        "parent_candidate_count": len(candidates),
        "parent_candidates": candidates,
        "child_summary": child_summary,
        "recommended_keep_sheet_row_number": keep_row,
        "manual_delete_candidate_sheet_row_numbers": sorted(manual_delete_rows),
        "apply_operations": [],
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
    args, unknown = parser.parse_known_args()
    
    if unknown:
        print("Error: Unknown arguments", file=sys.stderr)
        sys.exit(1)

    head = _get_git_head()
    origin_main = _get_git_origin_main()

    if check_safety_flags():
        rep = build_failure_report("SAFETY_FLAG_TRUE", implementation_head=head, origin_main=origin_main)
        with open(args.output, "w") as f:
            json.dump(rep, f, indent=2, ensure_ascii=False)
        print(f"WP3C2_SAFE_DUPLICATE_INSPECTION_JSON={json.dumps(rep, ensure_ascii=False)}")
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
        print(f"WP3C2_SAFE_DUPLICATE_INSPECTION_JSON={json.dumps(rep, ensure_ascii=False)}")
        sys.exit(1)

    missing_tabs = []
    read_errors = []
    
    source_posts_rows = []
    source_post_media_rows = []
    
    try:
        ws = client._ws("source_posts")
        prevent_writes(ws)
        all_recs = ws.get_all_records()
        for i, r in enumerate(all_recs):
            source_posts_rows.append((i + 2, dict(r)))
    except Exception as e:
        if "WorksheetNotFound" in type(e).__name__ or "WorksheetNotFound" in str(e):
            missing_tabs.append("source_posts")
        else:
            read_errors.append({"tab": "source_posts", "error_type": type(e).__name__})

    try:
        ws = client._ws("source_post_media")
        prevent_writes(ws)
        all_recs = ws.get_all_records()
        for i, r in enumerate(all_recs):
            source_post_media_rows.append((i + 2, dict(r)))
    except Exception as e:
        if "WorksheetNotFound" in type(e).__name__ or "WorksheetNotFound" in str(e):
            missing_tabs.append("source_post_media")
        else:
            read_errors.append({"tab": "source_post_media", "error_type": type(e).__name__})
            
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
        print(f"WP3C2_SAFE_DUPLICATE_INSPECTION_JSON={json.dumps(rep, ensure_ascii=False)}")
        sys.exit(1)

    try:
        verifier_data = verify_state(client)
    except Exception:
        rep = build_failure_report("UNEXPECTED_EXCEPTION", implementation_head=head, origin_main=origin_main)
        with open(args.output, "w") as f:
            json.dump(rep, f, indent=2, ensure_ascii=False)
        print(f"WP3C2_SAFE_DUPLICATE_INSPECTION_JSON={json.dumps(rep, ensure_ascii=False)}")
        sys.exit(1)

    rep = inspect_duplicate_parent(
        source_posts_rows,
        source_post_media_rows,
        verifier_result=verifier_data,
        implementation_head=head,
        origin_main=origin_main
    )
    
    with open(args.output, "w") as f:
        json.dump(rep, f, indent=2, ensure_ascii=False)
    print(f"WP3C2_SAFE_DUPLICATE_INSPECTION_JSON={json.dumps(rep, ensure_ascii=False)}")
    
    if rep["overall_status"] == "FAIL":
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()
