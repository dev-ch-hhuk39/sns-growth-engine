#!/usr/bin/env python3
import sys
import json
import os

def build_safe_summary(report: dict) -> dict:
    sheets_info = report.get("sheets_verifier", {})
    creds = report.get("credentials", {})
    tp = report.get("text_pipeline", {})
    si = report.get("source_inventory", {})
    pr = report.get("permission_requirements", {})
    ig = report.get("integrity", {})

    def get_tp_stats(acc):
        acc_tp = tp.get(acc, {})
        if not acc_tp: return {"ready_text_count": 0, "waiting_review_count": 0, "processing_count": 0, "posted_text_count": 0, "no_post_reasons": {}}
        return {
            "ready_text_count": len(acc_tp.get("ready", [])),
            "waiting_review_count": len(acc_tp.get("waiting_review", [])),
            "processing_count": len(acc_tp.get("processing", [])),
            "posted_text_count": len(acc_tp.get("posted", [])),
            "no_post_reasons": acc_tp.get("no_post_reasons", {})
        }

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
            "night_threads": creds.get("night_scout_threads", "MISSING"),
            "liver_threads": creds.get("liver_manager_threads", "MISSING"),
            "cloudinary_cloud_name": creds.get("cloudinary_cloud_name", "MISSING"),
            "cloudinary_api_key": creds.get("cloudinary_api_key", "MISSING"),
            "cloudinary_api_secret": creds.get("cloudinary_api_secret", "MISSING")
        },
        "text_pipeline": {
            "night_scout": get_tp_stats("night_scout"),
            "liver_manager": get_tp_stats("liver_manager")
        },
        "source_status": {
            "liver_threads_source_classification": report.get("liver_threads_source_classification", ""),
            "night_source_post_count": si.get("night_source_posts_count", 0),
            "liver_source_post_count": si.get("liver_source_posts_count", 0),
            "night_source_video_count": si.get("night_source_videos_count", 0),
            "liver_source_video_count": si.get("liver_source_videos_count", 0)
        },
        "permission_requirements": {
            "night_scout": {
                "status": pr.get("night_scout", {}).get("status", "BLOCKED"),
                "required_count": len(pr.get("night_scout", {}).get("required_source_ids", [])),
                "valid_count": len(pr.get("night_scout", {}).get("valid_source_ids", [])),
                "missing_or_invalid_source_ids": pr.get("night_scout", {}).get("missing_or_invalid_source_ids", [])
            },
            "liver_manager": {
                "status": pr.get("liver_manager", {}).get("status", "BLOCKED"),
                "required_count": len(pr.get("liver_manager", {}).get("required_source_ids", [])),
                "valid_count": len(pr.get("liver_manager", {}).get("valid_source_ids", [])),
                "missing_or_invalid_source_ids": pr.get("liver_manager", {}).get("missing_or_invalid_source_ids", [])
            }
        },
        "integrity": {
            "duplicate_queue_count": len(ig.get("duplicate_queue_ids", [])),
            "duplicate_slot_key_count": len(ig.get("duplicate_slot_idempotency_keys", [])),
            "stale_inflight_slot_count": len(ig.get("stale_inflight_slots", [])),
            "unauthorized_ready_media_count": len(ig.get("unauthorized_ready_media", [])),
            "parent_integrity_failure_count": len(ig.get("parent_integrity_failures", []))
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
        f"**Night Threads credential**: {summary.get('credentials', {}).get('night_threads')}",
        f"**Liver Threads credential**: {summary.get('credentials', {}).get('liver_threads')}",
        f"**Liver Threads source classification**: {summary.get('source_status', {}).get('liver_threads_source_classification')}",
        "",
        "### Permissions",
        f"**Night permission status**: {summary.get('permission_requirements', {}).get('night_scout', {}).get('status')}",
        f"**Liver permission status**: {summary.get('permission_requirements', {}).get('liver_manager', {}).get('status')}",
        "",
        "### Integrity",
        f"**Duplicate queue count**: {summary.get('integrity', {}).get('duplicate_queue_count')}",
        f"**Duplicate slot count**: {summary.get('integrity', {}).get('duplicate_slot_key_count')}",
        f"**Stale slot count**: {summary.get('integrity', {}).get('stale_inflight_slot_count')}",
        f"**Unauthorized READY media count**: {summary.get('integrity', {}).get('unauthorized_ready_media_count')}",
        f"**Parent integrity failure count**: {summary.get('integrity', {}).get('parent_integrity_failure_count')}",
        "",
        "### Other",
        f"**Missing tabs**: {summary.get('missing_tabs', [])}",
        f"**Read errors**: {summary.get('read_errors', [])}",
        f"**Status reasons**: {summary.get('status_reasons', [])}",
        ""
    ]
    return "\\n".join(md)

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
