#!/usr/bin/env python3
import sys
import json
import os

def safe_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0

def classify_no_post_reason(value: str) -> str:
    if "stale_slot_claim_requires_explicit_recovery" in value:
        return "STALE_SLOT_REQUIRES_RECOVERY"
    if "same text/account/platform/media already POSTED" in value or "same text/account/platform already POSTED" in value:
        return "DUPLICATE_CONTENT_ALREADY_POSTED"
    if "missed_text_slot_aftercare" in value:
        return "MISSED_TEXT_SLOT_AFTERCARE"
    if "COMMAND_FAILED" in value:
        return "COMMAND_FAILED"
    if "EMPTY_TEXT" in value:
        return "EMPTY_TEXT"
    if "ALLOW_MEDIA_POSTS=true and ALLOW_REAL_THREADS_VIDEO_POST=true are required" in value:
        return "MEDIA_POST_GATES_DISABLED"
    if "generated_clip_recovery_no_eligible_media_candidate" in value:
        return "NO_ELIGIBLE_MEDIA_CANDIDATE"
    if "TimeoutError" in value:
        return "THREADS_API_TIMEOUT"
    if "RuntimeError" in value:
        return "THREADS_API_RUNTIME_ERROR"
    return "OTHER_REDACTED"

def extract_stale_slot_labels(values) -> list[str]:
    if not isinstance(values, list):
        return []

    result: list[str] = []

    for item in values[:20]:
        if isinstance(item, str):
            slot_id = item.strip()
        elif isinstance(item, dict):
            slot_id = str(item.get("slot_run_id", "")).strip()
        else:
            slot_id = ""

        if slot_id:
            label = f"STALE_SLOT_{len(result) + 1}"
            if label not in result:
                result.append(label)

    return result


def build_safe_summary(report: dict) -> dict:
    sheets_info = report.get("sheets_verifier", {})
    creds = report.get("credentials", {})
    tp = report.get("text_pipeline", {})
    si = report.get("source_inventory", {})
    pr = report.get("permission_requirements", {})
    ig = report.get("integrity", {})

    def get_tp_stats(account_id: str) -> dict:
        account_data = tp.get(account_id, {})
        return {
            "ready_text_count": safe_int(account_data.get("ready_text_count")),
            "waiting_review_count": safe_int(account_data.get("waiting_review_count")),
            "processing_count": safe_int(account_data.get("processing_count")),
            "posted_text_count": safe_int(account_data.get("posted_text_count")),
        }

    night_sources = si.get("night_scout", {})
    liver_sources = si.get("liver_manager", {})

    # Process no_post_reasons
    no_post_reason_codes = {"night_scout": {}, "liver_manager": {}}
    for account_id in ["night_scout", "liver_manager"]:
        reasons = tp.get(account_id, {}).get("no_post_reasons", {})
        if isinstance(reasons, dict):
            for reason_str, count in reasons.items():
                code = classify_no_post_reason(reason_str)
                no_post_reason_codes[account_id][code] = no_post_reason_codes[account_id].get(code, 0) + safe_int(count)

    # Process permission warnings
    permission_warnings = []
    night_pr = pr.get("night_scout", {})
    if night_pr.get("status") == "PASS" and night_pr.get("missing_or_invalid_source_ids"):
        permission_warnings.append("NIGHT_HAS_PARTIAL_PERMISSION_COVERAGE")

    liver_pr = pr.get("liver_manager", {})
    if liver_pr.get("status") == "PASS" and liver_pr.get("missing_or_invalid_source_ids"):
        permission_warnings.append("LIVER_HAS_PARTIAL_PERMISSION_COVERAGE")

    # Process parent integrity
    allowed_parent_integrity_reasons = {
        "EMPTY_SOURCE_POST_ID",
        "PARENT_NOT_FOUND",
        "DUPLICATE_MEDIA_INDEX",
        "CANONICAL_POST_URL_MISMATCH",
        "MEDIA_COUNT_MISMATCH"
    }

    parent_integrity_failures_raw = (
        ig.get("parent_integrity_failures", [])
        if isinstance(ig.get("parent_integrity_failures", []), list)
        else []
    )

    parent_reason_counts: dict[str, int] = {}

    for failure in parent_integrity_failures_raw:
        if not isinstance(failure, dict):
            safe_reason = "UNKNOWN_PARENT_INTEGRITY_FAILURE"
        else:
            reason = str(failure.get("reason", ""))
            safe_reason = (
                reason
                if reason in allowed_parent_integrity_reasons
                else "UNKNOWN_PARENT_INTEGRITY_FAILURE"
            )

        parent_reason_counts[safe_reason] = (
            parent_reason_counts.get(safe_reason, 0) + 1
        )

    parent_integrity_failures_safe = []
    for failure in parent_integrity_failures_raw[:50]:
        if not isinstance(failure, dict):
            safe_reason = "UNKNOWN_PARENT_INTEGRITY_FAILURE"
            account_id = ""
        else:
            reason = str(failure.get("reason", ""))
            safe_reason = reason if reason in allowed_parent_integrity_reasons else "UNKNOWN_PARENT_INTEGRITY_FAILURE"
            account_id = str(failure.get("account_id", ""))

        parent_integrity_failures_safe.append({
            "failure_label": f"PARENT_FAILURE_{len(parent_integrity_failures_safe) + 1}",
            "reason": safe_reason,
            "account_id": account_id
        })

    # Process stale slots
    stale_slots_raw = ig.get("stale_inflight_slots", [])
    stale_slots_safe = extract_stale_slot_labels(stale_slots_raw)
    stale_slot_count = (
        len(stale_slots_raw)
        if isinstance(stale_slots_raw, list)
        else 0
    )

    # Cloudinary bundle
    cloudinary_values = [
        creds.get("Cloudinary cloud_name", "MISSING"),
        creds.get("Cloudinary api_key", "MISSING"),
        creds.get("Cloudinary api_secret", "MISSING"),
    ]

    cloudinary_bundle = (
        "PRESENT"
        if all(value == "PRESENT" for value in cloudinary_values)
        else "MISSING"
    )

    return {
        "schema_version": 1,
        "implementation_head": report.get("implementation_head", ""),
        "origin_main": report.get("origin_main", ""),
        "overall_status": report.get("overall_status", "UNKNOWN"),
        "status_reasons": report.get("status_reasons", []),
        "sheets": {
            "passed": sheets_info.get("passed", 0),
            "total": sheets_info.get("total", 0),
            "failed_count": len(sheets_info.get("failed", [])),
            "failed_checks": sheets_info.get("failed", []),
            "posted_save_failed_count": ig.get("posted_save_failed_count", 0)
        },
        "credentials": {
            "night_threads": creds.get("night_scout Threads publish credentials", "MISSING"),
            "liver_threads": creds.get("liver_manager Threads publish credentials", "MISSING"),
            "cloudinary_bundle": cloudinary_bundle,
            "cloudinary_cloud_name": creds.get("Cloudinary cloud_name", "MISSING"),
            "cloudinary_api_key": creds.get("Cloudinary api_key", "MISSING"),
            "cloudinary_api_secret": creds.get("Cloudinary api_secret", "MISSING")
        },
        "credential_evidence": {
            "threads_status_basis": "ENV_OR_TOKEN_FILE_PRESENCE_ONLY",
            "cloudinary_status_basis": "ENV_PRESENCE_ONLY",
            "api_validity": "UNVERIFIED",
            "posting_capability": "NOT_TESTED"
        },
        "text_pipeline": {
            "night_scout": get_tp_stats("night_scout"),
            "liver_manager": get_tp_stats("liver_manager")
        },
        "no_post_reason_codes": no_post_reason_codes,
        "source_status": {
            "liver_threads_source_classification": report.get("liver_threads_source_classification", ""),
            "night_source_post_count": safe_int(night_sources.get("source_post_count")),
            "liver_source_post_count": safe_int(liver_sources.get("source_post_count")),
            "night_source_video_count": safe_int(night_sources.get("source_video_count")),
            "liver_source_video_count": safe_int(liver_sources.get("source_video_count"))
        },
        "permission_requirements": {
            "night_scout": {
                "status": night_pr.get("status", "BLOCKED"),
                "required_count": len(night_pr.get("required_source_ids", [])),
                "valid_count": len(night_pr.get("valid_source_ids", [])),
                "missing_or_invalid_count": len(night_pr.get("missing_or_invalid_source_ids", []))
            },
            "liver_manager": {
                "status": liver_pr.get("status", "BLOCKED"),
                "required_count": len(liver_pr.get("required_source_ids", [])),
                "valid_count": len(liver_pr.get("valid_source_ids", [])),
                "missing_or_invalid_count": len(liver_pr.get("missing_or_invalid_source_ids", []))
            }
        },
        "permission_warnings": permission_warnings,
        "integrity": {
            "duplicate_queue_count": len(ig.get("duplicate_queue_ids", [])),
            "duplicate_slot_key_count": len(ig.get("duplicate_slot_idempotency_keys", [])),
            "stale_inflight_slot_count": stale_slot_count,
            "unauthorized_ready_media_count": len(ig.get("unauthorized_ready_media", [])),
            "parent_integrity_failure_count": len(parent_integrity_failures_raw)
        },
        "parent_integrity": {
            "failure_count": len(parent_integrity_failures_raw),
            "reason_counts": parent_reason_counts,
            "failures": parent_integrity_failures_safe
        },
        "stale_slots": {
            "count": stale_slot_count,
            "labels": stale_slots_safe
        },
        "missing_tabs": report.get("missing_tabs", []),
        "read_errors": [{"tab": e.get("tab", ""), "error_type": e.get("error_type", "")} for e in report.get("read_errors", [])]
    }

def render_markdown_summary(summary: dict) -> str:
    md = [
        "## WP3 Read-Only Production Baseline",
        f"**Overall status**: {summary.get('overall_status')}",
        f"**Implementation HEAD**: {summary.get('implementation_head')}",
        f"**Origin main**: {summary.get('origin_main')}",
        "",
        "### Sheets checks",
        f"- passed: {summary.get('sheets', {}).get('passed')}",
        f"- total: {summary.get('sheets', {}).get('total')}",
        f"- failed count: {summary.get('sheets', {}).get('failed_count')}",
        f"- failed checks: {summary.get('sheets', {}).get('failed_checks')}",
        f"**Posted-save-failed count**: {summary.get('sheets', {}).get('posted_save_failed_count')}",
        "",
        "### Text Pipeline",
        f"**Night text READY**: {summary.get('text_pipeline', {}).get('night_scout', {}).get('ready_text_count')}",
        f"**Liver text READY**: {summary.get('text_pipeline', {}).get('liver_manager', {}).get('ready_text_count')}",
        "",
        "### Credentials & Source Status",
        f"**Credential evidence basis**: {summary.get('credential_evidence', {}).get('threads_status_basis')}",
        f"**Night Threads credential**: {summary.get('credentials', {}).get('night_threads')}",
        f"**Liver Threads credential**: {summary.get('credentials', {}).get('liver_threads')}",
        f"**Cloudinary credential status**: {summary.get('credentials', {}).get('cloudinary_bundle')}",
        f"**Liver Threads source classification**: {summary.get('source_status', {}).get('liver_threads_source_classification')}",
        "",
        "### Permissions",
        f"**Night permission status**: {summary.get('permission_requirements', {}).get('night_scout', {}).get('status')}",
        f"**Night permission missing count**: {summary.get('permission_requirements', {}).get('night_scout', {}).get('missing_or_invalid_count')}",
        f"**Liver permission status**: {summary.get('permission_requirements', {}).get('liver_manager', {}).get('status')}",
        f"**Liver permission missing count**: {summary.get('permission_requirements', {}).get('liver_manager', {}).get('missing_or_invalid_count')}",
        f"**Permission warnings**: {summary.get('permission_warnings', [])}",
        "",
        "### Integrity",
        f"**Duplicate queue count**: {summary.get('integrity', {}).get('duplicate_queue_count')}",
        f"**Duplicate slot count**: {summary.get('integrity', {}).get('duplicate_slot_key_count')}",
        f"**Stale slot count**: {summary.get('integrity', {}).get('stale_inflight_slot_count')}",
        f"**Stale slot labels**: {summary.get('stale_slots', {}).get('labels')}",
        f"**Unauthorized READY media count**: {summary.get('integrity', {}).get('unauthorized_ready_media_count')}",
        f"**Parent integrity failure count**: {summary.get('integrity', {}).get('parent_integrity_failure_count')}",
        f"**Parent integrity reason counts**: {summary.get('parent_integrity', {}).get('reason_counts')}",
        f"**Parent integrity safe details**: {summary.get('parent_integrity', {}).get('failures')}",
        "",
        "### Other",
        f"**No-post reason codes**: {summary.get('no_post_reason_codes', {})}",
        f"**Missing tabs**: {summary.get('missing_tabs', [])}",
        f"**Read errors**: {summary.get('read_errors', [])}",
        f"**Status reasons**: {summary.get('status_reasons', [])}",
        ""
    ]
    return "\n".join(md) + "\n"

def evaluate_report(report: dict, summary_path: str) -> int:
    status = report.get("overall_status")
    if status not in ["PASS", "BLOCKED", "FAIL"]:
        return 1

    safe_summary = build_safe_summary(report)
    md = render_markdown_summary(safe_summary)

    try:
        with open(summary_path, "a") as f:
            f.write(md)
    except Exception:
        pass

    print(f"WP3_SAFE_SUMMARY_JSON={json.dumps(safe_summary, ensure_ascii=False)}")

    if status == "FAIL":
        return 1
    return 0

def main():
    if len(sys.argv) < 3:
        sys.exit(1)

    json_path = sys.argv[1]
    summary_path = sys.argv[2]

    if not os.path.exists(json_path):
        sys.exit(1)

    try:
        with open(json_path, "r") as f:
            data = json.load(f)
    except Exception:
        sys.exit(1)

    ret = evaluate_report(data, summary_path)
    sys.exit(ret)

if __name__ == "__main__":
    main()
