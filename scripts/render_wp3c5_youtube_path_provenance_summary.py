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

REQUIRED_TOP_LEVEL_KEYS = {
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
}

REQUIRED_COUNTS_KEYS = {
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
}

REQUIRED_STATIC_TRACE_KEYS = {
    "current_parent_id_uses_source_and_external_id",
    "current_child_id_uses_parent_and_media_index",
    "current_discovery_rejects_nonpost_youtube_urls",
    "current_discovery_handles_channel_landing_pages",
    "candidate_historical_writer_count",
    "candidate_historical_writer_labels",
}

REQUIRED_PARENT_KEYS = {
    "candidate_number", "sheet_row_number", "external_post_id_group",
    "source_id_group", "source_account_id_group", "canonical_url_group",
    "discovered_at_group", "created_at_group", "semantic_parent_group",
    "path_shape", "tab_kind", "post_kind", "media_count",
    "input_state", "host_family", "path_segment_count", "has_query",
    "allowed_query_key_flags", "has_fragment", "post_identity_extracted"
}

REQUIRED_CHILD_KEYS = {
    "child_number", "sheet_row_number", "child_id_group",
    "canonical_url_group", "original_media_url_group", "created_at_group",
    "semantic_child_group", "path_shape", "tab_kind", "post_kind",
    "media_index", "media_type", "acquisition_method_family",
    "input_state", "host_family", "path_segment_count", "has_query",
    "allowed_query_key_flags", "has_fragment", "post_identity_extracted"
}

def validate_group_name(val: str, prefix: str, allowed_empty: tuple = ()) -> None:
    if val in allowed_empty:
        return
    if not isinstance(val, str) or not re.match(r"^" + prefix + r"_[1-9][0-9]*$", val):
        raise ValueError(f"Invalid group name: {val}")

def validate_no_secrets_or_urls_recursive(data: Any) -> None:
    if isinstance(data, dict):
        for k, v in data.items():
            if k == "checked_commit_sha":
                continue
            if k == "candidate_historical_writer_labels":
                if not isinstance(v, list):
                    raise ValueError("candidate_historical_writer_labels must be list")
                for path in v:
                    if not isinstance(path, str):
                        raise ValueError("path must be str")
                    if not (path.startswith("src/") or path.startswith("scripts/")):
                        raise ValueError("path must start with src/ or scripts/")
                    if ".." in path or path.startswith("/"):
                        raise ValueError("path must be relative and safe")
                continue
            validate_no_secrets_or_urls_recursive(v)
    elif isinstance(data, list):
        for item in data:
            validate_no_secrets_or_urls_recursive(item)
    elif isinstance(data, str):
        v_low = data.lower()
        if "http://" in v_low or "https://" in v_low:
            raise ValueError("URL found")
        if re.search(r"^[0-9a-f]{40}$", v_low) or re.search(r"^[0-9a-f]{64}$", v_low):
            if not v_low.startswith("ext_post_id_group_"):
                raise ValueError("Hex string found")
        if "token" in v_low or "secret" in v_low or "credential" in v_low or "service account" in v_low or "spreadsheet" in v_low:
            if data not in ("secret", "token"): # Just in case it's part of a safe string
                pass
            raise ValueError("Sensitive keyword found")
        if "traceback" in v_low or "line " in v_low and "in <module>" in v_low:
            raise ValueError("Traceback found")

def validate_contract(data: dict, exit_code: int) -> None:
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object")

    if set(data.keys()) != REQUIRED_TOP_LEVEL_KEYS:
        raise ValueError("Root keys mismatch")
    
    if not is_plain_int(data["schema_version"]) or data["schema_version"] != 1:
        raise ValueError("schema_version must be 1")
        
    if data["mode"] != "READ_ONLY_SAFE_YOUTUBE_PATH_PROVENANCE":
        raise ValueError("Invalid mode")
        
    if data["overall_status"] not in ["READY_FOR_MANUAL_DECISION", "FAIL"]:
        raise ValueError("Invalid overall_status")

    if not re.match(r"^[0-9a-f]{40}$", data["checked_commit_sha"]):
        raise ValueError("checked_commit_sha must be 40 char hex")

    if not isinstance(data["status_reasons"], list):
        raise ValueError("status_reasons must be list")
        
    if not isinstance(data["apply_operations"], list) or len(data["apply_operations"]) > 0:
        raise ValueError("apply_operations must be empty list")

    if set(data["counts"].keys()) != REQUIRED_COUNTS_KEYS:
        raise ValueError("Counts keys mismatch")
        
    if set(data["static_trace"].keys()) != REQUIRED_STATIC_TRACE_KEYS:
        raise ValueError("Static trace keys mismatch")
        
    for k, v in data["counts"].items():
        if not is_plain_int(v) or v < 0:
            raise ValueError(f"Count {k} must be >= 0")
            
    for k in ["current_parent_id_uses_source_and_external_id", "current_child_id_uses_parent_and_media_index", "current_discovery_rejects_nonpost_youtube_urls", "current_discovery_handles_channel_landing_pages"]:
        if type(data["static_trace"][k]) is not bool:
            raise ValueError(f"{k} must be bool")
            
    if not is_plain_int(data["static_trace"]["candidate_historical_writer_count"]):
        raise ValueError("candidate_historical_writer_count must be int")
        
    if len(data["static_trace"]["candidate_historical_writer_labels"]) != data["static_trace"]["candidate_historical_writer_count"]:
        raise ValueError("writer count mismatch")

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

    if not isinstance(data["parents"], list):
        raise ValueError("parents must be list")
    if not isinstance(data["children"], list):
        raise ValueError("children must be list")
        
    if data["counts"]["parent_count"] != len(data["parents"]):
        raise ValueError("parent count mismatch")
    if data["counts"]["child_count"] != len(data["children"]):
        raise ValueError("child count mismatch")

    unique_parent_canon = set()
    unique_child_canon = set()
    unique_ext = set()
    unique_src = set()
    unique_child_id = set()
    unique_media_url = set()
    
    for idx, p in enumerate(data["parents"], start=1):
        if set(p.keys()) != REQUIRED_PARENT_KEYS:
            raise ValueError("Parent keys mismatch")
        if not is_plain_int(p["candidate_number"]) or p["candidate_number"] != idx:
            raise ValueError("Invalid candidate_number")
        if not is_plain_int(p["sheet_row_number"]) or p["sheet_row_number"] < 1:
            raise ValueError("Invalid sheet_row_number")
        if not is_plain_int(p["media_count"]) or p["media_count"] < 0:
            raise ValueError("Invalid media_count")
            
        validate_group_name(p["external_post_id_group"], "EXT_POST_ID_GROUP")
        validate_group_name(p["source_id_group"], "SOURCE_ID_GROUP")
        validate_group_name(p["source_account_id_group"], "SOURCE_ACCOUNT_ID_GROUP")
        validate_group_name(p["canonical_url_group"], "CANON_URL_GROUP")
        validate_group_name(p["semantic_parent_group"], "SEM_PARENT_GROUP")
        
        unique_parent_canon.add(p["canonical_url_group"])
        unique_ext.add(p["external_post_id_group"])
        unique_src.add(p["source_id_group"])

    for idx, c in enumerate(data["children"], start=1):
        if set(c.keys()) != REQUIRED_CHILD_KEYS:
            raise ValueError("Child keys mismatch")
        if not is_plain_int(c["child_number"]) or c["child_number"] != idx:
            raise ValueError("Invalid child_number")
        if not is_plain_int(c["sheet_row_number"]) or c["sheet_row_number"] < 1:
            raise ValueError("Invalid sheet_row_number")
        if not is_plain_int(c["media_index"]) or c["media_index"] < 0:
            raise ValueError("Invalid media_index")
            
        validate_group_name(c["child_id_group"], "CHILD_ID_GROUP")
        validate_group_name(c["canonical_url_group"], "CANON_URL_GROUP")
        validate_group_name(c["original_media_url_group"], "MEDIA_URL_GROUP")
        validate_group_name(c["semantic_child_group"], "SEM_CHILD_GROUP")
        
        unique_child_canon.add(c["canonical_url_group"])
        unique_child_id.add(c["child_id_group"])
        unique_media_url.add(c["original_media_url_group"])

    if data["counts"]["unique_parent_canonical_url_group_count"] != len(unique_parent_canon):
        raise ValueError("unique_parent_canonical_url_group_count mismatch")
    if data["counts"]["unique_child_canonical_url_group_count"] != len(unique_child_canon):
        raise ValueError("unique_child_canonical_url_group_count mismatch")
    if data["counts"]["unique_external_post_id_group_count"] != len(unique_ext):
        raise ValueError("unique_external_post_id_group_count mismatch")
    if data["counts"]["unique_source_id_group_count"] != len(unique_src):
        raise ValueError("unique_source_id_group_count mismatch")
    if data["counts"]["unique_child_id_group_count"] != len(unique_child_id):
        raise ValueError("unique_child_id_group_count mismatch")
    if data["counts"]["unique_child_original_media_url_group_count"] != len(unique_media_url):
        raise ValueError("unique_child_original_media_url_group_count mismatch")

    validate_no_secrets_or_urls_recursive(data)

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-file", required=True)
    parser.add_argument("--exit-code", type=int, required=True)
    args = parser.parse_args()

    try:
        with open(args.json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        print("WP3-C5 summary renderer failed: ValueError", file=sys.stderr)
        sys.exit(1)

    try:
        validate_contract(data, args.exit_code)
    except Exception:
        print("WP3-C5 summary renderer failed: ValueError", file=sys.stderr)
        sys.exit(1)
        
    print("WP3-C5 SUMMARY")
    sys.exit(args.exit_code)

if __name__ == "__main__":
    main()
