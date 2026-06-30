#!/usr/bin/env python3
"""PDCA dry-run stays safe when the first post has no measured metrics yet."""
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
    pending = [
        {"result_id": "r1", "account_id": "liver_manager", "metrics_status": "PENDING", "views": "0", "likes": "0", "comments": "0"}
    ]
    ranked = mod.rank_results_by_engagement(pending, "liver_manager")
    checks = [
        ("pending metrics ignored", ranked == []),
        ("script says never auto posts", "never auto-posts" in SCRIPT.read_text(encoding="utf-8")),
        ("candidate status draft", getattr(mod, "NON_POSTABLE_STATUS", "") == "DRAFT"),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
