import argparse
import json
import sys

def safe_text(value, max_length=200):
    text = str(value) if value is not None else ""
    text = text.replace("\r", " ").replace("\n", " ")
    text = text.replace("`", "'")
    return text[:max_length]

def is_plain_int(value):
    return isinstance(value, int) and not isinstance(value, bool)

REQUIRED_TOP_LEVEL_KEYS = {
    "schema_version",
    "mode",
    "overall_status",
    "status_reasons",
    "sheets_verifier",
    "target_source_post_id",
    "parent_candidate_count",
    "parent_candidates",
    "child_summary",
    "recommended_keep_sheet_row_number",
    "manual_delete_candidate_sheet_row_numbers",
    "apply_operations",
}

REQUIRED_CANDIDATE_KEYS = {
    "candidate_number",
    "sheet_row_number",
    "account_id",
    "declared_media_count",
    "has_canonical_post_url",
    "canonical_identity_hash",
    "required_field_presence_count",
    "parent_precondition_hash",
    "canonical_matching_child_count",
    "canonical_mismatching_child_ids",
    "material_difference_fields",
    "recommended_disposition",
    "blocker_codes",
}

REQUIRED_CHILD_SUMMARY_KEYS = {
    "child_count",
    "unique_child_id_count",
    "child_id_duplicate_count",
    "duplicate_media_indexes",
    "missing_child_id_count",
    "malformed_media_index_count",
    "negative_media_index_count",
}

def require_keys(value: dict, required: set[str], label: str) -> None:
    missing = sorted(required - set(value))
    if missing:
        raise ValueError(f"{label}_missing_required_keys")

def validate_contract(plan_json, exit_code):
    if not isinstance(plan_json, dict):
        raise ValueError("Top-level is not dict")
        
    require_keys(plan_json, REQUIRED_TOP_LEVEL_KEYS, "plan")
    
    if plan_json["schema_version"] != 1 or not is_plain_int(plan_json["schema_version"]):
        raise ValueError("schema_version is not 1 or not int")
        
    if plan_json["mode"] != "READ_ONLY_DUPLICATE_PARENT_INSPECTION":
        raise ValueError("mode is not READ_ONLY_DUPLICATE_PARENT_INSPECTION")
        
    overall_status = plan_json["overall_status"]
    if overall_status not in ["READY_FOR_MANUAL_DECISION", "BLOCKED", "FAIL"]:
        raise ValueError("overall_status invalid")
        
    if exit_code not in (0, 1):
        raise ValueError("exit_code must be 0 or 1")
    if overall_status == "FAIL" and exit_code != 1:
        raise ValueError("FAIL must have exit 1")
    if overall_status != "FAIL" and exit_code != 0:
        raise ValueError("non-FAIL must have exit 0")
        
    if not isinstance(plan_json["status_reasons"], list):
        raise ValueError("status_reasons is not list")
        
    if not isinstance(plan_json["sheets_verifier"], dict):
        raise ValueError("sheets_verifier is not dict")
        
    if not isinstance(plan_json["target_source_post_id"], str):
        raise ValueError("target_source_post_id is not str")
        
    candidate_count = plan_json["parent_candidate_count"]
    if not is_plain_int(candidate_count) or candidate_count < 0:
        raise ValueError("parent_candidate_count is not plain positive int")
        
    candidates = plan_json["parent_candidates"]
    if not isinstance(candidates, list):
        raise ValueError("parent_candidates is not list")
        
    if candidate_count != len(candidates):
        raise ValueError("parent_candidate_count mismatch")
        
    if overall_status == "FAIL" and candidate_count != 0:
        raise ValueError("FAIL must have 0 candidates")
        
    for c in candidates:
        if not isinstance(c, dict):
            raise ValueError("candidate is not dict")
        require_keys(c, REQUIRED_CANDIDATE_KEYS, "candidate")
        if not is_plain_int(c["candidate_number"]):
            raise ValueError("candidate_number is not plain int")
        if not is_plain_int(c["sheet_row_number"]):
            raise ValueError("sheet_row_number is not plain int")
        if not isinstance(c["has_canonical_post_url"], bool):
            raise ValueError("has_canonical_post_url is not bool")
        if not isinstance(c["canonical_mismatching_child_ids"], list):
            raise ValueError("canonical_mismatching_child_ids is not list")
        if not isinstance(c["material_difference_fields"], list):
            raise ValueError("material_difference_fields is not list")
        if not isinstance(c["blocker_codes"], list):
            raise ValueError("blocker_codes is not list")
            
    child_summary = plan_json["child_summary"]
    if not isinstance(child_summary, dict):
        raise ValueError("child_summary is not dict")
        
    if overall_status != "FAIL":
        require_keys(child_summary, REQUIRED_CHILD_SUMMARY_KEYS, "child_summary")
        for k in ["child_count", "unique_child_id_count", "child_id_duplicate_count", "missing_child_id_count", "malformed_media_index_count", "negative_media_index_count"]:
            val = child_summary[k]
            if not is_plain_int(val) or val < 0:
                raise ValueError(f"{k} must be plain positive int")
        dup_indexes = child_summary["duplicate_media_indexes"]
        if not isinstance(dup_indexes, list) or not all(is_plain_int(x) for x in dup_indexes):
            raise ValueError("duplicate_media_indexes must be list[int]")
            
    keep_row = plan_json["recommended_keep_sheet_row_number"]
    if keep_row is not None and not is_plain_int(keep_row):
        raise ValueError("recommended_keep_sheet_row_number must be plain int or None")
        
    del_rows = plan_json["manual_delete_candidate_sheet_row_numbers"]
    if not isinstance(del_rows, list) or not all(is_plain_int(x) for x in del_rows):
        raise ValueError("manual_delete_candidate_sheet_row_numbers must be list[int]")
        
    ops = plan_json["apply_operations"]
    if not isinstance(ops, list):
        raise ValueError("apply_operations is not list")
    if len(ops) > 0:
        raise ValueError("apply_operations is not empty")

def render_summary(plan_json: dict) -> str:
    lines = ["## WP3-C2 Duplicate Parent Inspection Summary", ""]
    
    lines.append("### Overall Status")
    lines.append(f"`{safe_text(plan_json.get('overall_status', 'UNKNOWN'))}`")
    lines.append("")
    
    lines.append("### Target Source Post ID")
    lines.append(f"`{safe_text(plan_json.get('target_source_post_id', ''))}`")
    lines.append("")
    
    reasons = plan_json.get("status_reasons", [])
    lines.append("### Status Reasons")
    if not reasons:
        lines.append("- None")
    else:
        for r in reasons:
            lines.append(f"- {safe_text(r)}")
    lines.append("")
    
    verifier = plan_json.get("sheets_verifier", {})
    lines.append("### Sheets Verifier")
    lines.append(f"- Passed: {safe_text(verifier.get('passed', 0))}")
    lines.append(f"- Total: {safe_text(verifier.get('total', 0))}")
    lines.append(f"- Basis: {safe_text(verifier.get('total_basis', ''))}")
    lines.append("")
    
    candidates = plan_json.get("parent_candidates", [])
    lines.append(f"### Candidates ({safe_text(plan_json.get('parent_candidate_count', 0))})")
    for c in candidates:
        has_hash = bool(c.get("canonical_identity_hash"))
        has_pre = bool(c.get("parent_precondition_hash"))
        lines.append(f"- **Candidate #{safe_text(c.get('candidate_number'))}** (Row {safe_text(c.get('sheet_row_number'))})")
        lines.append(f"  - Account: {safe_text(c.get('account_id'))}")
        lines.append(f"  - Declared Media: {safe_text(c.get('declared_media_count'))}")
        lines.append(f"  - Has Canonical URL: {str(c.get('has_canonical_post_url', False)).lower()}")
        lines.append(f"  - Has Canonical Identity Hash: {str(has_hash).lower()}")
        lines.append(f"  - Required Fields: {safe_text(c.get('required_field_presence_count'))}")
        lines.append(f"  - Has Parent Precondition Hash: {str(has_pre).lower()}")
        lines.append(f"  - Canonical Match Children: {safe_text(c.get('canonical_matching_child_count'))}")
        
        mismatched = c.get('canonical_mismatching_child_ids', [])
        lines.append(f"  - Mismatch Child IDs: {safe_text(', '.join(map(str, mismatched)))}")
        
        diffs = c.get('material_difference_fields', [])
        lines.append(f"  - Material Diffs: {safe_text(', '.join(map(str, diffs)))}")
        lines.append(f"  - Disposition: {safe_text(c.get('recommended_disposition'))}")
        
        blockers = c.get('blocker_codes', [])
        lines.append(f"  - Blockers: {safe_text(', '.join(map(str, blockers)))}")
    lines.append("")
    
    child = plan_json.get("child_summary", {})
    lines.append(f"### Child Summary")
    lines.append(f"- Child Count: {safe_text(child.get('child_count', ''))}")
    lines.append(f"- Unique IDs: {safe_text(child.get('unique_child_id_count', ''))}")
    lines.append(f"- Duplicate Child IDs: {safe_text(child.get('child_id_duplicate_count', ''))}")
    
    dup_media = child.get('duplicate_media_indexes', [])
    lines.append(f"- Duplicate Media Indexes: {safe_text(', '.join(map(str, dup_media)))}")
    lines.append(f"- Missing Child IDs: {safe_text(child.get('missing_child_id_count', ''))}")
    lines.append(f"- Malformed Media Indexes: {safe_text(child.get('malformed_media_index_count', ''))}")
    lines.append(f"- Negative Media Indexes: {safe_text(child.get('negative_media_index_count', ''))}")
    lines.append("")
    
    keep_row = plan_json.get("recommended_keep_sheet_row_number")
    keep_str = str(keep_row) if keep_row is not None else "null"
    del_rows = plan_json.get("manual_delete_candidate_sheet_row_numbers", [])
    
    lines.append("### Decision")
    lines.append(f"- Recommended Keep Row: {safe_text(keep_str)}")
    lines.append(f"- Manual Delete Rows: {safe_text(', '.join(map(str, del_rows)))}")
    lines.append(f"- Apply Operations Count: 0")
    lines.append("")
    
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-input", required=True)
    parser.add_argument("--summary-output", required=True)
    parser.add_argument("--exit-code", type=int, required=True)
    
    args = parser.parse_args()
    
    try:
        with open(args.json_input, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        validate_contract(data, args.exit_code)
        summary = render_summary(data)
        
    except Exception as exc:
        print(f"WP3-C2 summary renderer failed: {type(exc).__name__}", file=sys.stderr)
        sys.exit(1)
        
    with open(args.summary_output, 'a', encoding='utf-8') as f:
        f.write(summary)
            
    sys.exit(args.exit_code)

if __name__ == "__main__":
    main()
