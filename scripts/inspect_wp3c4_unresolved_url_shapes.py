import os
import json
import sys
import hashlib
import re
from typing import Any
import argparse

from src.sheets_client import SheetsClient
from src.url_shape_diagnostics import (
    parse_url_shape, 
    normalize_url_for_safe_grouping,
    normalize_media_url_for_fingerprint
)
from scripts.inspect_wp3c3_source_identity_collision import (
    TARGET_SOURCE_POST_ID,
    prevent_writes,
    check_safety_flags,
    read_rows_with_sheet_numbers,
    parse_non_negative_integer,
    normalize_media_type
)

def _safe_hash(val: str) -> str:
    return hashlib.sha256(val.encode("utf-8")).hexdigest()

def get_ident_hash(shape) -> str:
    if shape and shape.recovered_stable_post_id:
        return _safe_hash(f"{shape.recovered_platform}:{shape.recovered_identity_kind}:{shape.recovered_stable_post_id}")
    return "NONE"

def get_parent_sem_hash(row: dict[str, Any], shape) -> str:
    parts = []
    parts.append(get_ident_hash(shape))
    acct = str(row.get("account_id", "")).strip() or str(row.get("target_account_id", "")).strip()
    parts.append(_safe_hash(acct) if acct else "NONE")
    parts.append(str(row.get("media_count", "")).strip())
    parts.append(str(row.get("platform", "")).strip())
    parts.append(str(row.get("source_type", "")).strip())
    parts.append(str(row.get("content_type", "")).strip())
    return _safe_hash("|".join(parts))

def get_child_sem_hash(row: dict[str, Any], shape) -> str:
    parts = []
    parts.append(get_ident_hash(shape))
    parts.append(str(row.get("media_index", "")).strip())
    parts.append(normalize_media_type(row.get("media_type")))
    media_url = str(row.get("original_media_url", "")).strip()
    parts.append(normalize_media_url_for_fingerprint(media_url) if media_url else "NONE")
    parts.append(str(row.get("width", "")).strip())
    parts.append(str(row.get("height", "")).strip())
    parts.append(str(row.get("duration", "")).strip())
    return _safe_hash("|".join(parts))

def create_mapping(prefix: str, hashes: set[str]) -> dict[str, str]:
    sorted_hashes = sorted(list(h for h in hashes if h and h != "UNRESOLVED" and h != "NONE"))
    mapping = {h: f"{prefix}_{i+1}" for i, h in enumerate(sorted_hashes)}
    mapping["UNRESOLVED"] = "UNRESOLVED"
    mapping["NONE"] = "NONE"
    return mapping

def generate_fail_report(reason: str, output_file: str = None):
    sha = os.environ.get("GITHUB_SHA", "unknown_local")
    if len(sha) != 40 or not re.match(r"^[0-9a-f]{40}$", sha):
        sha = "0000000000000000000000000000000000000000"
    out = {
        "schema_version": 1,
        "mode": "READ_ONLY_SAFE_URL_SHAPE_DIAGNOSTICS",
        "overall_status": "FAIL",
        "classification": "MIXED_OR_UNRESOLVED",
        "status_reasons": [reason],
        "checked_commit_sha": sha,
        "parent_count": 0,
        "child_count": 0,
        "unique_parent_recovered_group_count": 0,
        "unique_child_recovered_group_count": 0,
        "unique_normalized_url_group_count": 0,
        "unique_semantic_parent_group_count": 0,
        "unique_semantic_child_group_count": 0,
        "parents": [],
        "children": [],
        "recommended_next_action": "MANUAL_INVESTIGATION",
        "apply_operations": []
    }
    j = json.dumps(out, separators=(',', ':'))
    if output_file:
        with open(output_file, 'w') as f:
            f.write(j)
    print(f"WP3C4_SAFE_URL_SHAPE_DIAGNOSTICS_JSON={j}")
    sys.exit(1)

import argparse
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        if check_safety_flags():
            generate_fail_report("UNSAFE_FLAG_ENABLED", args.output)

        client = SheetsClient()
        prevent_writes(client)

        source_posts_ws = client.get_worksheet("source_posts")
        source_post_media_ws = client.get_worksheet("source_post_media")

        source_posts_rows = read_rows_with_sheet_numbers(source_posts_ws)
        source_post_media_rows = read_rows_with_sheet_numbers(source_post_media_ws)

        parents = [r for r in source_posts_rows if str(r[1].get("source_post_id", "")) == TARGET_SOURCE_POST_ID]
        children = [r for r in source_post_media_rows if str(r[1].get("source_post_id", "")) == TARGET_SOURCE_POST_ID]

        sha = os.environ.get("GITHUB_SHA", "unknown_local")
        if len(sha) != 40 or not re.match(r"^[0-9a-f]{40}$", sha):
            sha = "0000000000000000000000000000000000000000"

        raw_parents = []
        raw_children = []
        
        url_hashes = set()
        rec_hashes = set()
        sem_parent_hashes = set()
        sem_child_hashes = set()
        child_id_hashes = set()

        for sheet_row, row in parents:
            url = str(row.get("canonical_post_url", ""))
            shape = parse_url_shape(url)
            url_hash = normalize_url_for_safe_grouping(url)
            
            ident_hash = get_ident_hash(shape) if shape.direct_identity_extracted or shape.recovered_stable_post_id else "UNRESOLVED"
            sem_parent_hash = get_parent_sem_hash(row, shape if shape.recovered_stable_post_id else None)
            
            mc = parse_non_negative_integer(row.get("media_count"))
            if mc is None or mc <= 0:
                mc_valid = False
                mc_val = 0
            else:
                mc_valid = True
                mc_val = mc
                
            url_hashes.add(url_hash)
            rec_hashes.add(ident_hash)
            sem_parent_hashes.add(sem_parent_hash)
            
            raw_parents.append({
                "sheet_row_number": sheet_row,
                "input_state": shape.input_state,
                "host_family": shape.host_family,
                "path_family": shape.path_family,
                "allowed_query_key_flags": list(shape.has_allowed_query_keys),
                "has_nested_url": shape.has_nested_url,
                "decoded_layer_count": shape.decoded_layer_count,
                "direct_identity_extracted": shape.direct_identity_extracted,
                "recovery_method": shape.recovery_method,
                "recovered_identity_extracted": bool(shape.recovered_stable_post_id),
                "_ident_hash": ident_hash,
                "_url_hash": url_hash,
                "_sem_parent_hash": sem_parent_hash,
                "declared_media_count": mc_val,
                "_mc_valid": mc_valid,
                "_recovered_ident_str": shape.recovered_stable_post_id
            })

        for sheet_row, row in children:
            url = str(row.get("canonical_post_url", ""))
            shape = parse_url_shape(url)
            url_hash = normalize_url_for_safe_grouping(url)
            
            ident_hash = get_ident_hash(shape) if shape.direct_identity_extracted or shape.recovered_stable_post_id else "UNRESOLVED"
            sem_child_hash = get_child_sem_hash(row, shape if shape.recovered_stable_post_id else None)
            c_id = str(row.get("source_post_media_id", ""))
            cid_hash = _safe_hash(c_id) if c_id else "NONE"
            
            mi = parse_non_negative_integer(row.get("media_index"))
            if mi is None:
                mi_valid = False
                mi_val = 0
            else:
                mi_valid = True
                mi_val = mi
                
            url_hashes.add(url_hash)
            rec_hashes.add(ident_hash)
            sem_child_hashes.add(sem_child_hash)
            child_id_hashes.add(cid_hash)
            
            raw_children.append({
                "sheet_row_number": sheet_row,
                "input_state": shape.input_state,
                "host_family": shape.host_family,
                "path_family": shape.path_family,
                "allowed_query_key_flags": list(shape.has_allowed_query_keys),
                "has_nested_url": shape.has_nested_url,
                "decoded_layer_count": shape.decoded_layer_count,
                "direct_identity_extracted": shape.direct_identity_extracted,
                "recovery_method": shape.recovery_method,
                "recovered_identity_extracted": bool(shape.recovered_stable_post_id),
                "_ident_hash": ident_hash,
                "_url_hash": url_hash,
                "_cid_hash": cid_hash,
                "_sem_child_hash": sem_child_hash,
                "media_index": mi_val,
                "_mi_valid": mi_valid,
                "media_type": normalize_media_type(row.get("media_type")),
                "_recovered_ident_str": shape.recovered_stable_post_id
            })

        url_map = create_mapping("URL_GROUP", url_hashes)
        rec_map = create_mapping("RECOVERED_POST_GROUP", rec_hashes)
        sp_map = create_mapping("SEM_PARENT_GROUP", sem_parent_hashes)
        sc_map = create_mapping("SEM_CHILD_GROUP", sem_child_hashes)
        cid_map = create_mapping("CHILD_ID_GROUP", child_id_hashes)

        safe_parents = []
        for idx, p in enumerate(raw_parents):
            c = p.copy()
            c["candidate_number"] = idx + 1
            c["recovered_post_group"] = rec_map[p["_ident_hash"]]
            c["normalized_url_group"] = url_map[p["_url_hash"]] if p["_url_hash"] else "EMPTY"
            c["semantic_parent_group"] = sp_map[p["_sem_parent_hash"]]
            p_id = p["_ident_hash"]
            c["matching_recovered_child_count"] = sum(1 for ch in raw_children if ch["_ident_hash"] == p_id and p_id != "UNRESOLVED")
            
            for k in ["_ident_hash", "_url_hash", "_sem_parent_hash", "_mc_valid", "_recovered_ident_str"]:
                del c[k]
            safe_parents.append(c)
            
        safe_children = []
        for idx, c in enumerate(raw_children):
            cc = c.copy()
            cc["child_number"] = idx + 1
            cc["recovered_post_group"] = rec_map[c["_ident_hash"]]
            cc["normalized_url_group"] = url_map[c["_url_hash"]] if c["_url_hash"] else "EMPTY"
            cc["child_id_group"] = cid_map[c["_cid_hash"]]
            cc["semantic_child_group"] = sc_map[c["_sem_child_hash"]]
            
            for k in ["_ident_hash", "_url_hash", "_cid_hash", "_sem_child_hash", "_mi_valid", "_recovered_ident_str"]:
                del cc[k]
            safe_children.append(cc)

        all_parents_recovered = len(raw_parents) > 0 and all(p["recovered_identity_extracted"] for p in raw_parents)
        all_children_recovered = len(raw_children) > 0 and all(c["recovered_identity_extracted"] for c in raw_children)
        unique_parent_groups = set(p["recovered_post_group"] for p in safe_parents if p["recovered_post_group"] != "UNRESOLVED")
        
        classification = "MIXED_OR_UNRESOLVED"
        next_action = "MANUAL_INVESTIGATION"
        status_reasons = []

        if not raw_parents:
            status_reasons.append("NO_PARENT_ROWS")
        if not raw_children:
            status_reasons.append("NO_CHILD_ROWS")
            
        if not raw_parents or not raw_children:
            pass
        elif not all(p["_mc_valid"] for p in raw_parents):
            status_reasons.append("INVALID_PARENT_MEDIA_COUNT")
        elif not all(c["_mi_valid"] for c in raw_children):
            status_reasons.append("INVALID_CHILD_MEDIA_INDEX")
        else:
            if len(safe_parents) >= 2 and all_parents_recovered and all_children_recovered:
                if len(unique_parent_groups) == 1:
                    child_groups = set(c["recovered_post_group"] for c in safe_children)
                    if len(child_groups) == 1 and child_groups.pop() == list(unique_parent_groups)[0]:
                        sem_parents = set(p["semantic_parent_group"] for p in safe_parents)
                        if len(sem_parents) == 1:
                            N = raw_parents[0]["declared_media_count"]
                            if all(p["declared_media_count"] == N for p in raw_parents) and len(safe_children) == len(safe_parents) * N:
                                expected_indices = set(range(N))
                                actual_indices = set(c["media_index"] for c in safe_children)
                                if expected_indices == actual_indices:
                                    valid_counts = all(sum(1 for c in safe_children if c["media_index"] == i) == len(safe_parents) for i in expected_indices)
                                    if valid_counts:
                                        sem_child_valid = True
                                        for i in expected_indices:
                                            sems = set(c["semantic_child_group"] for c in safe_children if c["media_index"] == i)
                                            if len(sems) != 1 or sum(1 for c in safe_children if c["semantic_child_group"] == list(sems)[0]) != len(safe_parents):
                                                sem_child_valid = False
                                                break
                                        if sem_child_valid:
                                            classification = "RECOVERABLE_SAME_POST"
                                            next_action = "PLAN_DEDUPLICATION_INSPECTION"
                                            status_reasons.append("SAME_POST_STRUCTURE_CONFIRMED")
                elif len(unique_parent_groups) >= 2:
                    child_groups = set(c["recovered_post_group"] for c in safe_children)
                    if child_groups == unique_parent_groups:
                        from collections import Counter
                        valid_distinct = True
                        for group in unique_parent_groups:
                            group_parents = [p for p in safe_parents if p["recovered_post_group"] == group]
                            group_children = [c for c in safe_children if c["recovered_post_group"] == group]
                            
                            if not group_parents or not group_children:
                                valid_distinct = False
                                break
                                
                            expected = Counter()
                            for p in group_parents:
                                if p["declared_media_count"] <= 0:
                                    valid_distinct = False
                                    break
                                for media_index in range(p["declared_media_count"]):
                                    expected[media_index] += 1
                                    
                            if not valid_distinct:
                                break
                                
                            actual = Counter()
                            for c in group_children:
                                if c["media_index"] < 0:
                                    valid_distinct = False
                                    break
                                actual[c["media_index"]] += 1
                                
                            if not valid_distinct:
                                break
                                
                            if expected != actual:
                                valid_distinct = False
                                break
                                
                            N_total = sum(p["declared_media_count"] for p in group_parents)
                            if len(group_children) != N_total:
                                valid_distinct = False
                                break
                                
                        if valid_distinct and not any(c["recovered_post_group"] not in unique_parent_groups for c in safe_children):
                            classification = "RECOVERABLE_DISTINCT_POSTS"
                            next_action = "PLAN_REKEY_MIGRATION_INSPECTION"
                            status_reasons.append("DISTINCT_POST_STRUCTURE_CONFIRMED")

        if classification == "MIXED_OR_UNRESOLVED":
            if len(safe_parents) > 0 and sum(1 for p in safe_parents if p["path_family"] in ("CHANNEL", "USER", "HANDLE", "PLAYLIST")) > len(safe_parents) / 2 and not any(p["recovered_identity_extracted"] for p in safe_parents):
                classification = "ACCOUNT_OR_CHANNEL_URLS"
                next_action = "TRACE_ID_GENERATION"
                status_reasons.append("ACCOUNT_OR_CHANNEL_URLS_DETECTED")
            elif len(safe_parents) > 0 and any(p["has_nested_url"] or p["decoded_layer_count"] > 0 or p["recovery_method"] in ("NESTED_QUERY_URL", "PERCENT_DECODED_URL") for p in safe_parents) and not all_parents_recovered:
                classification = "WRAPPED_OR_ENCODED_URLS"
                next_action = "EXTEND_LOCAL_PARSER"
                status_reasons.append("WRAPPED_OR_ENCODED_URLS_DETECTED")
            elif len(safe_parents) > 0 and sum(1 for p in safe_parents if p["input_state"] in ("EMPTY", "MALFORMED") or p["host_family"] in ("OTHER", "NONE")) >= len(safe_parents) / 2 and not any(p["recovered_identity_extracted"] for p in safe_parents):
                classification = "PLACEHOLDER_OR_NONPUBLIC_URLS"
                next_action = "TRACE_DATA_ORIGIN"
                status_reasons.append("PLACEHOLDER_OR_NONPUBLIC_URLS_DETECTED")
                
        if not status_reasons:
            status_reasons.append("MIXED_OR_UNRESOLVED")

        out = {
            "schema_version": 1,
            "mode": "READ_ONLY_SAFE_URL_SHAPE_DIAGNOSTICS",
            "overall_status": "READY_FOR_MANUAL_DECISION",
            "classification": classification,
            "status_reasons": status_reasons,
            "checked_commit_sha": sha,
            "parent_count": len(safe_parents),
            "child_count": len(safe_children),
            "unique_parent_recovered_group_count": len(unique_parent_groups),
            "unique_child_recovered_group_count": len(set(c["recovered_post_group"] for c in safe_children if c["recovered_post_group"] != "UNRESOLVED")),
            "unique_normalized_url_group_count": len(set(p["normalized_url_group"] for p in safe_parents if p["normalized_url_group"] != "EMPTY") | set(c["normalized_url_group"] for c in safe_children if c["normalized_url_group"] != "EMPTY")),
            "unique_semantic_parent_group_count": len(set(p["semantic_parent_group"] for p in safe_parents)),
            "unique_semantic_child_group_count": len(set(c["semantic_child_group"] for c in safe_children)),
            "parents": safe_parents,
            "children": safe_children,
            "recommended_next_action": next_action,
            "apply_operations": []
        }

        j = json.dumps(out, separators=(',', ':'))
        with open(args.output, 'w') as f:
            f.write(j)
        print(f"WP3C4_SAFE_URL_SHAPE_DIAGNOSTICS_JSON={j}")
    except Exception:
        generate_fail_report("INSPECTION_FAILED", args.output)
        sys.exit(1)

if __name__ == "__main__":
    main()