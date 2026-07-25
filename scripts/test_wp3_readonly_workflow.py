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

def get_base_data():
    return {
        "overall_status": "PASS",
        "status_reasons": ["REASON_X"],
        "sheets_verifier": {"passed": 5, "total": 5, "failed": []},
        "credentials": {},
        "text_pipeline": {},
        "source_inventory": {},
        "permission_requirements": {
            "night_scout": {"status": "PASS", "required_source_ids": ["a"], "valid_source_ids": ["a"], "missing_or_invalid_source_ids": []},
            "liver_manager": {"status": "BLOCKED", "required_source_ids": ["b"], "valid_source_ids": [], "missing_or_invalid_source_ids": ["b"]}
        },
        "integrity": {"duplicate_queue_ids": ["1"]},
        "missing_tabs": ["TabA"],
        "read_errors": [{"tab": "TabB", "error_type": "HttpError"}],
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

# 1. PASSでexit 0, 2. PASSでもsummary fileが生成される, 3. PASSでもstdoutへsafe summary JSONが出る, 20-24. secrets leaked
def test_eval_pass_and_secrets():
    data = get_base_data()
    code, summary, stdout = run_eval(data)
    assert code == 0
    assert summary != ""
    assert "WP3_SAFE_SUMMARY_JSON=" in stdout
    check_secrets(summary, stdout)

    # 12. permission requirement, 13. integrity count, 14. missing tabs, 15. read error
    assert "Night permission status**: PASS" in summary or "Night permission status: PASS" in summary
    assert "duplicate_queue_count" in stdout or "Duplicate queue count" in summary
    assert "TabA" in summary
    assert "TabB" in summary
    assert "HttpError" in summary

    # 11. optional field欠落
    data_missing = {"overall_status": "PASS"}
    code2, _, _ = run_eval(data_missing)
    assert code2 == 0

# 4. BLOCKEDでexit 0, 5. BLOCKED reasonがsummaryへ出る
def test_eval_blocked():
    data = get_base_data()
    data["overall_status"] = "BLOCKED"
    code, summary, stdout = run_eval(data)
    assert code == 0
    assert "REASON_X" in summary
    check_secrets(summary, stdout)

# 6. FAILでexit 1, 7. FAIL reasonがsummaryへ出る
def test_eval_fail():
    data = get_base_data()
    data["overall_status"] = "FAIL"
    code, summary, stdout = run_eval(data)
    assert code == 1
    assert "REASON_X" in summary
    check_secrets(summary, stdout)

# 8. JSON不存在でexit 1
def test_eval_missing_json():
    code, _, _ = run_eval(None)
    assert code == 1

# 9. malformed JSONでexit 1
def test_eval_malformed_json():
    code, _, _ = run_eval("{malformed")
    assert code == 1

# 10. unknown statusでexit 1
def test_eval_unknown_status():
    data = get_base_data()
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

    test_eval_pass_and_secrets()
    test_eval_blocked()
    test_eval_fail()
    test_eval_missing_json()
    test_eval_malformed_json()
    test_eval_unknown_status()

if __name__ == "__main__":
    run_all()
    print("PASS")
