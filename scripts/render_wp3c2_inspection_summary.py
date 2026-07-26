import argparse
import json
import sys
import os

def render_summary(plan_json: dict) -> str:
    lines = ["## WP3-C2 Duplicate Parent Inspection Summary", ""]
    
    lines.append("### Overall Status")
    lines.append(f"`{plan_json.get('overall_status', 'UNKNOWN')}`")
    lines.append("")
    
    lines.append("### Target Source Post ID")
    lines.append(f"`{plan_json.get('target_source_post_id', '')}`")
    lines.append("")
    
    verifier = plan_json.get("sheets_verifier", {})
    lines.append("### Sheets Verifier")
    lines.append(f"- Passed: {verifier.get('passed', 0)}")
    lines.append(f"- Total: {verifier.get('total', 0)}")
    lines.append(f"- Basis: {verifier.get('total_basis', '')}")
    lines.append("")
    
    candidates = plan_json.get("parent_candidates", [])
    lines.append(f"### Candidates ({plan_json.get('parent_candidate_count', 0)})")
    for c in candidates:
        has_hash = bool(c.get("canonical_identity_hash"))
        has_pre = bool(c.get("parent_precondition_hash"))
        lines.append(f"- **Candidate #{c.get('candidate_number')}** (Row {c.get('sheet_row_number')})")
        lines.append(f"  - Account: {c.get('account_id')}")
        lines.append(f"  - Declared Media: {c.get('declared_media_count')}")
        lines.append(f"  - Has Canonical URL: {str(c.get('has_canonical_post_url', False)).lower()}")
        lines.append(f"  - Has Canonical Identity Hash: {str(has_hash).lower()}")
        lines.append(f"  - Required Fields: {c.get('required_field_presence_count')}")
        lines.append(f"  - Has Parent Precondition Hash: {str(has_pre).lower()}")
        lines.append(f"  - Canonical Match Children: {c.get('canonical_matching_child_count')}")
        lines.append(f"  - Mismatch Child IDs: {', '.join(c.get('canonical_mismatching_child_ids', []))}")
        lines.append(f"  - Material Diffs: {', '.join(c.get('material_difference_fields', []))}")
        lines.append(f"  - Disposition: {c.get('recommended_disposition')}")
        lines.append(f"  - Blockers: {', '.join(c.get('blocker_codes', []))}")
    lines.append("")
    
    child = plan_json.get("child_summary", {})
    lines.append(f"### Child Summary ({child.get('child_count', 0)})")
    lines.append(f"- Unique IDs: {child.get('unique_child_id_count', 0)}")
    lines.append(f"- Duplicate Media Indexes: {', '.join(map(str, child.get('duplicate_media_indexes', [])))}")
    lines.append("")
    
    keep_row = plan_json.get("recommended_keep_sheet_row_number")
    keep_str = str(keep_row) if keep_row is not None else "null"
    del_rows = plan_json.get("manual_delete_candidate_sheet_row_numbers", [])
    
    lines.append("### Decision")
    lines.append(f"- Recommended Keep Row: {keep_str}")
    lines.append(f"- Manual Delete Rows: {', '.join(map(str, del_rows))}")
    lines.append("")
    
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-input", required=True)
    parser.add_argument("--summary-output", required=True)
    parser.add_argument("--exit-code", type=int, required=True)
    
    args = parser.parse_args()
    
    with open(args.json_input, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except Exception as e:
            sys.exit(f"Failed to parse JSON input: {e}")
            
    summary = render_summary(data)
    
    with open(args.summary_output, 'a', encoding='utf-8') as f:
        f.write(summary)
        
    sys.exit(args.exit_code)

if __name__ == "__main__":
    main()
