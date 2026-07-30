#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from auto_approve_queue import evaluate_item
from public_post_quality import generate_production_post


def check(condition: bool, name: str) -> None:
    assert condition, name


text = generate_production_post("night_scout", batch_id="auto_ready_contract", content_type="original_text")["public_post_text"]
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
derivative = None
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
result = evaluate_item(queue=queue, draft=None, derivative=derivative, scores_by_ref={}, existing_texts=[], rules=rules)
check(result["status"] == "APPROVABLE", "valid production contract approvable")

bad = dict(queue)
bad["topic_coherence_status"] = "BLOCKED"
blocked = evaluate_item(queue=bad, draft=None, derivative=derivative, scores_by_ref={}, existing_texts=[], rules=rules)
check(blocked["status"] == "REJECTED", "blocked topic contract rejected")
check("topic_coherence_not_pass" in blocked["reasons"], "contract rejection reason recorded")

print("PASS test_auto_ready_requires_generation_contract.py")
