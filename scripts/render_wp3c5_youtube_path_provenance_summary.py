#!/usr/bin/env python3
import sys
import json
import argparse
import re

REQUIRED_TOP_LEVEL_KEYS = {
    "schema_version", "mode", "overall_status", "classification",
    "status_reasons", "checked_commit_sha", "counts",
    "static_trace", "parents", "children", "recommended_next_action", "apply_operations"
}

REQUIRED_COUNTS_KEYS = {
    "parent_count", "child_count",
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
    "unique_child_recovered_group_count"
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
    "candidate_number", "sheet_row_number",
    "external_post_id_group", "source_id_group", "source_account_id_group",
    "canonical_url_group", "discovered_at_group", "created_at_group",
    "semantic_parent_group", "path_shape", "tab_kind", "post_kind",
    "media_count", "input_state", "host_family", "has_query", "has_fragment", "post_identity_extracted"
}

REQUIRED_CHILD_KEYS = {
    "child_number", "sheet_row_number",
    "child_id_group", "canonical_url_group", "original_media_url_group",
    "created_at_group", "semantic_child_group", "path_shape", "tab_kind",
    "post_kind", "media_index", "media_type", "acquisition_method_family",
    "input_state", "host_family", "has_query", "has_fragment", "post_identity_extracted"
}

VALID_STATUS_REASONS = {
    "HISTORICAL_CHANNEL_TAB_PSEUDO_ENTRIES",
    "ACCOUNT_PAGE_COLLISION_CONFIRMED",
    "NONPOST_YOUTUBE_URL_COLLISION",
    "MIXED_OR_UNRESOLVED",
    "NO_PARENT_ROWS",
    "NO_CHILD_ROWS",
    "UNSAFE_FLAG_ENABLED",
    "CLIENT_INITIALIZATION_FAILED",
    "WORKSHEET_READ_FAILED",
    "ANALYSIS_FAILED",
    "INSPECTOR_STARTUP_FAILED"
}

VALID_CLASSIFICATIONS = {
    "HISTORICAL_CHANNEL_TAB_PSEUDO_ENTRIES": "PLAN_HISTORICAL_PSEUDO_ENTRY_REPAIR_REVIEW",
    "ACCOUNT_PAGE_COLLISION_CONFIRMED": "TRACE_HISTORICAL_WRITER",
    "NONPOST_YOUTUBE_URL_COLLISION": "TRACE_DATA_ORIGIN",
    "MIXED_OR_UNRESOLVED": "MANUAL_INVESTIGATION"
}

VALID_INPUT_STATES = {"EMPTY", "MALFORMED", "NON_HTTP_URL", "VALID_URL"}
VALID_HOST_FAMILIES = {"EMPTY_OR_INVALID", "OTHER", "INSTAGRAM", "X_TWITTER", "TIKTOK", "YOUTUBE"}
VALID_PATH_SHAPES = {"EMPTY_OR_INVALID", "ROOT_ONLY", "NON_YOUTUBE", "YOUTUBE_POST_SHAPE", "YOUTUBE_NONPOST_OTHER"}
VALID_TAB_KINDS = {"UNKNOWN", "VIDEOS", "SHORTS", "STREAMS"}
VALID_POST_KINDS = {"UNKNOWN", "VIDEO", "SHORT", "STREAM"}
VALID_ACQ_FAMILIES = {"UNKNOWN", "SCRAPER_API", "YTDLP", "BROWSER_AUTOMATION"}
VALID_MEDIA_TYPES = {"UNKNOWN", "VIDEO", "IMAGE", "CAROUSEL"}

def is_plain_int(value: any) -> bool:
    return type(value) is int and type(value) is not bool

def is_strict_bool(value: any) -> bool:
    return type(value) is bool

def validate_group_name(val: str, expected_prefix: str) -> None:
    if not isinstance(val, str) or not val.startswith(expected_prefix):
        raise ValueError(f"Invalid group {val}")

def validate_no_secrets_or_urls_recursive(data: any, is_root: bool = True) -> None:
    if isinstance(data, dict):
        for k, v in data.items():
            if is_root and k == "checked_commit_sha":
                if not isinstance(v, str) or not re.match(r"^[0-9a-f]{40}$", v):
                    raise ValueError("checked_commit_sha must be 40 char hex")
                continue
            validate_no_secrets_or_urls_recursive(v, False)
    elif isinstance(data, list):
        for item in data:
            validate_no_secrets_or_urls_recursive(item, False)
    elif isinstance(data, str):
        v_low = data.lower()
        if "http://" in v_low or "https://" in v_low:
            raise ValueError("URL found")
        if re.search(r"[0-9a-f]{64}", v_low):
            raise ValueError("64-hex string found")
        if re.search(r"[0-9a-f]{40}", v_low):
            if not v_low.startswith("ext_post_id_group_"):
                raise ValueError("40-hex string found")
        
        # Additional exact constraints
        if "token" in v_low or "secret" in v_low or "credential" in v_low or "service account" in v_low or "spreadsheet" in v_low:
            raise ValueError("Sensitive keyword found")
        if "traceback" in v_low or ("line " in v_low and "in <module>" in v_low):
            raise ValueError("Traceback found")
            
        # raw source_post_id format (sp_) and source_post_media_id (spm_)
        if re.search(r"\bsp_[0-9]+_", v_low) or re.search(r"\bspm_", v_low):
            raise ValueError("Raw ID found")
        # YouTube handle format (@...)
        if re.search(r"@[a-zA-Z0-9_-]+", v_low):
            raise ValueError("YouTube handle found")
        # YouTube channel ID format (UC...)
        if re.search(r"\bUC[a-zA-Z0-9_-]{22}\b", v_low):
            raise ValueError("YouTube channel ID found")
        # YouTube video ID format (11 chars)
        # Avoid false positive on group names and enums by restricting to generic text
        pass # Better to check if it's explicitly matched if needed, skipped generic 11char match to avoid false positives

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

    if not isinstance(data["status_reasons"], list):
        raise ValueError("status_reasons must be list")
    for r in data["status_reasons"]:
        if r not in VALID_STATUS_REASONS:
            raise ValueError(f"Invalid status_reason {r}")

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
        if not is_strict_bool(data["static_trace"][k]):
            raise ValueError(f"{k} must be bool")
            
    if not is_plain_int(data["static_trace"]["candidate_historical_writer_count"]):
        raise ValueError("candidate_historical_writer_count must be int")
    if len(data["static_trace"]["candidate_historical_writer_labels"]) != data["static_trace"]["candidate_historical_writer_count"]:
        raise ValueError("writer count mismatch")

    if exit_code == 0:
        if data["overall_status"] != "READY_FOR_MANUAL_DECISION":
            raise ValueError(f"Success exit but status is {data['overall_status']}")
        c = data["classification"]
        if c not in VALID_CLASSIFICATIONS:
            raise ValueError(f"Invalid classification: {c}")
        if data["recommended_next_action"] != VALID_CLASSIFICATIONS[c]:
            raise ValueError(f"Mismatched recommended_next_action for {c}")
    else:
        if data["overall_status"] != "FAIL":
            raise ValueError("Non-zero exit but status not FAIL")
        if data["classification"] != "MIXED_OR_UNRESOLVED":
            raise ValueError("Failure classification must be MIXED_OR_UNRESOLVED")
        if data["recommended_next_action"] != "MANUAL_INVESTIGATION":
            raise ValueError("Failure next action must be MANUAL_INVESTIGATION")
        if data["parents"] or data["children"] or data["apply_operations"]:
            raise ValueError("Fail state must have empty lists")
        if any(v != 0 for v in data["counts"].values()):
            raise ValueError("Fail state must have 0 counts")
        st = data["static_trace"]
        if st["candidate_historical_writer_count"] != 0 or st["candidate_historical_writer_labels"]:
            raise ValueError("Fail state static trace must be empty")
        for k in ["current_parent_id_uses_source_and_external_id", "current_child_id_uses_parent_and_media_index", "current_discovery_rejects_nonpost_youtube_urls", "current_discovery_handles_channel_landing_pages"]:
            if st[k] is not False:
                raise ValueError(f"Fail state static trace flag {k} must be False")

    if not isinstance(data["parents"], list):
        raise ValueError("parents must be list")
    if not isinstance(data["children"], list):
        raise ValueError("children must be list")
        
    if data["counts"]["parent_count"] != len(data["parents"]):
        raise ValueError("parent count mismatch")
    if data["counts"]["child_count"] != len(data["children"]):
        raise ValueError("child count mismatch")
    if data["counts"]["unique_parent_recovered_group_count"] != 0:
        raise ValueError("recovered group count must be 0")
    if data["counts"]["unique_child_recovered_group_count"] != 0:
        raise ValueError("recovered group count must be 0")

    unique_parent_canon = set()
    unique_child_canon = set()
    unique_ext = set()
    unique_src = set()
    unique_child_id = set()
    unique_media_url = set()
    unique_parent_tabs = set()
    unique_child_tabs = set()
    parent_rows = set()
    child_rows = set()
    
    for idx, p in enumerate(data["parents"], start=1):
        if set(p.keys()) != REQUIRED_PARENT_KEYS:
            raise ValueError("Parent keys mismatch")
        if not is_plain_int(p["candidate_number"]) or p["candidate_number"] != idx:
            raise ValueError("Invalid candidate_number")
        if not is_plain_int(p["sheet_row_number"]) or p["sheet_row_number"] < 1:
            raise ValueError("Invalid sheet_row_number")
        if not is_plain_int(p["media_count"]) or p["media_count"] < 0:
            raise ValueError("Invalid media_count")
            
        if p["input_state"] not in VALID_INPUT_STATES: raise ValueError("Invalid input_state")
        if p["host_family"] not in VALID_HOST_FAMILIES: raise ValueError("Invalid host_family")
        if p["path_shape"] not in VALID_PATH_SHAPES: raise ValueError("Invalid path_shape")
        if p["tab_kind"] not in VALID_TAB_KINDS: raise ValueError("Invalid tab_kind")
        if p["post_kind"] not in VALID_POST_KINDS: raise ValueError("Invalid post_kind")
        if not is_strict_bool(p["has_query"]): raise ValueError("has_query must be bool")
        if not is_strict_bool(p["has_fragment"]): raise ValueError("has_fragment must be bool")
        if not is_strict_bool(p["post_identity_extracted"]): raise ValueError("post_identity_extracted must be bool")
            
        validate_group_name(p["external_post_id_group"], "EXT_POST_ID_GROUP")
        validate_group_name(p["source_id_group"], "SOURCE_ID_GROUP")
        validate_group_name(p["source_account_id_group"], "SOURCE_ACCOUNT_ID_GROUP")
        validate_group_name(p["canonical_url_group"], "CANON_URL_GROUP")
        validate_group_name(p["discovered_at_group"], "DISC_AT_GROUP")
        validate_group_name(p["created_at_group"], "CREATED_AT_GROUP")
        validate_group_name(p["semantic_parent_group"], "SEM_PARENT_GROUP")
        
        unique_parent_canon.add(p["canonical_url_group"])
        unique_ext.add(p["external_post_id_group"])
        unique_src.add(p["source_id_group"])
        unique_parent_tabs.add(p["tab_kind"])
        parent_rows.add(p["sheet_row_number"])

    for idx, c in enumerate(data["children"], start=1):
        if set(c.keys()) != REQUIRED_CHILD_KEYS:
            raise ValueError("Child keys mismatch")
        if not is_plain_int(c["child_number"]) or c["child_number"] != idx:
            raise ValueError("Invalid child_number")
        if not is_plain_int(c["sheet_row_number"]) or c["sheet_row_number"] < 1:
            raise ValueError("Invalid sheet_row_number")
        if not is_plain_int(c["media_index"]) or c["media_index"] < 0:
            raise ValueError("Invalid media_index")
            
        if c["input_state"] not in VALID_INPUT_STATES: raise ValueError("Invalid input_state")
        if c["host_family"] not in VALID_HOST_FAMILIES: raise ValueError("Invalid host_family")
        if c["path_shape"] not in VALID_PATH_SHAPES: raise ValueError("Invalid path_shape")
        if c["tab_kind"] not in VALID_TAB_KINDS: raise ValueError("Invalid tab_kind")
        if c["post_kind"] not in VALID_POST_KINDS: raise ValueError("Invalid post_kind")
        if c["media_type"] not in VALID_MEDIA_TYPES: raise ValueError("Invalid media_type")
        if c["acquisition_method_family"] not in VALID_ACQ_FAMILIES: raise ValueError("Invalid acquisition_method_family")
        if not is_strict_bool(c["has_query"]): raise ValueError("has_query must be bool")
        if not is_strict_bool(c["has_fragment"]): raise ValueError("has_fragment must be bool")
        if not is_strict_bool(c["post_identity_extracted"]): raise ValueError("post_identity_extracted must be bool")
            
        validate_group_name(c["child_id_group"], "CHILD_ID_GROUP")
        validate_group_name(c["canonical_url_group"], "CANON_URL_GROUP")
        validate_group_name(c["original_media_url_group"], "MEDIA_URL_GROUP")
        validate_group_name(c["created_at_group"], "CREATED_AT_GROUP")
        validate_group_name(c["semantic_child_group"], "SEM_CHILD_GROUP")
        
        unique_child_canon.add(c["canonical_url_group"])
        unique_child_id.add(c["child_id_group"])
        unique_media_url.add(c["original_media_url_group"])
        unique_child_tabs.add(c["tab_kind"])
        child_rows.add(c["sheet_row_number"])

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
        
    if data["counts"]["unique_parent_tab_kind_count"] != len(unique_parent_tabs):
        raise ValueError("unique_parent_tab_kind_count mismatch")
    if data["counts"]["unique_child_tab_kind_count"] != len(unique_child_tabs):
        raise ValueError("unique_child_tab_kind_count mismatch")
        
    url_match_count = len(unique_parent_canon & unique_child_canon)
    if data["counts"]["parent_child_url_group_match_count"] != url_match_count:
        raise ValueError("parent_child_url_group_match_count mismatch")
        
    row_match_count = len(parent_rows & child_rows)
    if data["counts"]["parent_child_row_number_match_count"] != row_match_count:
        raise ValueError("parent_child_row_number_match_count mismatch")

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
