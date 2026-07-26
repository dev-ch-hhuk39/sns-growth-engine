import os
import json
import hashlib
from typing import Any
import argparse

from src.sheets_client import SheetsClient
from src.url_shape_diagnostics import parse_url_shape, normalize_url_for_safe_grouping
from scripts.inspect_wp3c3_source_identity_collision import (
    TARGET_SOURCE_POST_ID,
    prevent_writes,
    check_safety_flags,
    read_rows_with_sheet_numbers
)

def safe_hash(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()

def get_parent_semantic_group(row: dict[str, Any], recovered_ident) -> str:
    parts = []
    if recovered_ident and recovered_ident.confidence != "NONE":
        parts.append(recovered_ident.stable_post_id)
    else:
        parts.append("NONE")
    parts.append(str(row.get("media_count", "")))
    parts.append(str(row.get("platform", "")))
    parts.append(str(row.get("source_type", "")))
    parts.append(str(row.get("content_type", "")))
    
    return "SEM_PARENT_" + safe_hash("|".join(parts))

def get_child_semantic_group(row: dict[str, Any], recovered_ident) -> str:
    parts = []
    if recovered_ident and recovered_ident.confidence != "NONE":
        parts.append(recovered_ident.stable_post_id)
    else:
        parts.append("NONE")
        
    parts.append(str(row.get("media_index", "")))
    
    media_type = str(row.get("media_type", "")).strip().lower()
    if media_type not in ("image", "video", "audio", "carousel"):
        media_type = "unknown"
    parts.append(media_type)
    
    url = str(row.get("original_media_url", "")).strip()
    norm = normalize_url_for_safe_grouping(url)
    parts.append(norm)
    
    parts.append(str(row.get("width", "")))
    parts.append(str(row.get("height", "")))
    parts.append(str(row.get("duration", "")))
    
    return "SEM_CHILD_" + safe_hash("|".join(parts))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    check_safety_flags()

    client = SheetsClient()
    prevent_writes(client)

    source_posts_ws = client.get_worksheet("source_posts")
    source_post_media_ws = client.get_worksheet("source_post_media")

    source_posts_rows = read_rows_with_sheet_numbers(source_posts_ws)
    source_post_media_rows = read_rows_with_sheet_numbers(source_post_media_ws)

    parents = [r for r in source_posts_rows if str(r[1].get("source_post_id", "")) == TARGET_SOURCE_POST_ID]
    children = [r for r in source_post_media_rows if str(r[1].get("source_post_id", "")) == TARGET_SOURCE_POST_ID]

    # Process Parents
    safe_parents = []
    for idx, (sheet_row, row) in enumerate(parents):
        url = str(row.get("canonical_post_url", ""))
        shape = parse_url_shape(url)
        
        parts = []
        parts.append(shape.recovered_stable_post_id if shape.recovered_stable_post_id else "NONE")
        parts.append(str(row.get("media_count", "")))
        parts.append(str(row.get("platform", "")))
        parts.append(str(row.get("source_type", "")))
        parts.append(str(row.get("content_type", "")))
        sem_group = "SEM_PARENT_" + safe_hash("|".join(parts))
        
        rec_post_group = "RECOVERED_GROUP_" + safe_hash(shape.recovered_stable_post_id) if shape.recovered_stable_post_id else "UNRESOLVED"
        
        safe_parents.append({
            "candidate_number": idx + 1,
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
            "recovered_post_group": rec_post_group,
            "normalized_url_group": normalize_url_for_safe_grouping(url) if url.strip() else "EMPTY",
            "semantic_parent_group": sem_group,
            "declared_media_count": str(row.get("media_count", "")).strip(),
            "matching_recovered_child_count": 0,
            "_recovered_ident_str": shape.recovered_stable_post_id
        })

    # Process Children
    safe_children = []
    for idx, (sheet_row, row) in enumerate(children):
        url = str(row.get("canonical_post_url", ""))
        shape = parse_url_shape(url)
        
        parts = []
        parts.append(shape.recovered_stable_post_id if shape.recovered_stable_post_id else "NONE")
        parts.append(str(row.get("media_index", "")))
        media_type = str(row.get("media_type", "")).strip().lower()
        if media_type not in ("image", "video", "audio", "carousel"):
            media_type = "unknown"
        parts.append(media_type)
        parts.append(normalize_url_for_safe_grouping(str(row.get("original_media_url", "")).strip()))
        parts.append(str(row.get("width", "")))
        parts.append(str(row.get("height", "")))
        parts.append(str(row.get("duration", "")))
        sem_group = "SEM_CHILD_" + safe_hash("|".join(parts))

        rec_post_group = "RECOVERED_GROUP_" + safe_hash(shape.recovered_stable_post_id) if shape.recovered_stable_post_id else "UNRESOLVED"
        
        safe_children.append({
            "child_number": idx + 1,
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
            "recovered_post_group": rec_post_group,
            "normalized_url_group": normalize_url_for_safe_grouping(url) if url.strip() else "EMPTY",
            "child_id_group": "CHILD_ID_GROUP_" + safe_hash(str(row.get("source_post_media_id", ""))),
            "semantic_child_group": sem_group,
            "media_index": str(row.get("media_index", "")).strip(),
            "media_type": media_type,
            "_recovered_ident_str": shape.recovered_stable_post_id
        })

    # Update matching counts
    for p in safe_parents:
        p_id = p["_recovered_ident_str"]
        if p_id:
            count = sum(1 for c in safe_children if c["_recovered_ident_str"] == p_id)
            p["matching_recovered_child_count"] = count

    # Classification
    all_parents_recovered = all(p["recovered_identity_extracted"] for p in safe_parents)
    all_children_recovered = all(c["recovered_identity_extracted"] for c in safe_children)
    unique_parent_groups = set(p["recovered_post_group"] for p in safe_parents if p["recovered_post_group"] != "UNRESOLVED")
    
    classification = "MIXED_OR_UNRESOLVED"
    next_action = "MANUAL_INVESTIGATION"

    if len(safe_parents) >= 2 and all_parents_recovered and all_children_recovered:
        if len(unique_parent_groups) == 1:
            child_groups = set(c["recovered_post_group"] for c in safe_children)
            if len(child_groups) == 1 and child_groups.pop() == list(unique_parent_groups)[0]:
                sem_parents = set(p["semantic_parent_group"] for p in safe_parents)
                if len(sem_parents) == 1:
                    # check media index consistency (one sem group per index)
                    index_to_sem = {}
                    consistent = True
                    for c in safe_children:
                        idx_val = c["media_index"]
                        if idx_val in index_to_sem and index_to_sem[idx_val] != c["semantic_child_group"]:
                            consistent = False
                            break
                        index_to_sem[idx_val] = c["semantic_child_group"]
                    if consistent:
                        classification = "RECOVERABLE_SAME_POST"
                        next_action = "PLAN_DEDUPLICATION_INSPECTION"
        elif len(unique_parent_groups) >= 2:
            # RECOVERABLE_DISTINCT_POSTS
            has_missing_child = False
            for group in unique_parent_groups:
                if not any(c["recovered_post_group"] == group for c in safe_children):
                    has_missing_child = True
                    break
            if not has_missing_child:
                classification = "RECOVERABLE_DISTINCT_POSTS"
                next_action = "PLAN_REKEY_MIGRATION_INSPECTION"
                
    if classification == "MIXED_OR_UNRESOLVED":
        # Check ACCOUNT_OR_CHANNEL_URLS
        if len(safe_parents) > 0 and all(p["path_family"] in ("CHANNEL", "USER", "HANDLE", "PLAYLIST") for p in safe_parents) and not all_parents_recovered:
            classification = "ACCOUNT_OR_CHANNEL_URLS"
            next_action = "TRACE_ID_GENERATION"
        elif len(safe_parents) > 0 and any(p["recovery_method"] in ("NESTED_QUERY_URL", "PERCENT_DECODED_URL") for p in safe_parents) and not all_parents_recovered:
            classification = "WRAPPED_OR_ENCODED_URLS"
            next_action = "EXTEND_LOCAL_PARSER"
        elif len(safe_parents) > 0 and all(p["host_family"] == "NONE" and p["path_family"] == "OTHER" for p in safe_parents):
            classification = "PLACEHOLDER_OR_NONPUBLIC_URLS"
            next_action = "TRACE_DATA_ORIGIN"

    for x in safe_parents: del x["_recovered_ident_str"]
    for x in safe_children: del x["_recovered_ident_str"]

    out = {
        "schema_version": 1,
        "mode": "READ_ONLY_SAFE_URL_SHAPE_DIAGNOSTICS",
        "overall_status": "READY_FOR_MANUAL_DECISION",
        "classification": classification,
        "status_reasons": [],
        "checked_commit_sha": os.environ.get("GITHUB_SHA", "unknown_local"),
        "parent_count": len(safe_parents),
        "child_count": len(safe_children),
        "unique_parent_recovered_group_count": len(unique_parent_groups),
        "parents": safe_parents,
        "children": safe_children,
        "recommended_next_action": next_action,
        "apply_operations": []
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(out, f)

if __name__ == "__main__":
    main()
