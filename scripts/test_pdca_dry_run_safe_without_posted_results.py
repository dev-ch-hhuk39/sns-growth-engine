#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("generate_next_queue_from_metrics", ROOT / "scripts/generate_next_queue_from_metrics.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    mod = _load()
    ranked = mod.rank_results_by_engagement([], "night_scout")
    drafts, queues, suggestion = mod.build_next_queue_candidates(ranked, "night_scout", 2, "20260630000000")
    checks = [
        ("posted_resultsなしでrank空", ranked == []),
        ("候補0件", drafts == [] and queues == []),
        ("suggestion WAITING_REVIEW", suggestion["status"] == "WAITING_REVIEW"),
        ("auto applyしない", "auto_apply=false" in suggestion["notes"]),
    ]
    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {n}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
