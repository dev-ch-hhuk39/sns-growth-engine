#!/usr/bin/env python3
import os
import yaml
import sys

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

def test_exit_codes_handled():
    assert 'exit 1' in workflow_text
    assert 'exit 0' in workflow_text
    
    assert '"$status" = "FAIL"' in workflow_text or 'status == "FAIL"' in workflow_text
    assert '"$status" = "BLOCKED"' in workflow_text or 'status == "BLOCKED"' in workflow_text
    assert '"$status" = "PASS"' in workflow_text or 'status == "PASS"' in workflow_text

def run_all():
    test_workflow_dispatch_only()
    test_permissions_read_only()
    test_production_environment()
    test_python_3_11()
    test_safety_flags_false_in_workflow_scope()
    test_job_env_credentials_only()
    test_no_banned_commands()
    test_collector_called_once()
    test_exit_codes_handled()

if __name__ == "__main__":
    run_all()
    print("PASS")
