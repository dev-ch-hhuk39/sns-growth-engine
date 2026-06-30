#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("process_threads_queue", ROOT / "scripts/process_threads_queue.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class FakeClient:
    def __init__(self, rows):
        self.rows = rows


def main() -> int:
    mod = _load()
    rows = [
        {"queue_id": "q_wait", "account_id": "night_scout", "platform": "threads", "status": "WAITING_REVIEW", "priority": "1"},
        {"queue_id": "q_ready", "account_id": "night_scout", "platform": "threads", "status": "READY", "priority": "2"},
    ]
    old_records = mod.records
    mod.records = lambda client, logical: rows if logical == "queue" else []
    try:
        selected = mod.select_candidates(FakeClient(rows), "night_scout", 10)
    finally:
        mod.records = old_records
    checks = [
        ("READYだけ選択", [r["queue_id"] for r in selected] == ["q_ready"]),
        ("WAITING_REVIEW除外", all(r["status"] == "READY" for r in selected)),
    ]
    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {n}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
