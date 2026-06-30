#!/usr/bin/env python3
"""Validate process_threads_queue fails once and does not retry real posts."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/process_threads_queue.py"


def main() -> int:
    src = SCRIPT.read_text(encoding="utf-8")
    failure_idx = src.find("if not result.success:")
    failure_block = src[failure_idx:src.find("try:", failure_idx)] if failure_idx >= 0 else ""
    checks = [
        ("failure branch exists", failure_idx >= 0),
        ("failure sets FAILED", '"status": "FAILED"' in failure_block),
        ("failure logs no retry", "no immediate retry" in failure_block),
        ("failure returns immediately", 'return {"status": "FAILED"' in failure_block),
        ("no retry helper", "retry" not in src.lower().replace("no immediate retry", "")),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
