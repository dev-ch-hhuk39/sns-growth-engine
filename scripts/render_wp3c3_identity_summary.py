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
    "unique_parent_post_identity_group_count",
    "unique_child_post_identity_group_count",
    "unique_post_identity_group_count",
    "unique_child_id_group_count",
    "unique_parent_fingerprint_group_count",
    "unique_child_fingerprint_group_count",
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
    if val == "UNRESOLVED":
        return
    if not isinstance(val, str) or not re.match(r"^" + prefix + r"_[1-9][0-9]*$", val):
        raise ValueError(f"Invalid group name: {val}")

def validate_contract(data, exit_code):
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object")

    require_keys(data, REQUIRED_TOP_LEVEL_KEYS, "root")
    
    if not is_plain_int(data["schema_version"]) or data["schema_version"] != 1:
        raise ValueError("schema_version must be 1")
        
    if data["mode"] != "READ_ONLY_SOURCE_IDENTITY_COLLISION_INSPECTION":
        raise ValueError("Invalid mode")
        
    if data["overall_status"] not in ["READY_FOR_MANUAL_DECISION", "BLOCKED", "FAIL"]:
        raise ValueError("Invalid overall_status")
        
    if data["classification"] not in ["SAME_POST_REINGESTED", "DISTINCT_POSTS_COLLIDED", "UNRESOLVED_IDENTITY"]:
        raise ValueError("Invalid classification")
        
    if data["recommended_next_action"] not in ["PLAN_DEDUPLICATION", "PLAN_REKEY_MIGRATION", "MANUAL_INVESTIGATION"]:
        raise ValueError("Invalid recommended_next_action")
        
    if data["classification"] == "SAME_POST_REINGESTED" and data["recommended_next_action"] != "PLAN_DEDUPLICATION":
        raise ValueError("Invalid classification/action combo")
    if data["classification"] == "DISTINCT_POSTS_COLLIDED" and data["recommended_next_action"] != "PLAN_REKEY_MIGRATION":
        raise ValueError("Invalid classification/action combo")
    if data["classification"] == "UNRESOLVED_IDENTITY" and data["recommended_next_action"] != "MANUAL_INVESTIGATION":
        raise ValueError("Invalid classification/action combo")
        
    if not isinstance(data["status_reasons"], list):
        raise ValueError("status_reasons must be a list")
    for r in data["status_reasons"]:
        if not isinstance(r, str) or not re.match(r"^[A-Z][A-Z0-9_]*$", r):
            raise ValueError(f"Invalid status reason")
            
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
        "unique_parent_post_identity_group_count",
        "unique_child_post_identity_group_count",
        "unique_post_identity_group_count",
        "unique_child_id_group_count",
        "unique_parent_fingerprint_group_count",
        "unique_child_fingerprint_group_count"
    ]
    for k in int_keys:
        if not is_plain_int(data[k]) or data[k] < 0:
            raise ValueError(f"{k} must be plain int >= 0")

    if not isinstance(data["parents"], list):
        raise ValueError("parents must be a list")
    if not isinstance(data["children"], list):
        raise ValueError("children must be a list")

    if data["parent_count"] != len(data["parents"]):
        raise ValueError("parent_count mismatch")
    if data["child_count"] != len(data["children"]):
        raise ValueError("child_count mismatch")

    parent_row_numbers = set()
    parent_candidate_numbers = set()
    parent_identity_groups = set()
    for p in data["parents"]:
        require_keys(p, [
            "candidate_number", "sheet_row_number", "platform", "identity_kind", 
            "identity_extracted", "post_identity_group", "declared_media_count", 
            "required_field_presence_count", "has_created_at", "has_updated_at", 
            "stable_parent_fingerprint_group", "matching_child_count"
        ], "parent")
        if not is_plain_int(p["candidate_number"]) or p["candidate_number"] < 1: raise ValueError("Invalid candidate_number")
        if not is_plain_int(p["sheet_row_number"]) or p["sheet_row_number"] < 2: raise ValueError("Invalid sheet_row_number")
        if p["platform"] not in ["youtube", "threads", "tiktok", ""]: raise ValueError("Invalid platform")
        if p["identity_kind"] not in ["youtube_video", "threads_post", "tiktok_video", ""]: raise ValueError("Invalid identity_kind")
        if not isinstance(p["identity_extracted"], bool): raise ValueError("Invalid identity_extracted")
        if not is_plain_int(p["declared_media_count"]) or p["declared_media_count"] < 0: raise ValueError("Invalid declared_media_count")
        if not is_plain_int(p["required_field_presence_count"]) or p["required_field_presence_count"] < 0: raise ValueError("Invalid required_field_presence_count")
        if not isinstance(p["has_created_at"], bool): raise ValueError("Invalid has_created_at")
        if not isinstance(p["has_updated_at"], bool): raise ValueError("Invalid has_updated_at")
        if not is_plain_int(p["matching_child_count"]) or p["matching_child_count"] < 0: raise ValueError("Invalid matching_child_count")
        
        validate_group_name(p["post_identity_group"], "POST_GROUP")
        validate_group_name(p["stable_parent_fingerprint_group"], "PARENT_GROUP")
        
        if not p["identity_extracted"]:
            if p["platform"] != "" or p["identity_kind"] != "" or p["post_identity_group"] != "UNRESOLVED":
                raise ValueError("identity_extracted=false requires empty platform/kind and UNRESOLVED group")
                
        parent_row_numbers.add(p["sheet_row_number"])
        parent_candidate_numbers.add(p["candidate_number"])
        if p["post_identity_group"] != "UNRESOLVED":
            parent_identity_groups.add(p["post_identity_group"])
            
    child_row_numbers = set()
    child_candidate_numbers = set()
    child_identity_groups = set()
    for c in data["children"]:
        require_keys(c, [
            "child_number", "sheet_row_number", "identity_extracted", 
            "post_identity_group", "child_id_group", "media_index", 
            "media_type", "stable_child_fingerprint_group"
        ], "child")
        if not is_plain_int(c["child_number"]) or c["child_number"] < 1: raise ValueError("Invalid child_number")
        if not is_plain_int(c["sheet_row_number"]) or c["sheet_row_number"] < 2: raise ValueError("Invalid sheet_row_number")
        if not isinstance(c["identity_extracted"], bool): raise ValueError("Invalid identity_extracted")
        if not is_plain_int(c["media_index"]) or c["media_index"] < -1: raise ValueError("Invalid media_index")
        if c["media_type"] not in ["image", "video", "audio", "carousel", "unknown"]: raise ValueError("Invalid media_type")
        
        validate_group_name(c["post_identity_group"], "POST_GROUP")
        validate_group_name(c["child_id_group"], "CHILD_ID_GROUP")
        validate_group_name(c["stable_child_fingerprint_group"], "CHILD_ROW_GROUP")
        
        child_row_numbers.add(c["sheet_row_number"])
        child_candidate_numbers.add(c["child_number"])
        if c["post_identity_group"] != "UNRESOLVED":
            child_identity_groups.add(c["post_identity_group"])
            
    if data["parent_count"] > 0:
        if sorted(list(parent_candidate_numbers)) != list(range(1, data["parent_count"] + 1)):
            raise ValueError("candidate_number must be contiguous 1..N")
        if len(parent_row_numbers) != data["parent_count"]:
            raise ValueError("Duplicate sheet_row_number in parents")
            
    if data["child_count"] > 0:
        if sorted(list(child_candidate_numbers)) != list(range(1, data["child_count"] + 1)):
            raise ValueError("child_number must be contiguous 1..N")
        if len(child_row_numbers) != data["child_count"]:
            raise ValueError("Duplicate sheet_row_number in children")
            
    if set(parent_row_numbers).intersection(child_row_numbers):
        pass # It is okay if parent and child are on different sheets, but wait, they are different sheets, so row numbers can overlap. No issue.

    if len(parent_identity_groups) != data["unique_parent_post_identity_group_count"]:
        raise ValueError("unique_parent_post_identity_group_count mismatch")
    if len(child_identity_groups) != data["unique_child_post_identity_group_count"]:
        raise ValueError("unique_child_post_identity_group_count mismatch")
    if len(parent_identity_groups.union(child_identity_groups)) != data["unique_post_identity_group_count"]:
        raise ValueError("unique_post_identity_group_count mismatch")

    if data["classification"] == "SAME_POST_REINGESTED":
        if data["parent_count"] < 2: raise ValueError("SAME needs parent_count >= 2")
        if data["child_count"] < 1: raise ValueError("SAME needs child_count > 0")
        if data["unique_parent_post_identity_group_count"] != 1: raise ValueError("SAME needs 1 parent identity group")
    elif data["classification"] == "DISTINCT_POSTS_COLLIDED":
        if data["parent_count"] < 2: raise ValueError("DISTINCT needs parent_count >= 2")
        if data["unique_parent_post_identity_group_count"] < 2: raise ValueError("DISTINCT needs >= 2 parent identity groups")

def render_markdown(data) -> str:
    lines = []
    lines.append("# WP3-C3 Identity Collision Inspection")
    lines.append(f"**Classification**: {sanitize_text(data['classification'])}")
    lines.append(f"**Status**: {sanitize_text(data['overall_status'])}")
    lines.append(f"**Action**: {sanitize_text(data['recommended_next_action'])}")
    lines.append(f"**Checked Commit**: {sanitize_text(data['checked_commit_sha'])}")
    
    if data['status_reasons']:
        lines.append("## Reasons")
        for r in data['status_reasons']:
            lines.append(f"- {sanitize_text(r)}")
            
    lines.append("## Metrics")
    lines.append(f"- Unique Post Identities: {data['unique_post_identity_group_count']}")
    lines.append(f"- Unique Parent Fingerprints: {data['unique_parent_fingerprint_group_count']}")
    lines.append(f"- Unique Child Fingerprints: {data['unique_child_fingerprint_group_count']}")
    
    lines.append("## Parents")
    for p in data['parents']:
        lines.append(f"### Parent {p.get('candidate_number')} (Row {p.get('sheet_row_number')})")
        lines.append(f"- Extracted: {p.get('identity_extracted')}")
        lines.append(f"- Post Identity: {sanitize_text(p.get('post_identity_group'))}")
        lines.append(f"- Parent Fingerprint: {sanitize_text(p.get('stable_parent_fingerprint_group'))}")
        
    lines.append("## Children")
    for c in data['children']:
        lines.append(f"### Child {c.get('child_number')} (Row {c.get('sheet_row_number')})")
        lines.append(f"- Extracted: {c.get('identity_extracted')}")
        lines.append(f"- Post Identity: {sanitize_text(c.get('post_identity_group'))}")
        lines.append(f"- Child ID Group: {sanitize_text(c.get('child_id_group'))}")
        lines.append(f"- Child Fingerprint: {sanitize_text(c.get('stable_child_fingerprint_group'))}")

    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-input", required=True)
    parser.add_argument("--summary-output", required=True)
    parser.add_argument("--exit-code", type=int, required=True)
    args = parser.parse_args()

    if args.exit_code not in [0, 1]:
        print("WP3-C3 summary renderer failed: ValueError", file=sys.stderr)
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
        print(f"WP3-C3 summary renderer failed: {type(e).__name__}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
