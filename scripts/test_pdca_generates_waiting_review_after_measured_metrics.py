#!/usr/bin/env python3
"""PDCA candidates from measured metrics require review before posting."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/generate_next_queue_from_metrics.py"


def _load():
    spec = importlib.util.spec_from_file_location("generate_next_queue_from_metrics_for_test2", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    mod = _load()
    ranked = [{"result_id": "r1", "content_type": "hook", "views": 20, "likes": 2, "comments": 0, "er": 0.1}]
    drafts, queues, suggestion = mod.build_next_queue_candidates(ranked, "night_scout", 1, "202606300002")
    checks = [
        ("draft waiting review", drafts[0]["status"] == "WAITING_REVIEW"),
        ("queue draft", queues[0]["status"] == "DRAFT"),
        ("queue ai recommendation waiting review", queues[0]["ai_publish_recommendation"] == "WAITING_REVIEW"),
        ("suggestion review only", suggestion["status"] == "WAITING_REVIEW" and "auto_apply=false" in suggestion["notes"]),
        ("no ready generated", all(q["status"] != "READY" for q in queues)),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
