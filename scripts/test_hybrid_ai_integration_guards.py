#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

from hybrid_ai_gate import hybrid_ai_gate_passed  # noqa: E402


def main() -> None:
    approve = (ROOT / "scripts/approve_queue.py").read_text(encoding="utf-8")
    auto = (ROOT / "scripts/auto_approve_queue.py").read_text(encoding="utf-8")
    worker = (ROOT / "scripts/process_threads_queue.py").read_text(encoding="utf-8")
    for source in (approve, auto, worker):
        assert "requires_hybrid_ai_gate" in source
        assert "hybrid_ai_gate_passed" in source
    assert worker.count("HYBRID_AI_GATE_BLOCKED") == 1
    assert "hybrid_ai_gate_" in auto
    assert "[REJECTED] hybrid_ai_gate" in approve
    process_start = worker.index("def process_one(")
    process_end = worker.find("\ndef ", process_start + 1)
    process_region = worker[process_start:] if process_end < 0 else worker[process_start:process_end]
    assert process_region.count("HYBRID_AI_GATE_BLOCKED") == 1
    queue = {
        "account_id": "night_scout",
        "platform": "threads",
        "generation_mode": "reference_text",
        "public_post_text": "夜職の条件を確認する。",
    }
    ok, reason = hybrid_ai_gate_passed(queue, {})
    assert ok is False and reason == "missing"
    print("PASS 11 tests")


if __name__ == "__main__":
    main()
