#!/usr/bin/env python3
"""Fail closed unless every account capability has production evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "production_capability_matrix.json"
STATUS = ROOT / "docs" / "capability-matrix-status.json"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate(*, config_path: Path = CONFIG, status_path: Path = STATUS) -> dict[str, Any]:
    config = _load(config_path)
    status = _load(status_path)
    failures: list[dict[str, str]] = []
    passed = 0
    code_complete = 0
    code_incomplete: list[dict[str, str]] = []
    for account_id in config["accounts"]:
        rows = status.get("accounts", {}).get(account_id, {})
        for capability in config["capabilities"]:
            evidence_paths = [str(path) for path in config.get("code_evidence", {}).get(capability, [])]
            missing_paths = [path for path in evidence_paths if not (ROOT / path).exists()]
            if evidence_paths and not missing_paths:
                code_complete += 1
            else:
                code_incomplete.append({"account_id": account_id, "capability": capability, "missing_paths": ",".join(missing_paths or ["code_evidence_missing"])})
            row = rows.get(capability, {}) if isinstance(rows, dict) else {}
            state = str(row.get("state", "UNVERIFIED"))
            evidence = row.get("evidence", {}) if isinstance(row.get("evidence"), dict) else {}
            missing = [key for key in config["required_evidence"] if not evidence.get(key)]
            if state != "PASS" or missing:
                failures.append({"account_id": account_id, "capability": capability, "state": state, "missing_evidence": ",".join(missing)})
            else:
                passed += 1
    required = len(config["accounts"]) * len(config["capabilities"])
    return {
        "status": "PASS" if not failures else "FAIL",
        "passed": passed,
        "required": required,
        "failed": failures,
        "code_complete": code_complete,
        "code_required": required,
        "code_incomplete": code_incomplete,
        "production_unverified": required - passed,
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
        print(f"capability_matrix={result['status']} production_pass={result['passed']}/{result['required']} code_complete={result['code_complete']}/{result['code_required']}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
