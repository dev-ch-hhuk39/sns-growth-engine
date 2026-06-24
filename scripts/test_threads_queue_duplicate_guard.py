#!/usr/bin/env python3
"""Validate duplicate guards used by the Threads queue worker."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/process_threads_queue.py"


def _load():
    spec = importlib.util.spec_from_file_location("process_threads_queue", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    mod = _load()
    base_queue = {"queue_id": "q1", "draft_id": "d1", "account_id": "night_scout", "platform": "threads"}
    social = {"derivative_id": "sd1", "platform": "threads"}
    text = "同じ投稿文"
    cases = [
        (
            "queue_id duplicate",
            [{"queue_id": "q1", "status": "POSTED", "platform": "threads"}],
            "queue_id already",
        ),
        (
            "derivative_id duplicate",
            [{"derivative_id": "sd1", "status": "POSTED", "platform": "threads"}],
            "derivative_id already",
        ),
        (
            "draft_id duplicate",
            [{"draft_id": "d1", "status": "RECOVERED", "platform": "threads"}],
            "draft_id already",
        ),
        (
            "same text duplicate",
            [{"account_id": "night_scout", "platform": "threads", "status": "POSTED", "posted_text": text}],
            "same text",
        ),
    ]
    checks = []
    for name, posted_rows, expected in cases:
        reason = mod.duplicate_reason(queue_row=base_queue, social=social, text=text, posted_rows=posted_rows)
        checks.append((name, expected in reason))
    checks.append((
        "different platform ignored",
        mod.duplicate_reason(
            queue_row=base_queue,
            social=social,
            text=text,
            posted_rows=[{"queue_id": "other", "platform": "x", "status": "POSTED", "posted_text": text}],
        ) == "",
    ))
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
