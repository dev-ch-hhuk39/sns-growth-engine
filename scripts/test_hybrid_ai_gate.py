#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

from hybrid_ai_gate import HybridAiGate, hybrid_ai_gate_passed, merge_gate_audit  # noqa: E402


class FakeClient:
    def __init__(self, *, classification: dict[str, Any] | None = None, generated_text: str = "", review: dict[str, Any] | None = None):
        self.actual_request_count = 0
        self.classification = classification or {
            "decision": "PASS",
            "target_account_match": "PASS",
            "target_audience_match": "PASS",
            "source_audience": "beginner_liver",
            "commercial_context": "B2C",
            "source_usage_fit": "PASS",
            "risk_flags": [],
            "reasons": [],
        }
        self.generated_text = generated_text
        self.review = review or {
            "decision": "PASS",
            "natural_japanese": "PASS",
            "source_grounding": "PASS",
            "account_fit": "PASS",
            "public_safety": "PASS",
            "risk_flags": [],
            "reasons": [],
        }

    def generate_json(self, **kwargs: Any) -> dict[str, Any]:
        self.actual_request_count += 1
        operation = kwargs["operation"]
        if operation == "classify":
            data = self.classification
        elif operation == "generate":
            data = {
                "public_post_text": self.generated_text,
                "preserved_facts": [],
                "removed_noise": [],
                "notes": "fixture",
            }
        else:
            data = self.review
        return {"data": data, "actual_requests": 1, "cache_hit": False}


def base_queue() -> dict[str, Any]:
    return {
        "queue_id": "q_fixture",
        "account_id": "liver_manager",
        "target_account_id": "liver_manager",
        "platform": "threads",
        "generation_mode": "direct_reference_media",
        "transformation_type": "source_copyedit",
        "media_origin": "direct_reference",
        "public_post_text": "枠が崩れそうって配信者が一番感じているからこそ、リスナー皆んなでで支えなきゃいけない！",
        "source_post_id": "sp_fixture",
    }


def main() -> None:
    corrected = "枠が崩れそうって配信者が一番感じているからこそ、リスナーみんなで支えなきゃいけない！"
    client = FakeClient(generated_text=corrected)
    result = HybridAiGate(client).evaluate(base_queue(), {"original_post_text": base_queue()["public_post_text"]})
    assert result.status == "PASS", result.audit()
    assert "でで" not in result.public_post_text
    assert result.actual_requests == 3

    mismatch = dict(client.classification)
    mismatch.update({"decision": "REJECT", "target_audience_match": "FAIL", "source_audience": "store_owner", "commercial_context": "B2B", "risk_flags": ["b2b_b2c_mismatch"]})
    blocked = HybridAiGate(FakeClient(classification=mismatch, generated_text=corrected)).evaluate(base_queue(), {"original_post_text": base_queue()["public_post_text"]})
    assert blocked.status == "BLOCKED"
    assert "ai_target_audience_match_failed" in blocked.blocked_reasons

    reference_only = HybridAiGate(FakeClient(generated_text=corrected)).evaluate(base_queue(), {"original_post_text": base_queue()["public_post_text"], "use_policy": "REFERENCE_ONLY"})
    assert reference_only.status == "BLOCKED"
    assert "reference_only_media_reuse_blocked" in reference_only.blocked_reasons
    assert reference_only.actual_requests == 0

    income_queue = base_queue()
    income_queue["generation_mode"] = "reference_text"
    income_queue["transformation_type"] = "transform"
    income_queue["media_origin"] = ""
    income = HybridAiGate(FakeClient(generated_text="配信未経験から月収500万円を達成できます。"))
    income_result = income.evaluate(income_queue, {"source_text": "配信事務所の説明"})
    assert income_result.status == "BLOCKED"
    assert "unverified_income_amount_present" in income_result.blocked_reasons

    passed_queue = base_queue()
    passed_queue["public_post_text"] = result.public_post_text
    passed_queue["generation_policy_json"] = merge_gate_audit("", result)
    ok, reason = hybrid_ai_gate_passed(passed_queue)
    assert ok is True and reason == "pass"
    passed_queue["public_post_text"] += "変更"
    ok, reason = hybrid_ai_gate_passed(passed_queue)
    assert ok is False and reason == "input_hash_stale"
    print("PASS 13 tests")


if __name__ == "__main__":
    main()
