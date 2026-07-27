#!/usr/bin/env python3
"""
WP3-C5: Renderer for Safe YouTube Path Provenance.
Validates the inspector's output and prints a human-readable summary.
"""
from __future__ import annotations

import argparse
import json
import sys
import re
from typing import Any

def is_plain_int(val: Any) -> bool:
    if isinstance(val, bool):
        return False
    return isinstance(val, int)

def require_keys(obj: dict, keys: list[str], context: str = "") -> None:
    missing = [k for k in keys if k not in obj]
    if missing:
        raise ValueError(f"Missing required keys in {context}: {missing}")

REQUIRED_TOP_LEVEL_KEYS = [
    "schema_version",
    "mode",
    "overall_status",
    "classification",
    "status_reasons",
    "checked_commit_sha",
    "counts",
    "static_trace",
    "parents",
    "children",
    "recommended_next_action",
    "apply_operations"
]

REQUIRED_COUNTS_KEYS = [
    "parent_count",
    "child_count",
    "unique_external_post_id_group_count",
    "unique_source_id_group_count",
    "unique_child_id_group_count",
    "unique_parent_canonical_url_group_count",
    "unique_child_canonical_url_group_count",
    "unique_child_original_media_url_group_count",
    "unique_parent_tab_kind_count",
    "unique_child_tab_kind_count",
    "parent_child_url_group_match_count",
    "parent_child_row_number_match_count",
    "unique_parent_recovered_group_count",
    "unique_child_recovered_group_count",
]

def sanitize_text(text: str) -> str:
    s = str(text)
    s = s.replace("\r", " ").replace("\n", " ")
    s = s.replace("`", "'")
    if len(s) > 200:
        s = s[:197] + "..."
    return s

def validate_group_name(val: str, prefix: str, allowed_empty: tuple = ()) -> None:
    if val in allowed_empty:
        return
    if not isinstance(val, str) or not re.match(r"^" + prefix + r"_[1-9][0-9]*$", val):
        raise ValueError(f"Invalid group name: {val}")

def validate_no_secrets_or_urls(val: Any) -> None:
    if not isinstance(val, str):
        return
    if re.search(r"http[s]?://", val) or re.search(r"[0-9a-f]{64}", val.lower()) or "token" in val.lower() or "secret" in val.lower():
        raise ValueError("Sensitive data leaked in output (URL, hash, token)")

def validate_contract(data: dict, exit_code: int) -> None:
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object")

    require_keys(data, REQUIRED_TOP_LEVEL_KEYS, "root")
    
    if not is_plain_int(data["schema_version"]) or data["schema_version"] != 1:
        raise ValueError("schema_version must be 1")
        
    if data["mode"] != "READ_ONLY_SAFE_YOUTUBE_PATH_PROVENANCE":
        raise ValueError("Invalid mode")
        
    if data["overall_status"] not in ["READY_FOR_MANUAL_DECISION", "FAIL"]:
        raise ValueError("Invalid overall_status")

    require_keys(data["counts"], REQUIRED_COUNTS_KEYS, "counts")
    
    valid_actions = {
        "HISTORICAL_CHANNEL_TAB_PSEUDO_ENTRIES": "PLAN_HISTORICAL_PSEUDO_ENTRY_REPAIR_REVIEW",
        "ACCOUNT_PAGE_COLLISION_CONFIRMED": "TRACE_HISTORICAL_WRITER",
        "NONPOST_YOUTUBE_URL_COLLISION": "TRACE_DATA_ORIGIN",
        "MIXED_OR_UNRESOLVED": "MANUAL_INVESTIGATION"
    }

    if exit_code == 0:
        if data["overall_status"] != "READY_FOR_MANUAL_DECISION":
            raise ValueError(f"Success exit but status is {data['overall_status']}")
            
        c = data["classification"]
        if c not in valid_actions:
            raise ValueError(f"Invalid classification: {c}")
            
        if data["recommended_next_action"] != valid_actions[c]:
            raise ValueError(f"Mismatched recommended_next_action for {c}")
    else:
        if data["overall_status"] != "FAIL":
            raise ValueError("Non-zero exit but status not FAIL")
        if data["classification"] != "MIXED_OR_UNRESOLVED":
            raise ValueError("Failure classification must be MIXED_OR_UNRESOLVED")

    # Validate parents
    for p in data["parents"]:
        require_keys(p, [
            "candidate_number", "sheet_row_number", "external_post_id_group",
            "source_id_group", "source_account_id_group", "canonical_url_group",
            "discovered_at_group", "created_at_group", "semantic_parent_group",
            "path_shape", "tab_kind", "post_kind", "media_count"
        ], "parent")
        validate_group_name(p["external_post_id_group"], "EXT_POST_ID_GROUP")
        validate_group_name(p["source_id_group"], "SOURCE_ID_GROUP")
        validate_group_name(p["canonical_url_group"], "PARENT_CANON_URL_GROUP")
        validate_group_name(p["semantic_parent_group"], "SEM_PARENT_GROUP")
        
        for k, v in p.items():
            validate_no_secrets_or_urls(v)

    # Validate children
    for c in data["children"]:
        require_keys(c, [
            "child_number", "sheet_row_number", "child_id_group",
            "canonical_url_group", "original_media_url_group", "created_at_group",
            "semantic_child_group", "path_shape", "tab_kind", "post_kind",
            "media_index", "media_type", "acquisition_method_family"
        ], "child")
        validate_group_name(c["child_id_group"], "CHILD_ID_GROUP")
        validate_group_name(c["canonical_url_group"], "CHILD_CANON_URL_GROUP")
        validate_group_name(c["original_media_url_group"], "MEDIA_URL_GROUP")
        validate_group_name(c["semantic_child_group"], "SEM_CHILD_GROUP")
        
        for k, v in c.items():
            validate_no_secrets_or_urls(v)

def print_summary(data: dict) -> None:
    print("\n" + "="*60)
    print("WP3-C5 YouTube Path Provenance Summary")
    print("="*60)
    print(f"Status:             {data['overall_status']}")
    print(f"Classification:     {data['classification']}")
    print(f"Next Action:        {data['recommended_next_action']}")
    if data['status_reasons']:
        print(f"Reasons:            {', '.join(data['status_reasons'])}")
    print(f"Checked SHA:        {data['checked_commit_sha']}")
    
    print("\n--- Counts ---")
    counts = data["counts"]
    print(f"Parent Rows: {counts['parent_count']}")
    print(f"Child Rows:  {counts['child_count']}")
    print(f"Unique Ext Post ID Groups: {counts['unique_external_post_id_group_count']}")
    print(f"Unique Source ID Groups:   {counts['unique_source_id_group_count']}")
    print(f"Unique Child ID Groups:    {counts['unique_child_id_group_count']}")
    print(f"Unique Media URL Groups:   {counts['unique_child_original_media_url_group_count']}")
    print(f"Match (Parent/Child URL):  {counts['parent_child_url_group_match_count']}")
    print(f"Match (Parent/Child Row):  {counts['parent_child_row_number_match_count']}")
    
    print("\n--- Static Trace ---")
    trace = data.get("static_trace", {})
    for k, v in trace.items():
        if isinstance(v, list):
            print(f"{k}:")
            for item in v:
                print(f"  - {item}")
        else:
            print(f"{k}: {v}")
            
    print("\n--- Parents ---")
    for p in data["parents"]:
        print(f"Candidate #{p['candidate_number']} (Row {p['sheet_row_number']})")
        print(f"  Ext ID Grp: {p['external_post_id_group']}")
        print(f"  Src ID Grp: {p['source_id_group']}")
        print(f"  Sem Grp:    {p['semantic_parent_group']}")
        print(f"  Path Shape: {p['path_shape']}")
        print(f"  Tab Kind:   {p['tab_kind']}")
        
    print("\n--- Children ---")
    for c in data["children"]:
        print(f"Child #{c['child_number']} (Row {c['sheet_row_number']})")
        print(f"  Child ID Grp: {c['child_id_group']}")
        print(f"  Sem Grp:      {c['semantic_child_group']}")
        print(f"  Path Shape:   {c['path_shape']}")
        print(f"  Tab Kind:     {c['tab_kind']}")
        print(f"  Media Index:  {c['media_index']} ({c['media_type']})")
        print(f"  Acquisition:  {c['acquisition_method_family']}")

    print("="*60 + "\n")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-file", required=True)
    parser.add_argument("--exit-code", type=int, required=True)
    args = parser.parse_args()

    try:
        with open(args.json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Failed to read/parse JSON: {e}")
        sys.exit(1)

    try:
        validate_contract(data, args.exit_code)
    except Exception as e:
        print(f"CONTRACT VIOLATION: {e}")
        sys.exit(1)
        
    print_summary(data)
    sys.exit(0)

if __name__ == "__main__":
    main()
