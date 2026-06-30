#!/usr/bin/env python3
"""Validate successful Threads posts create a posted_results row."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/process_threads_queue.py"


def _load():
    spec = importlib.util.spec_from_file_location("process_threads_queue_for_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    mod = _load()
    captured: list[tuple[str, dict]] = []
    original_append = mod.append_row
    try:
        mod.append_row = lambda _client, logical, row: captured.append((logical, row))
        result_id = mod.save_posted_result(
            object(),
            queue_row={"queue_id": "q_test", "draft_id": "d_test", "account_id": "liver_manager", "status": "READY"},
            social={"derivative_id": "sd_test"},
            text="test post",
            external_post_id="post_123",
            post_url="https://www.threads.com/@example/post/123",
        )
    finally:
        mod.append_row = original_append
    rows = [row for logical, row in captured if logical == "posted_results"]
    row = rows[0] if rows else {}
    checks = [
        ("result id namespaced", result_id.startswith("threads_q_test_")),
        ("one posted_results append", len(rows) == 1),
        ("status posted", row.get("status") == "POSTED"),
        ("queue id saved", row.get("queue_id") == "q_test"),
        ("external id saved", row.get("external_post_id") == "post_123"),
        ("post url saved", str(row.get("post_url", "")).startswith("https://www.threads.com/")),
        ("metrics pending", row.get("metrics_status") == "PENDING"),
        ("real post true", row.get("real_post") == "true"),
        ("media false", row.get("media_used") == "false"),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
