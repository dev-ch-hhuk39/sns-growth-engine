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

def parse_safe_summary(stdout: str) -> dict:
    for line in stdout.splitlines():
        if line.startswith("WP3_SAFE_SUMMARY_JSON="):
            return json.loads(line.removeprefix("WP3_SAFE_SUMMARY_JSON="))
    raise AssertionError("safe summary JSON was not emitted")

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
    assert "THREADS_ACCESS_TOKEN_NIGHT_SCOUT" in env
    assert "THREADS_USER_ID_NIGHT_SCOUT" in env
    assert "THREADS_ACCESS_TOKEN_LIVER_MANAGER" in env
    assert "THREADS_USER_ID_LIVER_MANAGER" in env
    assert "CLOUDINARY_CLOUD_NAME" in env
    assert "CLOUDINARY_API_KEY" in env
    assert "CLOUDINARY_API_SECRET" in env

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
        "echo $SNS_MASTER_SHEET_ID",
        'echo "$THREADS',
        'echo "$CLOUDINARY'
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
                    "stale_slot_claim_requires_explicit_recovery": 2,
                    "RuntimeError 123": 1
                },
            },
            "liver_manager": {
                "ready_text_count": 4,
                "waiting_review_count": 5,
                "processing_count": 6,
                "posted_text_count": 7,
                "no_post_reasons": {
                    "EMPTY_TEXT": 1,
                    "some unknown reason": 2
                },
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
                "status": "PASS",
                "required_source_ids": ["source_liver", "missing_src"],
                "valid_source_ids": ["source_liver"],
                "missing_or_invalid_source_ids": ["missing_src"],
            },
        },
        "integrity": {
            "posted_save_failed_count": 0,
            "duplicate_queue_ids": ["q1", "q2"],
            "duplicate_slot_idempotency_keys": ["slot1"],
            "stale_inflight_slots": [
                "stale1",
                "stale2"
            ],
            "unauthorized_ready_media": ["media1"],
            "parent_integrity_failures": [
                {"id": "p1", "reason": "PARENT_NOT_FOUND", "account_id": "night_scout", "url": "https://media.url/secret"},
                {"id": "p2", "reason": "UNKNOWN_STRANGE_REASON", "account_id": "liver_manager", "raw": "secret_payload"}
            ],
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

    safe_summary = parse_safe_summary(stdout)

    assert safe_summary["credentials"]["night_threads"] == "PRESENT"
    assert safe_summary["credentials"]["liver_threads"] == "MISSING"
    assert safe_summary["credentials"]["cloudinary_bundle"] == "PRESENT"
    
    assert safe_summary["credential_evidence"]["threads_status_basis"] == "ENV_OR_TOKEN_FILE_PRESENCE_ONLY"

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
    assert safe_summary["integrity"]["stale_inflight_slot_count"] == 2
    assert safe_summary["integrity"]["unauthorized_ready_media_count"] == 1
    assert safe_summary["integrity"]["parent_integrity_failure_count"] == 2
    
    assert safe_summary["parent_integrity"]["failure_count"] == 2
    assert safe_summary["parent_integrity"]["failures"][0]["reason"] == "PARENT_NOT_FOUND"
    assert safe_summary["parent_integrity"]["failures"][1]["reason"] == "UNKNOWN_PARENT_INTEGRITY_FAILURE"
    
    assert safe_summary["stale_slots"]["count"] == 2
    assert "stale1" in safe_summary["stale_slots"]["slot_run_ids"]
    assert "stale2" in safe_summary["stale_slots"]["slot_run_ids"]
    
    assert "LIVER_HAS_PARTIAL_PERMISSION_COVERAGE" in safe_summary["permission_warnings"]
    assert "NIGHT_HAS_PARTIAL_PERMISSION_COVERAGE" not in safe_summary["permission_warnings"]
    
    assert safe_summary["no_post_reason_codes"]["night_scout"]["STALE_SLOT_REQUIRES_RECOVERY"] == 2
    assert safe_summary["no_post_reason_codes"]["night_scout"]["THREADS_API_RUNTIME_ERROR"] == 1
    assert safe_summary["no_post_reason_codes"]["liver_manager"]["EMPTY_TEXT"] == 1
    assert safe_summary["no_post_reason_codes"]["liver_manager"]["OTHER_REDACTED"] == 2

    assert "Parent integrity reason counts" in summary
    assert "## WP3 Read-Only Production Baseline\n" in summary
    assert "\\n" not in summary
    assert summary.count("\n") > 5

    data2 = get_collector_shaped_data()
    data2["credentials"]["Cloudinary api_secret"] = "MISSING"
    _, _, stdout2 = run_eval(data2)
    safe_summary2 = parse_safe_summary(stdout2)
    assert safe_summary2["credentials"]["cloudinary_bundle"] == "MISSING"

def test_parent_integrity_full_count_and_safe_detail_limit():
    data = get_collector_shaped_data()

    failures = []
    for index in range(55):
        failures.append({
            "id": f"parent_{index}",
            "reason": (
                "PARENT_NOT_FOUND"
                if index < 52
                else "UNSAFE_UNKNOWN_REASON"
            ),
            "account_id": (
                "night_scout"
                if index % 2 == 0
                else "liver_manager"
            ),
            "url": "TEST_PARENT_SECRET_URL",
            "raw": "TEST_PARENT_RAW_SECRET",
            "notes": "TEST_PARENT_NOTES_SECRET",
            "evidence_reference": "TEST_EVIDENCE_SECRET",
        })

    data["integrity"]["parent_integrity_failures"] = failures

    code, summary, stdout = run_eval(data)
    assert code == 0

    safe_summary = parse_safe_summary(stdout)

    assert safe_summary["parent_integrity"]["failure_count"] == 55
    assert len(safe_summary["parent_integrity"]["failures"]) == 50
    assert (
        sum(
            safe_summary["parent_integrity"]["reason_counts"].values()
        )
        == 55
    )
    assert (
        safe_summary["parent_integrity"]["reason_counts"][
            "PARENT_NOT_FOUND"
        ]
        == 52
    )
    assert (
        safe_summary["parent_integrity"]["reason_counts"][
            "UNKNOWN_PARENT_INTEGRITY_FAILURE"
        ]
        == 3
    )

    for secret in (
        "TEST_PARENT_SECRET_URL",
        "TEST_PARENT_RAW_SECRET",
        "TEST_PARENT_NOTES_SECRET",
        "TEST_EVIDENCE_SECRET",
    ):
        assert secret not in summary
        assert secret not in stdout

def test_extract_stale_slot_ids_contract():
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from evaluate_wp3_readonly_workflow_result import (
        extract_stale_slot_ids,
    )

    values = [
        "slot_1",
        "slot_1",
        "",
        {"slot_run_id": "slot_2"},
        {
            "slot_run_id": "slot_3",
            "url": "TEST_STALE_URL_SECRET",
            "lease_expires_at": "TEST_STALE_TIME_SECRET",
        },
    ] + [f"slot_{index}" for index in range(4, 30)]

    result = extract_stale_slot_ids(values)

    assert result[0] == "slot_1"
    assert "slot_2" in result
    assert "slot_3" in result
    assert len(result) <= 20
    assert len(result) == len(set(result))
    assert "" not in result
    assert extract_stale_slot_ids("invalid") == []

    # Also test via run_eval to ensure schema matches
    data = get_collector_shaped_data()
    data["integrity"]["stale_inflight_slots"] = values
    code, summary, stdout = run_eval(data)
    assert code == 0

    safe_summary = parse_safe_summary(stdout)
    assert safe_summary["stale_slots"]["count"] == len(values)
    assert len(safe_summary["stale_slots"]["slot_run_ids"]) <= 20
    
    assert "TEST_STALE_URL_SECRET" not in summary
    assert "TEST_STALE_URL_SECRET" not in stdout
    assert "TEST_STALE_TIME_SECRET" not in summary
    assert "TEST_STALE_TIME_SECRET" not in stdout


def test_collector_integration():
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from collect_wp3_readonly_evidence import run_collector
    from test_collect_wp3_readonly_evidence import fake_client_factory, _run_with_mocks, MockArgs

    # Prepare database to inject stale slots and parent integrity failures
    db = {
        "content_slot_runs": [
            {"slot_run_id": "stale_run_1", "status": "RUNNING", "lease_expires_at": "2000-01-01T00:00:00Z"},
            {"slot_run_id": "stale_run_2", "status": "RUNNING", "lease_expires_at": "2000-01-01T00:00:00Z"},
            {"account_id": "night_scout", "no_post_reason": "R1"},
        ],
        "source_post_media": [
            {"source_post_id": "p1", "media_index": "1"} # Missing parent
        ],
        "media_permissions": [
            {"source_id": "s1", "permission_status": "approved", "rights_status": "allowed", "evidence_type": "x", "evidence_reference": "y", "allow_analysis": "true", "allow_transcription": "true"}
        ],
        "source_accounts": [
            {"source_id": "s1", "platform": "youtube", "target_account_id": "night_scout", "source_url": "u", "active": "true", "blocked": "false", "review_status": "APPROVED"}
        ]
    }

    # Run collector to get full report
    report = _run_with_mocks(fake_client_factory(db), MockArgs())

    report["permission_requirements"]["liver_manager"] = {
        "status": "PASS",
        "required_source_ids": ["s2"],
        "valid_source_ids": [],
        "missing_or_invalid_source_ids": ["s2"],
    }
    report["overall_status"] = "PASS"

    # Evaluate it
    code, summary, stdout = run_eval(report)
    assert code == 0

    safe_summary = parse_safe_summary(stdout)

    assert safe_summary["credentials"]["night_threads"] == "PRESENT"
    assert safe_summary["text_pipeline"]["night_scout"]["ready_text_count"] == 0
    assert safe_summary["source_status"]["night_source_post_count"] == 0
    
    assert safe_summary["integrity"]["duplicate_queue_count"] == 0
    
    # Assert concrete parent failure integration
    assert safe_summary["parent_integrity"]["failure_count"] == 1
    assert safe_summary["parent_integrity"]["failures"][0]["reason"] == "PARENT_NOT_FOUND"
    assert safe_summary["parent_integrity"]["failures"][0]["id"] == "p1"
    assert "url" not in safe_summary["parent_integrity"]["failures"][0]
    assert "raw" not in safe_summary["parent_integrity"]["failures"][0]
    assert safe_summary["parent_integrity"]["reason_counts"]["PARENT_NOT_FOUND"] == 1

    # Assert concrete stale slot integration
    assert safe_summary["stale_slots"]["count"] == 2
    assert "stale_run_1" in safe_summary["stale_slots"]["slot_run_ids"]
    assert "stale_run_2" in safe_summary["stale_slots"]["slot_run_ids"]
    assert isinstance(safe_summary["stale_slots"]["slot_run_ids"], list)

    # Assert fixed codes for no-post reason
    assert safe_summary["no_post_reason_codes"]["night_scout"]["OTHER_REDACTED"] == 1
    
    # Assert permission warnings
    assert "LIVER_HAS_PARTIAL_PERMISSION_COVERAGE" in safe_summary["permission_warnings"]

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
    test_parent_integrity_full_count_and_safe_detail_limit()
    test_extract_stale_slot_ids_contract()
    test_collector_integration()
    
    test_eval_missing_json()
    test_eval_malformed_json()
    test_eval_unknown_status()

if __name__ == "__main__":
    run_all()
    print("PASS")
