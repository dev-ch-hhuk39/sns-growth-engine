#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

import run_hybrid_ai_queue_gate as runner  # noqa: E402
from hybrid_ai_gate import (  # noqa: E402
    GATE_SCHEMA_VERSION,
    PROMPT_VERSION,
    hybrid_ai_input_hash,
)
from hybrid_ai_source_context import (  # noqa: E402
    build_source_context,
    hybrid_ai_source_context_hash,
)


class FakeQueueClient:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def get_queue_items(self, **_kwargs: Any) -> list[dict[str, Any]]:
        return [dict(row) for row in self.rows]


class FakeLedgerClient:
    def log(self, **_kwargs: Any) -> None:
        raise AssertionError("log must not be called when ledger read fails")


class RecordingLedgerClient:
    def __init__(self) -> None:
        self.logged: list[dict[str, Any]] = []

    def log(self, **kwargs: Any) -> None:
        self.logged.append(dict(kwargs))


def main() -> None:
    queue = {
        "queue_id": "q_current",
        "account_id": "night_scout",
        "target_account_id": "night_scout",
        "platform": "threads",
        "status": "WAITING_REVIEW",
        "generation_mode": "original_text",
        "public_post_text": "夜職の条件は、表示額だけでなく控除と相談環境まで確認したい。",
        "priority": "1",
    }
    fake = FakeQueueClient([queue])
    context = build_source_context(fake, queue)
    gate = {
        "schema_version": GATE_SCHEMA_VERSION,
        "prompt_version": PROMPT_VERSION,
        "status": "PASS",
        "provider_status": "AVAILABLE",
        "provider_mode": "gemini",
        "input_hash": hybrid_ai_input_hash(queue),
        "source_context_hash": hybrid_ai_source_context_hash(context),
        "route": "new_text_generation",
    }
    queue["generation_policy_json"] = json.dumps(
        {"hybrid_ai_gate": gate},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    selected, skipped = runner.candidate_rows(FakeQueueClient([queue]), "night_scout", 2)
    assert selected == []
    assert skipped == [{"queue_id": "q_current", "gate_status": "pass"}]

    changed = dict(queue)
    changed["public_post_text"] += "更新"
    selected, skipped = runner.candidate_rows(FakeQueueClient([changed]), "night_scout", 2)
    assert len(selected) == 1
    assert skipped == []

    original_reader = runner.read_records_safely

    def fail_reader(_client: Any, _logical: str) -> list[dict[str, Any]]:
        raise RuntimeError("fixture_read_failure")

    runner.read_records_safely = fail_reader
    try:
        ledger = runner.SheetsBudgetLedger(FakeLedgerClient(), "night_scout")
        try:
            ledger.reserve({"operation": "classify"})
        except RuntimeError as exc:
            assert "fixture_read_failure" in str(exc)
        else:
            raise AssertionError("budget read failure must fail closed")
    finally:
        runner.read_records_safely = original_reader

    original_daily_max = runner.DAILY_MAX
    runner.DAILY_MAX = 1
    try:
        other_account_rows = [{
            "operation": "hybrid_ai_request_reserved",
            "status": "OK",
            "account_id": "liver_manager",
            "timestamp": runner.now_iso(),
        }]
        runner.read_records_safely = lambda _client, _logical: other_account_rows
        recording = RecordingLedgerClient()
        runner.SheetsBudgetLedger(recording, "night_scout").reserve({"operation": "classify"})
        assert len(recording.logged) == 1

        same_account_rows = [{**other_account_rows[0], "account_id": "night_scout"}]
        runner.read_records_safely = lambda _client, _logical: same_account_rows
        try:
            runner.SheetsBudgetLedger(RecordingLedgerClient(), "night_scout").reserve({"operation": "classify"})
        except RuntimeError as exc:
            assert str(exc) == "hybrid_ai_daily_limit_exceeded"
        else:
            raise AssertionError("same-account daily budget must remain fail-closed")
    finally:
        runner.read_records_safely = original_reader
        runner.DAILY_MAX = original_daily_max

    workflows = [
        (ROOT / ".github/workflows/hybrid-ai-gate-night-scout.yml").read_text(encoding="utf-8"),
        (ROOT / ".github/workflows/hybrid-ai-gate-liver-manager.yml").read_text(encoding="utf-8"),
    ]
    for workflow in workflows:
        assert "gemini-3.1-flash-lite" in workflow
        assert "gemini-3.5-flash" in workflow
        assert "gemini-2.5" not in workflow
        assert "--max-candidates 2" in workflow
        assert "group: hybrid-ai-gate-production" in workflow

    print("PASS 10 tests")


if __name__ == "__main__":
    main()
