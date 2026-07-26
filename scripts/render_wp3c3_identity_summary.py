import argparse
import json
import sys

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
        
    if not isinstance(data["status_reasons"], list):
        raise ValueError("status_reasons must be a list")
        
    if not isinstance(data["apply_operations"], list) or len(data["apply_operations"]) > 0:
        raise ValueError("apply_operations must be empty")

    if data["overall_status"] == "FAIL":
        if exit_code != 1:
            raise ValueError("exit_code must be 1 when overall_status is FAIL")
    else:
        if exit_code != 0:
            raise ValueError("exit_code must be 0 when overall_status is not FAIL")

    if not isinstance(data["parents"], list):
        raise ValueError("parents must be a list")
    if not isinstance(data["children"], list):
        raise ValueError("children must be a list")

    if data["parent_count"] != len(data["parents"]):
        raise ValueError("parent_count mismatch")
    if data["child_count"] != len(data["children"]):
        raise ValueError("child_count mismatch")

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

    try:
        with open(args.json_input, "r") as f:
            data = json.load(f)
            
        validate_contract(data, args.exit_code)
        md = render_markdown(data)
        
        with open(args.summary_output, "w") as f:
            f.write(md)
            
    except Exception as e:
        print(f"WP3-C3 summary renderer failed: {type(e).__name__}: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
