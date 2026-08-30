#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from auto_approve_queue import evaluate_item  # noqa: E402
from hybrid_ai_gate import (  # noqa: E402
    GATE_SCHEMA_VERSION,
    PROMPT_VERSION,
    hybrid_ai_input_hash,
)
from hybrid_ai_source_context import hybrid_ai_source_context_hash  # noqa: E402
from public_post_quality import generate_production_post  # noqa: E402


def check(condition: bool, name: str) -> None:
    assert condition, name


def add_mock_gate(queue: dict[str, str]) -> None:
    queue["generation_policy_json"] = json.dumps(
        {
            "hybrid_ai_gate": {
                "schema_version": GATE_SCHEMA_VERSION,
                "prompt_version": PROMPT_VERSION,
                "status": "PASS",
                "provider_status": "AVAILABLE",
                "provider_mode": "gemini",
                "input_hash": hybrid_ai_input_hash(queue),
                "source_context_hash": hybrid_ai_source_context_hash({}),
                "route": "new_text_generation",
            }
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


text = generate_production_post(
    "night_scout",
    batch_id="auto_ready_contract",
    content_type="original_text",
)["public_post_text"]
queue = {
    "queue_id": "q_contract",
    "account_id": "night_scout",
    "platform": "threads",
    "status": "WAITING_REVIEW",
    "generation_mode": "original_text",
    "public_post_text": text,
    "media_reuse_risk": "not_applicable",
    "feature_schema_version": "post_features_v1",
    "quality_gate_version": "generation_quality_v3",
    "batch_diversity_status": "PASS",
    "topic_coherence_status": "PASS",
    "primary_topic": "work_conditions",
    "structure_variant": "1",
    "hook_topic_match": "true",
    "closing_topic_match": "true",
    "shared_hook_detected": "false",
    "shared_closing_detected": "false",
}
derivative = {
    "text": "絶対稼げる。今すぐ応募。",
    "platform": "threads",
}
rules = {
    "auto_ready_enabled": True,
    "kill_switch": False,
    "require_no_media_for_auto_ready": True,
    "allow_third_party_media": False,
    "min_quality_score": 0,
    "min_safety_score": 0,
    "max_risk_score": 100,
    "min_reader_value_score": 0,
    "min_naturalness_score": 0,
    "min_account_fit_score": 0,
    "max_cta_pressure_score": 100,
    "blocked_terms": [],
    "sensitive_terms": [],
}

missing = evaluate_item(
    queue=queue,
    draft=None,
    derivative=derivative,
    scores_by_ref={},
    existing_texts=[],
    rules=rules,
)
check(missing["status"] == "REJECTED", "missing hybrid gate rejected")
check("hybrid_ai_gate_missing" in missing["reasons"], "missing gate reason recorded")

add_mock_gate(queue)
valid = evaluate_item(
    queue=queue,
    draft=None,
    derivative=derivative,
    scores_by_ref={},
    existing_texts=[],
    rules=rules,
)
check(valid["status"] == "APPROVABLE", "valid production and AI contracts approvable")

bad = dict(queue)
bad["topic_coherence_status"] = "BLOCKED"
blocked = evaluate_item(
    queue=bad,
    draft=None,
    derivative=derivative,
    scores_by_ref={},
    existing_texts=[],
    rules=rules,
)
check(blocked["status"] == "REJECTED", "blocked topic contract rejected")
check("topic_coherence_not_pass" in blocked["reasons"], "contract rejection reason recorded")

print("PASS test_auto_ready_requires_generation_contract.py")
