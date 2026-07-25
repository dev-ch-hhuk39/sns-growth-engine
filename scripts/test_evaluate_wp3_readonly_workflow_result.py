#!/usr/bin/env python3
import os
import subprocess
import tempfile
import json

def run_eval(data):
    with tempfile.NamedTemporaryFile("w", delete=False) as jf, tempfile.NamedTemporaryFile("w", delete=False) as sf:
        if data is not None:
            json.dump(data, jf)
        jf.flush()
        
    cmd = ["python3", "scripts/evaluate_wp3_readonly_workflow_result.py", jf.name if data is not None else "nonexistent", sf.name]
    proc = subprocess.run(cmd, capture_output=True)
    
    if os.path.exists(sf.name):
        with open(sf.name, "r") as f:
            summary = f.read()
    else:
        summary = ""
        
    if os.path.exists(jf.name): os.unlink(jf.name)
    if os.path.exists(sf.name): os.unlink(sf.name)
        
    return proc.returncode, summary

def test_missing_json():
    code, _ = run_eval(None)
    assert code == 1

def test_malformed_json():
    with tempfile.NamedTemporaryFile("w", delete=False) as jf, tempfile.NamedTemporaryFile("w", delete=False) as sf:
        jf.write("{malformed")
        jf.flush()
        proc = subprocess.run(["python3", "scripts/evaluate_wp3_readonly_workflow_result.py", jf.name, sf.name])
        assert proc.returncode == 1
        os.unlink(jf.name)
        os.unlink(sf.name)

def test_fail():
    code, _ = run_eval({"overall_status": "FAIL"})
    assert code == 1

def test_blocked():
    code, summary = run_eval({"overall_status": "BLOCKED", "status_reasons": ["REASON1"]})
    assert code == 0
    assert "REASON1" in summary

def test_pass():
    code, _ = run_eval({"overall_status": "PASS"})
    assert code == 0

def test_unknown():
    code, _ = run_eval({"overall_status": "UNKNOWN"})
    assert code == 1

def run_all():
    test_missing_json()
    test_malformed_json()
    test_fail()
    test_blocked()
    test_pass()
    test_unknown()

if __name__ == "__main__":
    run_all()
    print("PASS")
