#!/usr/bin/env python3
import sys
import json
import argparse
from typing import Any

REQUIRED_TOP_LEVEL_KEYS = {
    "schema_version",
    "mode",
    "overall_status",
    "classification",
    "status_reasons",
    "checked_commit_sha",
    "parent_count",
    "child_count",
    "unique_parent_recovered_group_count",
    "parents",
    "children",
    "recommended_next_action",
    "apply_operations"
}

ALLOWED_CLASSIFICATIONS = {
    "RECOVERABLE_SAME_POST",
    "RECOVERABLE_DISTINCT_POSTS",
    "ACCOUNT_OR_CHANNEL_URLS",
    "WRAPPED_OR_ENCODED_URLS",
    "PLACEHOLDER_OR_NONPUBLIC_URLS",
    "MIXED_OR_UNRESOLVED"
}

ALLOWED_ACTIONS = {
    "PLAN_DEDUPLICATION_INSPECTION",
    "PLAN_REKEY_MIGRATION_INSPECTION",
    "TRACE_ID_GENERATION",
    "EXTEND_LOCAL_PARSER",
    "TRACE_DATA_ORIGIN",
    "MANUAL_INVESTIGATION"
}

def validate_contract(data: Any):
    if not isinstance(data, dict):
        raise ValueError("top level must be dict")
    
    missing = REQUIRED_TOP_LEVEL_KEYS - set(data.keys())
    if missing:
        raise ValueError(f"missing keys: {missing}")

    if data["schema_version"] != 1:
        raise ValueError("schema_version must be 1")
    if data["overall_status"] not in ("READY_FOR_MANUAL_DECISION", "BLOCKED", "FAIL"):
        raise ValueError("invalid overall_status")
    if data["classification"] not in ALLOWED_CLASSIFICATIONS:
        raise ValueError("invalid classification")
    if data["recommended_next_action"] not in ALLOWED_ACTIONS:
        raise ValueError("invalid recommended_next_action")
    if not isinstance(data["apply_operations"], list) or len(data["apply_operations"]) > 0:
        raise ValueError("apply_operations must be an empty list")
        
    for k in ["status_reasons", "parents", "children"]:
        if not isinstance(data[k], list):
            raise ValueError(f"{k} must be list")

    for p in data["parents"]:
        if not isinstance(p, dict):
            raise ValueError("parent must be dict")
        if not isinstance(p.get("allowed_query_key_flags"), list):
            raise ValueError("parent allowed_query_key_flags must be list")
        for key in ["has_nested_url", "direct_identity_extracted", "recovered_identity_extracted"]:
            if not isinstance(p.get(key), bool):
                raise ValueError(f"parent {key} must be bool")
        for key in ["host_family", "path_family", "recovery_method", "recovered_post_group", "normalized_url_group", "semantic_parent_group"]:
            val = p.get(key)
            if not isinstance(val, str):
                raise ValueError(f"parent {key} must be str")
            if "://" in val or "?" in val or "/" in val:
                raise ValueError(f"raw url detected in parent {key}")
                
    for c in data["children"]:
        if not isinstance(c, dict):
            raise ValueError("child must be dict")
        if not isinstance(c.get("allowed_query_key_flags"), list):
            raise ValueError("child allowed_query_key_flags must be list")
        for key in ["has_nested_url", "direct_identity_extracted", "recovered_identity_extracted"]:
            if not isinstance(c.get(key), bool):
                raise ValueError(f"child {key} must be bool")
        for key in ["host_family", "path_family", "recovery_method", "recovered_post_group", "normalized_url_group", "child_id_group", "semantic_child_group", "media_type"]:
            val = c.get(key)
            if not isinstance(val, str):
                raise ValueError(f"child {key} must be str")
            if "://" in val or "?" in val or "/" in val:
                raise ValueError(f"raw url detected in child {key}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", required=True)
    parser.add_argument("--summary-file", required=True)
    parser.add_argument("--exit-code", type=int, required=True)
    args = parser.parse_args()

    try:
        with open(args.json, "r") as f:
            data = json.load(f)
            
        validate_contract(data)
        
        lines = [
            f"# WP3-C4 URL Shape Diagnostics",
            f"**Classification**: {data['classification']}",
            f"**Action**: {data['recommended_next_action']}",
            f"**Overall Status**: {data['overall_status']}",
            f"",
            f"## Metrics",
            f"- Parent count: {data['parent_count']}",
            f"- Child count: {data['child_count']}",
            f"- Unique Parent Recovered Groups: {data['unique_parent_recovered_group_count']}",
            f"",
            f"## Parents",
            f"```json",
            json.dumps(data["parents"], indent=2),
            f"```",
            f"",
            f"## Children",
            f"```json",
            json.dumps(data["children"], indent=2),
            f"```"
        ]
        
        with open(args.summary_file, "a") as f:
            f.write("\n".join(lines) + "\n")
            
        sys.exit(args.exit_code)
    except Exception as e:
        sys.stderr.write(f"WP3-C4 summary renderer failed: {type(e).__name__}\n")
        sys.exit(args.exit_code if args.exit_code != 0 else 1)

if __name__ == "__main__":
    main()
