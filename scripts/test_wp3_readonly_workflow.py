#!/usr/bin/env python3
import os
import yaml
import sys
import subprocess
import tempfile
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WF_PATH = os.path.join(ROOT, ".github", "workflows", "wp3-production-readonly-verification.yml")

with open(WF_PATH, "r") as f:
    workflow = yaml.safe_load(f)

with open(WF_PATH, "r") as f:
    workflow_text = f.read()

def test_workflow_dispatch_only():
    on_key = True if True in workflow else "on"
    assert on_key in workflow
    assert "workflow_dispatch" in workflow[on_key]
    assert "schedule" not in workflow[on_key]
    assert "push" not in workflow[on_key]

def test_permissions_read_only():
    assert workflow.get("permissions", {}).get("contents") == "read"

def test_production_environment():
    job = workflow["jobs"]["readonly_verification"]
    assert job.get("environment") == "production"

def test_python_3_11():
    job = workflow["jobs"]["readonly_verification"]
    for step in job["steps"]:
        if step.get("uses", "").startswith("actions/setup-python"):
            assert step.get("with", {}).get("python-version") == "3.11"
            return
    assert False, "Python setup step not found"

def test_safety_flags_false_in_workflow_scope():
    env = workflow.get("env", {})
    flags = [
        "PUBLISH_ENABLED", "ALLOW_REAL_THREADS_POST", "ALLOW_REAL_X_POST",
        "ALLOW_VIDEO_DOWNLOAD", "ALLOW_VIDEO_CUT", "ALLOW_CLOUDINARY_UPLOAD",
        "ALLOW_MEDIA_POSTS", "ALLOW_REAL_THREADS_VIDEO_POST", "ALLOW_TRANSCRIPTION_API"
    ]
    for flag in flags:
        assert str(env.get(flag)).lower() == "false"

def test_job_env_credentials_only():
    job = workflow["jobs"]["readonly_verification"]
    env = job.get("env", {})
    assert "SNS_MASTER_SHEET_ID" in env
    assert "SA_JSON_BASE64" in env
    assert "SPREADSHEET_ID" in env
    assert "GCP_SA_JSON_BASE64" in env

    flags = [
        "PUBLISH_ENABLED", "ALLOW_REAL_THREADS_POST", "ALLOW_REAL_X_POST"
    ]
    for flag in flags:
        assert flag not in env

def test_no_banned_commands():
    banned = [
        "acquire_approved_source_posts.py",
        "reconcile_production_integrity.py",
        "threads_publisher.py",
        "transcribe",
        "ffmpeg",
        "--confirm",
        "echo $SA_JSON_BASE64",
        "echo $SNS_MASTER_SHEET_ID"
    ]
    for b in banned:
        assert b not in workflow_text, f"Found banned string: {b}"

def test_collector_called_once():
    assert workflow_text.count("collect_wp3_readonly_evidence.py") == 1


def run_eval(data):
    import tempfile
    import json
    import subprocess
    with tempfile.NamedTemporaryFile("w", delete=False) as jf, tempfile.NamedTemporaryFile("w", delete=False) as sf:
        if data is not None:
            if isinstance(data, str):
                jf.write(data)
            else:
                json.dump(data, jf)
        jf.flush()

    cmd = ["python3", "scripts/evaluate_wp3_readonly_workflow_result.py", jf.name if data is not None else "nonexistent", sf.name]
    proc = subprocess.run(cmd, capture_output=True, text=True)

    if os.path.exists(sf.name):
        with open(sf.name, "r") as f:
            summary = f.read()
    else:
        summary = ""

    if os.path.exists(jf.name): os.unlink(jf.name)
    if os.path.exists(sf.name): os.unlink(sf.name)

    return proc.returncode, summary, proc.stdout

def get_collector_shaped_data():
    return {
        "implementation_head": "HEAD_SHA",
        "origin_main": "MAIN_SHA",
        "overall_status": "BLOCKED",
        "status_reasons": [
            "REQUIRED_PERMISSION_MISSING_LIVER_MANAGER"
        ],
        "sheets_verifier": {
            "passed": 63,
            "total": 63,
            "failed": [],
        },
        "credentials": {
            "night_scout Threads publish credentials": "PRESENT",
            "liver_manager Threads publish credentials": "MISSING",
            "Cloudinary cloud_name": "PRESENT",
            "Cloudinary api_key": "PRESENT",
            "Cloudinary api_secret": "PRESENT",
        },
        "text_pipeline": {
            "night_scout": {
                "ready_text_count": 3,
                "waiting_review_count": 2,
                "processing_count": 1,
                "posted_text_count": 10,
                "no_post_reasons": {
                    "NO_ELIGIBLE_CANDIDATE": 2
                },
            },
            "liver_manager": {
                "ready_text_count": 4,
                "waiting_review_count": 5,
                "processing_count": 6,
                "posted_text_count": 7,
                "no_post_reasons": {},
            },
        },
        "source_inventory": {
            "night_scout": {
                "source_post_count": 11,
                "source_video_count": 12,
            },
            "liver_manager": {
                "source_post_count": 13,
                "source_video_count": 14,
            },
        },
        "permission_requirements": {
            "night_scout": {
                "status": "PASS",
                "required_source_ids": ["source_night"],
                "valid_source_ids": ["source_night"],
                "missing_or_invalid_source_ids": [],
            },
            "liver_manager": {
                "status": "BLOCKED",
                "required_source_ids": ["source_liver"],
                "valid_source_ids": [],
                "missing_or_invalid_source_ids": ["source_liver"],
            },
        },
        "integrity": {
            "posted_save_failed_count": 0,
            "duplicate_queue_ids": ["q1", "q2"],
            "duplicate_slot_idempotency_keys": ["slot1"],
            "stale_inflight_slots": ["stale1", "stale2", "stale3"],
            "unauthorized_ready_media": ["media1"],
            "parent_integrity_failures": ["parent1", "parent2"],
        },
        "missing_tabs": [],
        "read_errors": [],
        "liver_threads_source_classification": "FOUND_UNAPPROVED",
        "TEST_SOURCE_URL_SECRET": "https://source.url/secret",
        "TEST_MEDIA_URL_SECRET": "https://media.url/secret",
        "TEST_POST_TEXT_SECRET": "secret_text",
        "TEST_TRANSCRIPT_SECRET": "secret_transcript",
        "TEST_ACCESS_TOKEN_SECRET": "secret_token",
        "TEST_REFRESH_TOKEN_SECRET": "secret_refresh",
        "TEST_COOKIE_SECRET": "secret_cookie",
        "TEST_API_SECRET_SECRET": "secret_api",
        "TEST_SA_JSON_SECRET": "secret_json",
        "TEST_EVIDENCE_REFERENCE_SECRET": "secret_ref",
        "TEST_RAW_PAYLOAD_SECRET": "secret_payload"
    }

def check_secrets(summary, stdout):
    secrets = [
        "https://source.url/secret", "https://media.url/secret", "secret_text", "secret_transcript",
        "secret_token", "secret_refresh", "secret_cookie", "secret_api", "secret_json", "secret_ref", "secret_payload"
    ]
    for s in secrets:
        assert s not in summary, f"Secret leaked in summary: {s}"
        assert s not in stdout, f"Secret leaked in stdout: {s}"

def test_evaluator_schema_alignment():
    data = get_collector_shaped_data()
    code, summary, stdout = run_eval(data)
    assert code == 0
    assert summary != ""
    assert "WP3_SAFE_SUMMARY_JSON=" in stdout
    check_secrets(summary, stdout)

    import json
    for line in stdout.split("\n"):
        if line.startswith("WP3_SAFE_SUMMARY_JSON="):
            safe_summary = json.loads(line.replace("WP3_SAFE_SUMMARY_JSON=", ""))
            break

    assert safe_summary["credentials"]["night_threads"] == "PRESENT"
    assert safe_summary["credentials"]["liver_threads"] == "MISSING"
    assert safe_summary["credentials"]["cloudinary_cloud_name"] == "PRESENT"
    assert safe_summary["credentials"]["cloudinary_api_key"] == "PRESENT"
    assert safe_summary["credentials"]["cloudinary_api_secret"] == "PRESENT"

    assert safe_summary["text_pipeline"]["night_scout"]["ready_text_count"] == 3
    assert safe_summary["text_pipeline"]["night_scout"]["waiting_review_count"] == 2
    assert safe_summary["text_pipeline"]["night_scout"]["processing_count"] == 1
    assert safe_summary["text_pipeline"]["night_scout"]["posted_text_count"] == 10

    assert safe_summary["text_pipeline"]["liver_manager"]["ready_text_count"] == 4
    assert safe_summary["text_pipeline"]["liver_manager"]["waiting_review_count"] == 5
    assert safe_summary["text_pipeline"]["liver_manager"]["processing_count"] == 6
    assert safe_summary["text_pipeline"]["liver_manager"]["posted_text_count"] == 7

    assert safe_summary["source_status"]["night_source_post_count"] == 11
    assert safe_summary["source_status"]["night_source_video_count"] == 12
    assert safe_summary["source_status"]["liver_source_post_count"] == 13
    assert safe_summary["source_status"]["liver_source_video_count"] == 14

    assert safe_summary["integrity"]["duplicate_queue_count"] == 2
    assert safe_summary["integrity"]["duplicate_slot_key_count"] == 1
    assert safe_summary["integrity"]["stale_inflight_slot_count"] == 3
    assert safe_summary["integrity"]["unauthorized_ready_media_count"] == 1
    assert safe_summary["integrity"]["parent_integrity_failure_count"] == 2

    # Check Markdown newline
    assert "\n" in summary
    assert "\\n" not in summary
    assert "## WP3 Read-Only Production Baseline\n" in summary

def test_collector_integration():
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from collect_wp3_readonly_evidence import run_collector
    from test_collect_wp3_readonly_evidence import fake_client_factory, _run_with_mocks, MockArgs

    # Run collector to get full report
    report = _run_with_mocks(fake_client_factory(), MockArgs())

    # Evaluate it
    code, summary, stdout = run_eval(report)
    assert code == 0

    import json
    for line in stdout.split("\n"):
        if line.startswith("WP3_SAFE_SUMMARY_JSON="):
            safe_summary = json.loads(line.replace("WP3_SAFE_SUMMARY_JSON=", ""))
            break

    assert "night_threads" in safe_summary["credentials"]
    assert "ready_text_count" in safe_summary["text_pipeline"]["night_scout"]
    assert "night_source_post_count" in safe_summary["source_status"]
    assert "status" in safe_summary["permission_requirements"]["night_scout"]

    assert isinstance(safe_summary["integrity"]["duplicate_queue_count"], int)

    check_secrets(summary, stdout)

def test_eval_missing_json():
    code, _, _ = run_eval(None)
    assert code == 1

def test_eval_malformed_json():
    code, _, _ = run_eval("{malformed")
    assert code == 1

def test_eval_unknown_status():
    data = get_collector_shaped_data()
    data["overall_status"] = "UNKNOWN_STATUS"
    code, _, _ = run_eval(data)
    assert code == 1

def test_workflow_no_cat_or_echo_full():
    with open(WF_PATH, "r") as f:
        text = f.read()
    assert "cat /tmp/wp3_evidence.json" not in text
    assert "echo $WP3_EVIDENCE" not in text
    assert "actions/upload-artifact" not in text

def run_all():
    test_workflow_dispatch_only()
    test_permissions_read_only()
    test_production_environment()
    test_python_3_11()
    test_safety_flags_false_in_workflow_scope()
    test_job_env_credentials_only()
    test_no_banned_commands()
    test_collector_called_once()
    test_workflow_no_cat_or_echo_full()

    test_evaluator_schema_alignment()
    test_collector_integration()
    test_eval_missing_json()
    test_eval_malformed_json()
    test_eval_unknown_status()

if __name__ == "__main__":
    run_all()
    print("PASS")
