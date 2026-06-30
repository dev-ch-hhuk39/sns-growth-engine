#!/usr/bin/env python3
"""PDCA generation must never create READY rows directly."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/generate_next_queue_from_metrics.py"


def _load():
    spec = importlib.util.spec_from_file_location("generate_next_queue_from_metrics_for_test3", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    mod = _load()
    ranked = [{"result_id": "r1", "content_type": "engagement", "views": 100, "likes": 4, "comments": 1, "er": 0.05}]
    _drafts, queues, suggestion = mod.build_next_queue_candidates(ranked, "liver_manager", 1, "202606300003")
    checks = [
        ("non postable constant", mod.NON_POSTABLE_STATUS == "DRAFT"),
        ("ready only eligible", mod.ELIGIBLE_STATUSES == {"READY"}),
        ("queue not ready", all(q["status"] != "READY" for q in queues)),
        ("auto publish false", all(q["auto_publish"] == "false" for q in queues)),
        ("suggestion does not auto apply", "auto_apply=false" in suggestion["notes"]),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
