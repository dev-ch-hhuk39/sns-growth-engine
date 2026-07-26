import argparse
import json
import sys
import re

def is_plain_int(val):
    if isinstance(val, bool):
        return False
    return isinstance(val, int)

def require_keys(obj, keys, context=""):
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
    "parent_count",
    "child_count",
    "unique_parent_recovered_group_count",
    "unique_child_recovered_group_count",
    "unique_normalized_url_group_count",
    "unique_semantic_parent_group_count",
    "unique_semantic_child_group_count",
    "parents",
    "children",
    "recommended_next_action",
    "apply_operations"
]

def sanitize_text(text: str) -> str:
    s = str(text)
    s = s.replace("\r", " ").replace("\n", " ")
    s = s.replace("`", "'")
    if len(s) > 200:
        s = s[:197] + "..."
    return s

def validate_group_name(val, prefix):
    if val in ("UNRESOLVED", "EMPTY", "NONE"):
        return
    if not isinstance(val, str) or not re.match(r"^" + prefix + r"_[1-9][0-9]*$", val):
        raise ValueError(f"Invalid group name: {val}")

def validate_no_secrets_or_urls(val):
    if not isinstance(val, str):
        return
    if re.search(r"http[s]?://", val) or re.search(r"[0-9a-f]{64}", val.lower()) or "token" in val.lower() or "secret" in val.lower():
        raise ValueError("Sensitive data leaked in output (URL, hash, token)")

def validate_contract(data, exit_code):
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object")

    require_keys(data, REQUIRED_TOP_LEVEL_KEYS, "root")
    
    if not is_plain_int(data["schema_version"]) or data["schema_version"] != 1:
        raise ValueError("schema_version must be 1")
        
    if data["mode"] != "READ_ONLY_SAFE_URL_SHAPE_DIAGNOSTICS":
        raise ValueError("Invalid mode")
        
    if data["overall_status"] not in ["READY_FOR_MANUAL_DECISION", "FAIL"]:
        raise ValueError("Invalid overall_status")
        
    valid_actions = {
        "RECOVERABLE_SAME_POST": "PLAN_DEDUPLICATION_INSPECTION",
        "RECOVERABLE_DISTINCT_POSTS": "PLAN_REKEY_MIGRATION_INSPECTION",
        "ACCOUNT_OR_CHANNEL_URLS": "TRACE_ID_GENERATION",
        "WRAPPED_OR_ENCODED_URLS": "EXTEND_LOCAL_PARSER",
        "PLACEHOLDER_OR_NONPUBLIC_URLS": "TRACE_DATA_ORIGIN",
        "MIXED_OR_UNRESOLVED": "MANUAL_INVESTIGATION"
    }
    if data["classification"] not in valid_actions:
        raise ValueError("Invalid classification")
    if data["recommended_next_action"] != valid_actions[data["classification"]]:
        raise ValueError("classification/action mismatch")
        
    if not isinstance(data["status_reasons"], list) or len(data["status_reasons"]) == 0:
        raise ValueError("status_reasons must be a non-empty list")
    for r in data["status_reasons"]:
        if not isinstance(r, str) or not re.match(r"^[A-Z][A-Z0-9_]*$", r):
            raise ValueError("Invalid status reason format (must be uppercase code)")
            
    if not isinstance(data["checked_commit_sha"], str) or not re.match(r"^[0-9a-f]{40}$", data["checked_commit_sha"]):
        raise ValueError("checked_commit_sha must be 40 lowercase hex chars")
        
    if not isinstance(data["apply_operations"], list) or len(data["apply_operations"]) > 0:
        raise ValueError("apply_operations must be empty")

    if data["overall_status"] == "FAIL":
        if exit_code != 1:
            raise ValueError("exit_code must be 1 when overall_status is FAIL")
    else:
        if exit_code != 0:
            raise ValueError("exit_code must be 0 when overall_status is not FAIL")

    int_keys = [
        "parent_count", "child_count",
        "unique_parent_recovered_group_count",
        "unique_child_recovered_group_count",
        "unique_normalized_url_group_count",
        "unique_semantic_parent_group_count",
        "unique_semantic_child_group_count"
    ]
    for k in int_keys:
        if not is_plain_int(data[k]) or data[k] < 0:
            raise ValueError(f"{k} must be plain int >= 0")


    parent_rows = set()
    for i, p in enumerate(data["parents"]):
        if p["candidate_number"] != i + 1: raise ValueError("candidate_number not continuous")
        if p["sheet_row_number"] in parent_rows: raise ValueError("Duplicate sheet_row_number in parents")
        parent_rows.add(p["sheet_row_number"])
        
    child_rows = set()
    for i, c in enumerate(data["children"]):
        if c["child_number"] != i + 1: raise ValueError("child_number not continuous")
        if c["sheet_row_number"] in child_rows: raise ValueError("Duplicate sheet_row_number in children")
        child_rows.add(c["sheet_row_number"])

    if not isinstance(data["parents"], list):
        raise ValueError("parents must be a list")
    if not isinstance(data["children"], list):
        raise ValueError("children must be a list")

    if data["parent_count"] != len(data["parents"]):
        raise ValueError("parent_count mismatch")
    if data["child_count"] != len(data["children"]):
        raise ValueError("child_count mismatch")

    ALLOWED_QUERY_KEYS = {"v", "url", "q", "u", "target", "list"}

    for p in data["parents"]:
        require_keys(p, [
            "candidate_number", "sheet_row_number", "input_state", "host_family", 
            "path_family", "allowed_query_key_flags", "has_nested_url", 
            "decoded_layer_count", "direct_identity_extracted", "recovery_method",
            "recovered_identity_extracted", "recovered_post_group",
            "normalized_url_group", "semantic_parent_group", "declared_media_count", 
            "matching_recovered_child_count"
        ], "parent")
        if not is_plain_int(p["candidate_number"]) or p["candidate_number"] < 1: raise ValueError("Invalid candidate_number")
        if not is_plain_int(p["sheet_row_number"]) or p["sheet_row_number"] < 2: raise ValueError("Invalid sheet_row_number")
        
        if not isinstance(p["allowed_query_key_flags"], list): raise ValueError("allowed_query_key_flags must be list")
        for k in p["allowed_query_key_flags"]:
            if k not in ALLOWED_QUERY_KEYS: raise ValueError(f"Disallowed query key in flags: {k}")
            
        if not is_plain_int(p["decoded_layer_count"]) or p["decoded_layer_count"] < 0 or p["decoded_layer_count"] > 2: raise ValueError("Invalid decoded_layer_count")
        if not is_plain_int(p["declared_media_count"]) or p["declared_media_count"] < 0: raise ValueError("Invalid declared_media_count")
        if not is_plain_int(p["matching_recovered_child_count"]) or p["matching_recovered_child_count"] < 0: raise ValueError("Invalid matching_recovered_child_count")
        
        validate_group_name(p["recovered_post_group"], "RECOVERED_POST_GROUP")
        validate_group_name(p["normalized_url_group"], "URL_GROUP")
        validate_group_name(p["semantic_parent_group"], "SEM_PARENT_GROUP")
        validate_no_secrets_or_urls(p["recovered_post_group"])
        validate_no_secrets_or_urls(p["normalized_url_group"])
        validate_no_secrets_or_urls(p["semantic_parent_group"])
        
    for c in data["children"]:
        require_keys(c, [
            "child_number", "sheet_row_number", "input_state", "host_family", 
            "path_family", "allowed_query_key_flags", "has_nested_url", 
            "decoded_layer_count", "direct_identity_extracted", "recovery_method",
            "recovered_identity_extracted", "recovered_post_group",
            "normalized_url_group", "child_id_group", "semantic_child_group", 
            "media_index", "media_type"
        ], "child")
        if not is_plain_int(c["child_number"]) or c["child_number"] < 1: raise ValueError("Invalid child_number")
        if not is_plain_int(c["sheet_row_number"]) or c["sheet_row_number"] < 2: raise ValueError("Invalid sheet_row_number")
        
        if not isinstance(c["allowed_query_key_flags"], list): raise ValueError("allowed_query_key_flags must be list")
        for k in c["allowed_query_key_flags"]:
            if k not in ALLOWED_QUERY_KEYS: raise ValueError(f"Disallowed query key in flags: {k}")
            
        if not is_plain_int(c["decoded_layer_count"]) or c["decoded_layer_count"] < 0 or c["decoded_layer_count"] > 2: raise ValueError("Invalid decoded_layer_count")
        if not is_plain_int(c["media_index"]) or c["media_index"] < 0: raise ValueError("Invalid media_index")
        
        validate_group_name(c["recovered_post_group"], "RECOVERED_POST_GROUP")
        validate_group_name(c["normalized_url_group"], "URL_GROUP")
        validate_group_name(c["child_id_group"], "CHILD_ID_GROUP")
        validate_group_name(c["semantic_child_group"], "SEM_CHILD_GROUP")
        validate_no_secrets_or_urls(c["recovered_post_group"])
        validate_no_secrets_or_urls(c["normalized_url_group"])
        validate_no_secrets_or_urls(c["child_id_group"])
        validate_no_secrets_or_urls(c["semantic_child_group"])

def render_markdown(data) -> str:
    lines = []
    lines.append("# WP3-C4 Safe URL Shape Diagnostics")
    lines.append(f"**Classification**: {sanitize_text(data['classification'])}")
    lines.append(f"**Status**: {sanitize_text(data['overall_status'])}")
    lines.append(f"**Action**: {sanitize_text(data['recommended_next_action'])}")
    lines.append(f"**Checked Commit**: {sanitize_text(data['checked_commit_sha'])}")
    
    if data['status_reasons']:
        lines.append("## Reasons")
        for r in data['status_reasons']:
            lines.append(f"- {sanitize_text(r)}")
            
    lines.append("## Metrics")
    lines.append(f"- Unique Parent Recovered Groups: {data['unique_parent_recovered_group_count']}")
    lines.append(f"- Unique Child Recovered Groups: {data['unique_child_recovered_group_count']}")
    lines.append(f"- Unique URL Groups: {data['unique_normalized_url_group_count']}")
    lines.append(f"- Unique Semantic Parent Groups: {data['unique_semantic_parent_group_count']}")
    lines.append(f"- Unique Semantic Child Groups: {data['unique_semantic_child_group_count']}")
    
    lines.append("## Parents")
    for p in data['parents']:
        lines.append(f"### Parent {p.get('candidate_number')} (Row {p.get('sheet_row_number')})")
        lines.append(f"- Host Family: {sanitize_text(p.get('host_family'))}")
        lines.append(f"- Path Family: {sanitize_text(p.get('path_family'))}")
        lines.append(f"- Direct Identity Extracted: {p.get('direct_identity_extracted')}")
        lines.append(f"- Recovery Method: {sanitize_text(p.get('recovery_method'))}")
        lines.append(f"- Recovered Post Group: {sanitize_text(p.get('recovered_post_group'))}")
        lines.append(f"- URL Group: {sanitize_text(p.get('normalized_url_group'))}")
        lines.append(f"- Semantic Parent Group: {sanitize_text(p.get('semantic_parent_group'))}")
        
    lines.append("## Children")
    for c in data['children']:
        lines.append(f"### Child {c.get('child_number')} (Row {c.get('sheet_row_number')})")
        lines.append(f"- Host Family: {sanitize_text(c.get('host_family'))}")
        lines.append(f"- Path Family: {sanitize_text(c.get('path_family'))}")
        lines.append(f"- Direct Identity Extracted: {c.get('direct_identity_extracted')}")
        lines.append(f"- Recovery Method: {sanitize_text(c.get('recovery_method'))}")
        lines.append(f"- Recovered Post Group: {sanitize_text(c.get('recovered_post_group'))}")
        lines.append(f"- URL Group: {sanitize_text(c.get('normalized_url_group'))}")
        lines.append(f"- Child ID Group: {sanitize_text(c.get('child_id_group'))}")
        lines.append(f"- Semantic Child Group: {sanitize_text(c.get('semantic_child_group'))}")

    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-input", required=True)
    parser.add_argument("--summary-output", required=True)
    parser.add_argument("--exit-code", type=int, required=True)
    args = parser.parse_args()

    if args.exit_code not in [0, 1]:
        print("WP3-C4 summary renderer failed: ValueError", file=sys.stderr)
        sys.exit(1)

    try:
        with open(args.json_input, "r") as f:
            data = json.load(f)
            
        validate_contract(data, args.exit_code)
        md = render_markdown(data)
        
        with open(args.summary_output, "a") as f:
            f.write(md + "\n")
            
        sys.exit(args.exit_code)
            
    except Exception as e:
        print(f"WP3-C4 summary renderer failed: {type(e).__name__}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
