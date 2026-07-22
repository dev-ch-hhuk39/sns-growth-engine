#!/usr/bin/env python3
"""Fail closed unless every required production criterion has evidence."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ACCEPTANCE = ROOT / "config" / "goal_acceptance.json"
STATUS = ROOT / "docs" / "goal-status.json"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, text=True, capture_output=True, check=False
    ).stdout.strip()


def evaluate(
    *,
    acceptance_path: Path = ACCEPTANCE,
    status_path: Path = STATUS,
    current_head: str | None = None,
    current_origin_main: str | None = None,
) -> dict[str, Any]:
    acceptance = _load(acceptance_path)
    state = _load(status_path)
    recorded = state.get("criteria", {})
    failures: list[dict[str, Any]] = []
    passed: list[str] = []

    for criterion in acceptance.get("criteria", []):
        criterion_id = str(criterion["id"])
        row = recorded.get(criterion_id, {})
        status = str(row.get("status", "EVIDENCE_MISSING"))
        evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
        missing = [name for name in criterion.get("requires", []) if evidence.get(name) in (None, "", [], {})]
        if status != acceptance.get("passing_status", "PASS") or missing:
            failures.append({"id": criterion_id, "status": status, "missing_evidence": missing})
        else:
            passed.append(criterion_id)

    dynamic: dict[str, Any] = {}
    workflow_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    )
    dynamic["self_hosted_workflow_references"] = workflow_text.count("self-hosted")
    dynamic["vps_workflow_references"] = workflow_text.lower().count("xserver")
    dynamic["working_tree_clean"] = not bool(_git("status", "--short"))
    dynamic["head"] = current_head if current_head is not None else _git("rev-parse", "HEAD")
    dynamic["origin_main"] = current_origin_main if current_origin_main is not None else _git("rev-parse", "origin/main")

    # PASS evidence is only valid for the exact commit it describes.  The
    # planning documents are useful context, but can never promote a Goal.
    scope_head = str(state.get("implementation_head") or "")
    if any(str(row.get("status")) == acceptance.get("passing_status", "PASS") for row in recorded.values()):
        if not scope_head:
            failures.append({"id": "evidence_scope", "status": "FAIL", "missing_evidence": ["implementation_head"]})
        elif scope_head != dynamic["head"]:
            failures.append({"id": "evidence_scope", "status": "FAIL", "missing_evidence": ["commit_sha_mismatch"]})

    if recorded.get("github_hosted_only", {}).get("status") == "PASS" and dynamic["self_hosted_workflow_references"]:
        failures.append({"id": "github_hosted_only", "status": "FAIL", "missing_evidence": ["static_workflow_scan_failed"]})
    if recorded.get("no_vps_or_self_hosted_dependency", {}).get("status") == "PASS" and (
        dynamic["self_hosted_workflow_references"] or dynamic["vps_workflow_references"]
    ):
        failures.append({"id": "no_vps_or_self_hosted_dependency", "status": "FAIL", "missing_evidence": ["static_dependency_scan_failed"]})
    origin_evidence = recorded.get("origin_main_matches", {}).get("evidence", {})
    if recorded.get("origin_main_matches", {}).get("status") == "PASS" and (
        str(origin_evidence.get("head") or "") != dynamic["head"]
        or str(origin_evidence.get("origin_main") or "") != dynamic["origin_main"]
    ):
        failures.append({"id": "origin_main_matches", "status": "FAIL", "missing_evidence": ["final_main_sha_mismatch"]})

    unique_failures = {item["id"]: item for item in failures}
    return {
        "status": "PASS" if not unique_failures else "FAIL",
        "passed": len(passed),
        "required": len(acceptance.get("criteria", [])),
        "failed": list(unique_failures.values()),
        "dynamic": dynamic,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--status-file", type=Path, default=STATUS)
    args = parser.parse_args()
    result = evaluate(status_path=args.status_file)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"goal_status={result['status']} passed={result['passed']}/{result['required']}")
        for item in result["failed"]:
            print(f"FAIL {item['id']}: status={item['status']} missing={','.join(item['missing_evidence']) or '-'}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
