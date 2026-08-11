#!/usr/bin/env python3
from pathlib import Path

from evaluate_reference_first_completion import evaluate

ROOT = Path(__file__).resolve().parents[1]
evaluator_source = (ROOT / "scripts/evaluate_reference_first_completion.py").read_text(encoding="utf-8")
assert ".codex-owner-context" not in evaluator_source

def artifact(test_count: int, failed_count: int = 0):
    return {
        "status": "PASS" if failed_count == 0 else "FAIL",
        "test_count": test_count,
        "failed_count": failed_count,
        "excluded_external_probe_count": 8,
        "excluded_optional_local_tool_count": 3,
    }


result = evaluate(repository_tests_result=artifact(818))
assert result["status"] == "PASS", result
assert result["completion_status"] == "SOFTWARE_COMPLETE_EXTERNAL_BLOCKERS_ONLY", result
assert result["software_complete"] is True
assert result["integration_complete"] is True
assert result["production_evidence_complete"] is False
assert result["architecture_consistent"]["status"] == "PASS"
assert result["x_physical_media_ready"]["code_ready"] is True
assert result["x_physical_media_ready"]["permission_blocker"] is True
assert result["production_write_approval_external_blocker"]["blocker"] is True

bad = evaluate(repository_tests_result=artifact(814))
assert bad["status"] == "FAIL", bad
assert bad["software_complete"] is False

print("PASS test_reference_first_completion_evaluator.py")
