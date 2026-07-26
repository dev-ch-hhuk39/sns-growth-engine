import argparse
import json
import sys
import os

def safe_text(value, max_length=200):
    text = str(value) if value is not None else ""
    text = text.replace("\r", " ").replace("\n", " ")
    text = text.replace("`", "'")
    return text[:max_length]

def validate_contract(plan_json):
    if not isinstance(plan_json, dict):
        raise ValueError("Top-level is not dict")
    if plan_json.get("schema_version") != 1:
        raise ValueError("schema_version is not 1")
    if plan_json.get("overall_status") not in ["READY_FOR_MANUAL_DECISION", "BLOCKED", "FAIL"]:
        raise ValueError("overall_status invalid")
    if not isinstance(plan_json.get("sheets_verifier", {}), dict):
        raise ValueError("sheets_verifier is not dict")
    
    candidates = plan_json.get("parent_candidates", [])
    if not isinstance(candidates, list):
        raise ValueError("parent_candidates is not list")
    
    for c in candidates:
        if not isinstance(c, dict):
            raise ValueError("candidate is not dict")
            
    if plan_json.get("parent_candidate_count", 0) != len(candidates):
        raise ValueError("parent_candidate_count mismatch")
        
    if not isinstance(plan_json.get("status_reasons", []), list):
        raise ValueError("status_reasons is not list")
        
    if not isinstance(plan_json.get("child_summary", {}), dict):
        raise ValueError("child_summary is not dict")
        
    if not isinstance(plan_json.get("manual_delete_candidate_sheet_row_numbers", []), list):
        raise ValueError("manual_delete_candidate_sheet_row_numbers is not list")
        
    ops = plan_json.get("apply_operations", [])
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
    lines.append(f"- Child Count: {safe_text(child.get('child_count', 0))}")
    lines.append(f"- Unique IDs: {safe_text(child.get('unique_child_id_count', 0))}")
    lines.append(f"- Duplicate Child IDs: {safe_text(child.get('child_id_duplicate_count', 0))}")
    
    dup_media = child.get('duplicate_media_indexes', [])
    lines.append(f"- Duplicate Media Indexes: {safe_text(', '.join(map(str, dup_media)))}")
    lines.append(f"- Missing Child IDs: {safe_text(child.get('missing_child_id_count', 0))}")
    lines.append(f"- Malformed Media Indexes: {safe_text(child.get('malformed_media_index_count', 0))}")
    lines.append(f"- Negative Media Indexes: {safe_text(child.get('negative_media_index_count', 0))}")
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
        
        validate_contract(data)
        summary = render_summary(data)
        
        with open(args.summary_output, 'a', encoding='utf-8') as f:
            f.write(summary)
            
    except Exception as exc:
        print(f"WP3-C2 summary renderer failed: {type(exc).__name__}", file=sys.stderr)
        sys.exit(1)
        
    sys.exit(args.exit_code)

if __name__ == "__main__":
    main()
