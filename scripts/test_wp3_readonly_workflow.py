import os
import yaml
import pytest

def test_workflow_properties():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    wf_path = os.path.join(root, ".github", "workflows", "wp3-production-readonly-verification.yml")
    
    with open(wf_path, "r") as f:
        wf = yaml.safe_load(f)
        
    on_clause = wf.get("on", wf.get(True, {}))
    assert "workflow_dispatch" in on_clause
    assert "schedule" not in on_clause
    assert wf.get("permissions", {}).get("contents") == "read"
    
    job = wf.get("jobs", {}).get("verify", {})
    assert job.get("environment") == "production"
    
    env = job.get("env", {})
    flags = [
        "PUBLISH_ENABLED", "ALLOW_REAL_THREADS_POST", "ALLOW_REAL_X_POST",
        "ALLOW_VIDEO_DOWNLOAD", "ALLOW_VIDEO_CUT", "ALLOW_CLOUDINARY_UPLOAD",
        "ALLOW_MEDIA_POSTS", "ALLOW_REAL_THREADS_VIDEO_POST", "ALLOW_TRANSCRIPTION_API"
    ]
    for flag in flags:
        assert env.get(flag) == "false"
        
    # Check steps
    steps = job.get("steps", [])
    script_calls = "\n".join([str(s.get("run", "")) for s in steps])
    
    assert "collect_wp3_readonly_evidence.py" in script_calls
    assert "research" not in script_calls
    assert "account_acquisition" not in script_calls
    assert "reconcile" not in script_calls
    assert "publisher" not in script_calls
    
    assert "--confirm-real-post" not in script_calls
    assert "--confirm-upload" not in script_calls
    assert "--confirm-download" not in script_calls
    assert "--confirm-cut" not in script_calls
    
    assert "echo ${{ secrets." not in script_calls
    assert "exit 1" in script_calls # Hard Failure Gate
