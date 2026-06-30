#!/usr/bin/env python3
"""MEASURED metrics should produce a PDCA next-candidate offline."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/generate_next_queue_from_metrics.py"


def _load():
    spec = importlib.util.spec_from_file_location("generate_next_queue_from_metrics_for_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    mod = _load()
    posted = [{
        "result_id": "threads_sample_measured",
        "account_id": "liver_manager",
        "platform": "threads",
        "metrics_status": "MEASURED",
        "views": "10",
        "likes": "1",
        "comments": "1",
    }]
    ranked = mod.rank_results_by_engagement(posted, "liver_manager")
    drafts, queues, suggestion = mod.build_next_queue_candidates(ranked, "liver_manager", 1, "202606300001")
    checks = [
        ("one measured row ranked", len(ranked) == 1),
        ("er computed", ranked[0]["er"] == 0.2),
        ("one queue candidate", len(queues) == 1),
        ("candidate not postable", queues[0]["status"] == mod.NON_POSTABLE_STATUS and queues[0]["status"] not in mod.ELIGIBLE_STATUSES),
        ("suggestion waiting review", suggestion["status"] == "WAITING_REVIEW"),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
