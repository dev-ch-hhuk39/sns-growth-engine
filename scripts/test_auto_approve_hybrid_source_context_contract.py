#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

from auto_approve_queue import build_plan, load_rules
from autonomous_recovery_test_utils import _mock_hybrid_ai_pass_fields
from hybrid_ai_gate import hybrid_ai_gate_current
from hybrid_ai_source_context import build_source_context, hybrid_ai_source_context_hash
from public_post_quality import generate_reader_facing_post
from sheets_client import MockSheetsClient


def main() -> None:
    client = MockSheetsClient()
    body = generate_reader_facing_post("night_scout", 1)["public_post_text"]
    client.save_draft(
        "night_scout",
        body.splitlines()[0],
        body,
        draft_id="d-context-contract",
        status="WAITING_REVIEW",
        generation_mode="safe_original_fallback_threads",
        media_strategy="none",
        media_reuse_risk="low",
        source_refs="",
    )
    client.append_social_derivative({
        "derivative_id": "sd-context-contract",
        "draft_id": "d-context-contract",
        "account_id": "night_scout",
        "platform": "threads",
        "text": body,
        "status": "WAITING_REVIEW",
        "media_strategy": "none",
    })
    queue = {
        "queue_id": "q-context-contract",
        "draft_id": "d-context-contract",
        "account_id": "night_scout",
        "platform": "threads",
        "status": "WAITING_REVIEW",
        "generation_mode": "safe_original_fallback_threads",
        "media_reuse_risk": "low",
        "priority": "1",
        "public_post_text": body,
    }
    queue.update(_mock_hybrid_ai_pass_fields(client, queue, body))
    gate = json.loads(queue["generation_policy_json"])["hybrid_ai_gate"]
    canonical = build_source_context(client, queue)
    assert gate["source_context_hash"] == hybrid_ai_source_context_hash(canonical)

    client.append_queue_item(queue)
    plan = build_plan(client, "night_scout", 1, load_rules())
    assert plan["approvable_count"] == 1, plan

    changed_evidence = {**canonical, "permission_evidence_status": "APPROVED"}
    current, reason = hybrid_ai_gate_current(queue, changed_evidence)
    assert current is False
    assert reason == "source_context_stale"
    print("PASS test_auto_approve_hybrid_source_context_contract.py")


if __name__ == "__main__":
    main()
