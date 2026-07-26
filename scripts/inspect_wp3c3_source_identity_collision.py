#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import json
import os
import sys
import hashlib
from collections import defaultdict
from urllib.parse import urlsplit, urlunsplit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, os.path.join(ROOT, "src"))

TARGET_SOURCE_POST_ID = "sp_src_lm_yt_user_001_UCzFzty7aEd4tw3NqCW6pkLQ"

def safe_int(val, default=0):
    try:
        if val is None or val == "": return default
        return int(float(val))
    except (ValueError, TypeError):
        return default

def sha256_text(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()

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

def read_rows_with_sheet_numbers(worksheet) -> list[tuple[int, dict]]:
    values = worksheet.get_all_values()
    if not values:
        return []
    headers = [str(value).strip() for value in values[0]]
    if not headers or not any(headers):
        raise ValueError("HEADER_ROW_MISSING")
    rows = []
    for sheet_row_number, values_row in enumerate(values[1:], start=2):
        padded = list(values_row) + [""] * (len(headers) - len(values_row))
        row = {
            header: padded[index] if index < len(padded) else ""
            for index, header in enumerate(headers)
            if header
        }
        if any(str(v).strip() for v in row.values()):
            rows.append((sheet_row_number, row))
    return rows

def build_failure_report(
    reason: str,
    *,
    implementation_head: str = "",
    origin_main: str = "",
) -> dict:
    return {
        "schema_version": 1,
        "mode": "READ_ONLY_SOURCE_IDENTITY_COLLISION_INSPECTION",
        "implementation_head": implementation_head,
        "origin_main": origin_main,
        "overall_status": "FAIL",
        "classification": "UNRESOLVED_IDENTITY",
        "status_reasons": [reason] if reason else [],
        "checked_commit_sha": implementation_head,
        "parent_count": 0,
        "child_count": 0,
        "unique_parent_post_identity_group_count": 0,
        "unique_child_post_identity_group_count": 0,
        "unique_post_identity_group_count": 0,
        "unique_child_id_group_count": 0,
        "unique_parent_fingerprint_group_count": 0,
        "unique_child_fingerprint_group_count": 0,
        "parents": [],
        "children": [],
        "recommended_next_action": "MANUAL_INVESTIGATION",
        "apply_operations": []
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

def strip_query_and_temp_signatures(url: str) -> str:
    if not url: return ""
    raw = str(url).strip()
    if "://" not in raw:
        raw = "https://" + raw.lstrip("/")
    parsed = urlsplit(raw)
    return urlunsplit((parsed.scheme, parsed.netloc.lower(), parsed.path, "", ""))

def inspect_wp3c3(source_posts_rows: list, source_post_media_rows: list, implementation_head: str, origin_main: str) -> dict:
    from source_post_identity import extract_source_post_identity
    
    parents = [r for r in source_posts_rows if str(r[1].get("source_post_id", "")) == TARGET_SOURCE_POST_ID]
    children = [r for r in source_post_media_rows if str(r[1].get("source_post_id", "")) == TARGET_SOURCE_POST_ID]
    
    parent_post_identity_hashes = set()
    child_post_identity_hashes = set()
    combined_post_identity_hashes = set()
    
    parent_fingerprint_hashes = set()
    child_id_hashes = set()
    child_fingerprint_hashes = set()
    
    raw_parents = []
    raw_children = []
    
    status_reasons = []
    
    # 1st pass to collect all identities for hashing
    for _, p in parents:
        url = str(p.get("canonical_post_url", ""))
        ident = extract_source_post_identity(url)
        if ident.confidence == "HIGH" and ident.stable_post_id:
            h = sha256_text(f"{ident.platform}:{ident.identity_kind}:{ident.stable_post_id}")
            parent_post_identity_hashes.add(h)
            combined_post_identity_hashes.add(h)

    for _, c in children:
        url = str(c.get("canonical_post_url", ""))
        ident = extract_source_post_identity(url)
        if ident.confidence == "HIGH" and ident.stable_post_id:
            h = sha256_text(f"{ident.platform}:{ident.identity_kind}:{ident.stable_post_id}")
            child_post_identity_hashes.add(h)
            combined_post_identity_hashes.add(h)
            
    for r_idx, p in parents:
        url = str(p.get("canonical_post_url", ""))
        ident = extract_source_post_identity(url)
        
        ident_hash = ""
        if ident.confidence == "HIGH" and ident.stable_post_id:
            ident_hash = sha256_text(f"{ident.platform}:{ident.identity_kind}:{ident.stable_post_id}")
            
        p_clone = dict(p)
        for k in ["canonical_post_url", "created_at", "updated_at"]:
            p_clone.pop(k, None)
        p_clone["_computed_ident_hash"] = ident_hash
        p_fingerprint = sha256_text(json.dumps(p_clone, sort_keys=True))
        parent_fingerprint_hashes.add(p_fingerprint)
        
        req_count = sum(1 for f in ["source_post_id", "canonical_post_url", "media_count"] if str(p.get(f, "")).strip())
        if str(p.get("target_account_id", "")).strip() or str(p.get("account_id", "")).strip():
            req_count += 1
            
        matching_child_count = 0
        if ident_hash:
            for _, c in children:
                curl = str(c.get("canonical_post_url", ""))
                cident = extract_source_post_identity(curl)
                if cident.confidence == "HIGH" and cident.stable_post_id:
                    chash = sha256_text(f"{cident.platform}:{cident.identity_kind}:{cident.stable_post_id}")
                    if chash == ident_hash:
                        matching_child_count += 1
        
        raw_parents.append({
            "candidate_number": len(raw_parents) + 1,
            "sheet_row_number": r_idx,
            "platform": ident.platform,
            "identity_kind": ident.identity_kind,
            "identity_extracted": ident.confidence == "HIGH",
            "ident_hash": ident_hash,
            "declared_media_count": safe_int(p.get("media_count", "")),
            "required_field_presence_count": req_count,
            "has_created_at": bool(str(p.get("created_at", "")).strip()),
            "has_updated_at": bool(str(p.get("updated_at", "")).strip()),
            "fingerprint": p_fingerprint,
            "matching_child_count": matching_child_count
        })
        
    for r_idx, c in children:
        url = str(c.get("canonical_post_url", ""))
        ident = extract_source_post_identity(url)
        
        ident_hash = ""
        if ident.confidence == "HIGH" and ident.stable_post_id:
            ident_hash = sha256_text(f"{ident.platform}:{ident.identity_kind}:{ident.stable_post_id}")
            
        cid = str(c.get("source_post_media_id", ""))
        cid_hash = sha256_text(cid) if cid else ""
        if cid_hash:
            child_id_hashes.add(cid_hash)
            
        c_clone = dict(c)
        for k in ["created_at", "updated_at", "canonical_post_url", "source_post_media_id", "id", "row_hash"]:
            c_clone.pop(k, None)
        c_clone["_computed_ident_hash"] = ident_hash
        
        for mk in ["media_url", "original_media_url", "video_url"]:
            if mk in c_clone:
                c_clone[mk] = strip_query_and_temp_signatures(str(c_clone[mk]))
                
        c_fingerprint = sha256_text(json.dumps(c_clone, sort_keys=True))
        child_fingerprint_hashes.add(c_fingerprint)
        
        raw_children.append({
            "child_number": len(raw_children) + 1,
            "sheet_row_number": r_idx,
            "ident_hash": ident_hash,
            "identity_extracted": ident.confidence == "HIGH",
            "cid_hash": cid_hash,
            "media_index": safe_int(c.get("media_index", "") if str(c.get("media_index", "")) else "-1", -1),
            "media_type": str(c.get("media_type", "")),
            "fingerprint": c_fingerprint
        })
        
    def create_group_map(hashes, prefix):
        return {h: f"{prefix}_{i+1}" for i, h in enumerate(sorted(list(hashes)))}
        
    post_identity_map = create_group_map(combined_post_identity_hashes, "POST_GROUP")
    parent_fingerprint_map = create_group_map(parent_fingerprint_hashes, "PARENT_GROUP")
    child_id_map = create_group_map(child_id_hashes, "CHILD_ID_GROUP")
    child_fingerprint_map = create_group_map(child_fingerprint_hashes, "CHILD_ROW_GROUP")
    
    final_parents = []
    parent_identity_groups = set()
    for p in raw_parents:
        pg = post_identity_map.get(p["ident_hash"], "UNRESOLVED")
        p["post_identity_group"] = pg
        if pg != "UNRESOLVED":
            parent_identity_groups.add(pg)
        p["stable_parent_fingerprint_group"] = parent_fingerprint_map.get(p["fingerprint"], "UNRESOLVED")
        del p["ident_hash"]
        del p["fingerprint"]
        final_parents.append(p)
        
    final_children = []
    child_identity_groups = set()
    for c in raw_children:
        pg = post_identity_map.get(c["ident_hash"], "UNRESOLVED")
        c["post_identity_group"] = pg
        if pg != "UNRESOLVED":
            child_identity_groups.add(pg)
        c["child_id_group"] = child_id_map.get(c["cid_hash"], "UNRESOLVED")
        c["stable_child_fingerprint_group"] = child_fingerprint_map.get(c["fingerprint"], "UNRESOLVED")
        del c["ident_hash"]
        del c["cid_hash"]
        del c["fingerprint"]
        final_children.append(c)

    unique_parent_post_identity_group_count = len(parent_post_identity_hashes)
    unique_child_post_identity_group_count = len(child_post_identity_hashes)
    unique_post_identity_group_count = len(combined_post_identity_hashes)
    
    unique_child_id_group_count = len(child_id_hashes)
    unique_parent_fingerprint_group_count = len(parent_fingerprint_hashes)
    unique_child_fingerprint_group_count = len(child_fingerprint_hashes)
    
    classification = "UNRESOLVED_IDENTITY"
    recommended_next_action = "MANUAL_INVESTIGATION"
    
    # Validation checks
    unresolved = False
    
    if len(final_parents) == 0:
        unresolved = True
        status_reasons.append("NO_PARENT_ROWS")
    elif len(final_parents) == 1:
        unresolved = True
        status_reasons.append("NOT_ENOUGH_PARENT_ROWS")
        
    if len(final_children) == 0:
        unresolved = True
        status_reasons.append("NO_CHILD_ROWS")
        
    if any(not p["identity_extracted"] for p in final_parents):
        unresolved = True
        status_reasons.append("PARENT_IDENTITY_UNRESOLVED")
        
    if any(not c["identity_extracted"] for c in final_children):
        unresolved = True
        status_reasons.append("CHILD_IDENTITY_UNRESOLVED")
        
    if any(c["post_identity_group"] not in parent_identity_groups for c in final_children if c["identity_extracted"]):
        unresolved = True
        status_reasons.append("CHILD_WITHOUT_PARENT_IDENTITY")
        
    if any(p["post_identity_group"] not in child_identity_groups for p in final_parents if p["identity_extracted"]):
        unresolved = True
        status_reasons.append("PARENT_WITHOUT_CHILD")

    for pg in parent_identity_groups:
        pg_parents = [p for p in final_parents if p["post_identity_group"] == pg]
        pg_children = [c for c in final_children if c["post_identity_group"] == pg]
        
        sum_declared = sum(p["declared_media_count"] for p in pg_parents)
        if sum_declared != len(pg_children):
            unresolved = True
            if "DECLARED_MEDIA_COUNT_MISMATCH" not in status_reasons:
                status_reasons.append("DECLARED_MEDIA_COUNT_MISMATCH")
                
        media_indices = [c["media_index"] for c in pg_children]
        if any(idx < 0 for idx in media_indices):
            unresolved = True
            if "MEDIA_INDEX_LAYOUT_MISMATCH" not in status_reasons:
                status_reasons.append("MEDIA_INDEX_LAYOUT_MISMATCH")
                
        # Media index configuration must be exactly 0 to N-1 for each parent
        for p in pg_parents:
            dmc = p["declared_media_count"]
            expected_indices = list(range(dmc)) * len(pg_parents)
            if sorted(media_indices) != sorted(expected_indices):
                unresolved = True
                if "MEDIA_INDEX_LAYOUT_MISMATCH" not in status_reasons:
                    status_reasons.append("MEDIA_INDEX_LAYOUT_MISMATCH")

    if not unresolved:
        if unique_parent_post_identity_group_count == 1:
            # SAME_POST_REINGESTED
            pg_parents = final_parents
            pg_children = final_children
            dmcs = set(p["declared_media_count"] for p in pg_parents)
            
            if len(dmcs) == 1 and unique_parent_fingerprint_group_count == 1:
                dmc = list(dmcs)[0]
                if dmc > 0 and len(pg_children) == len(pg_parents) * dmc:
                    # check stable child fingerprint is 1 per media index
                    fingerprints_by_index = defaultdict(set)
                    for c in pg_children:
                        fingerprints_by_index[c["media_index"]].add(c["stable_child_fingerprint_group"])
                        
                    if all(len(s) == 1 for s in fingerprints_by_index.values()):
                        # check counts
                        counts = defaultdict(int)
                        for c in pg_children:
                            counts[c["stable_child_fingerprint_group"]] += 1
                        if all(v == len(pg_parents) for v in counts.values()):
                            classification = "SAME_POST_REINGESTED"
                            recommended_next_action = "PLAN_DEDUPLICATION"
                            
        elif unique_parent_post_identity_group_count >= 2:
            classification = "DISTINCT_POSTS_COLLIDED"
            recommended_next_action = "PLAN_REKEY_MIGRATION"

    if classification == "UNRESOLVED_IDENTITY":
        recommended_next_action = "MANUAL_INVESTIGATION"

    return {
        "schema_version": 1,
        "mode": "READ_ONLY_SOURCE_IDENTITY_COLLISION_INSPECTION",
        "overall_status": "READY_FOR_MANUAL_DECISION",
        "classification": classification,
        "status_reasons": sorted(status_reasons),
        "checked_commit_sha": implementation_head,
        "parent_count": len(final_parents),
        "child_count": len(final_children),
        "unique_parent_post_identity_group_count": unique_parent_post_identity_group_count,
        "unique_child_post_identity_group_count": unique_child_post_identity_group_count,
        "unique_post_identity_group_count": unique_post_identity_group_count,
        "unique_child_id_group_count": unique_child_id_group_count,
        "unique_parent_fingerprint_group_count": unique_parent_fingerprint_group_count,
        "unique_child_fingerprint_group_count": unique_child_fingerprint_group_count,
        "parents": final_parents,
        "children": final_children,
        "recommended_next_action": recommended_next_action,
        "apply_operations": []
    }

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
        print(f"WP3C3_SAFE_IDENTITY_INSPECTION_JSON={json.dumps(rep, ensure_ascii=False)}")
        sys.exit(1)

    try:
        from config_loader import get_config
        from sheets_client import SheetsClient
        
        cfg = get_config()
        client = SheetsClient(cfg.get("sheet_id", ""), cfg.get("sa_dict", {}), dry_run=True)
        prevent_writes(client)
    except Exception:
        rep = build_failure_report("UNEXPECTED_EXCEPTION", implementation_head=head, origin_main=origin_main)
        with open(args.output, "w") as f:
            json.dump(rep, f, indent=2, ensure_ascii=False)
        print(f"WP3C3_SAFE_IDENTITY_INSPECTION_JSON={json.dumps(rep, ensure_ascii=False)}")
        sys.exit(1)

    try:
        ws_posts = client._ws("source_posts")
        prevent_writes(ws_posts)
        source_posts_rows = read_rows_with_sheet_numbers(ws_posts)
        
        ws_media = client._ws("source_post_media")
        prevent_writes(ws_media)
        source_post_media_rows = read_rows_with_sheet_numbers(ws_media)
    except Exception:
        rep = build_failure_report("READ_ERROR", implementation_head=head, origin_main=origin_main)
        with open(args.output, "w") as f:
            json.dump(rep, f, indent=2, ensure_ascii=False)
        print(f"WP3C3_SAFE_IDENTITY_INSPECTION_JSON={json.dumps(rep, ensure_ascii=False)}")
        sys.exit(1)

    rep = inspect_wp3c3(source_posts_rows, source_post_media_rows, head, origin_main)
    
    with open(args.output, "w") as f:
        json.dump(rep, f, indent=2, ensure_ascii=False)
    print(f"WP3C3_SAFE_IDENTITY_INSPECTION_JSON={json.dumps(rep, ensure_ascii=False)}")
    
    if rep["overall_status"] == "FAIL":
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()
