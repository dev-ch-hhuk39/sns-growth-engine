#!/usr/bin/env python3
"""Goal evaluation must reject missing and stale evidence, then accept a complete fixture."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from evaluate_goal import ACCEPTANCE, evaluate  # noqa: E402

acceptance = json.loads(ACCEPTANCE.read_text(encoding="utf-8"))


def fixture(*, head: str, missing: bool = False) -> dict:
    criteria = {}
    for criterion in acceptance["criteria"]:
        evidence = {name: "fixture" for name in criterion["requires"]}
        if criterion["id"] == "origin_main_matches":
            evidence = {"head": head, "origin_main": head}
        criteria[criterion["id"]] = {"status": "PASS", "evidence": evidence}
    if missing:
        criteria["repository_public"]["evidence"].pop("visibility_checked_at")
    return {"implementation_head": head, "criteria": criteria}


with tempfile.TemporaryDirectory() as temp:
    path = Path(temp) / "status.json"
    path.write_text(json.dumps(fixture(head="fixture-head", missing=True)), encoding="utf-8")
    missing_result = evaluate(status_path=path, current_head="fixture-head", current_origin_main="fixture-head")
    assert missing_result["status"] == "FAIL"
    assert any(row["id"] == "repository_public" for row in missing_result["failed"])

    path.write_text(json.dumps(fixture(head="stale-head")), encoding="utf-8")
    stale_result = evaluate(status_path=path, current_head="fixture-head", current_origin_main="fixture-head")
    assert stale_result["status"] == "FAIL"
    assert any(row["id"] == "evidence_scope" for row in stale_result["failed"])

    path.write_text(json.dumps(fixture(head="fixture-head")), encoding="utf-8")
    pass_result = evaluate(status_path=path, current_head="fixture-head", current_origin_main="fixture-head")
    assert pass_result["status"] == "PASS" and pass_result["passed"] == 35

print("PASS test_goal_evidence_fail_closed.py")
