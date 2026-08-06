#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

from hybrid_ai_gate import HybridAiGate
from run_direct_reference_media_pipeline import scheduled_direct_caption_blockers
from run_media_production_pipeline import (
    approved_clip_duration_blockers,
    approved_clip_duration_seconds,
)


class ContractClient:
    def __init__(self, generated_text: str) -> None:
        self.generated_text = generated_text
        self.actual_request_count = 0

    def generate_json(self, **kwargs: Any) -> dict[str, Any]:
        self.actual_request_count += 1
        operation = kwargs["operation"]
        if operation == "classify":
            account_id = kwargs.get("account_id", "")
            data = {
                "decision": "PASS",
                "target_account_match": "PASS",
                "target_audience_match": "PASS",
                "source_audience": (
                    "night_work_job_seeker"
                    if account_id == "night_scout"
                    else "beginner_liver"
                ),
                "commercial_context": "B2C",
                "source_usage_fit": "PASS",
                "risk_flags": [],
                "reasons": [],
            }
        elif operation == "generate":
            data = {
                "public_post_text": self.generated_text,
                "preserved_facts": [],
                "removed_noise": [],
                "notes": "fixture",
            }
        else:
            data = {
                "decision": "PASS",
                "natural_japanese": "PASS",
                "source_grounding": "PASS",
                "account_fit": "PASS",
                "public_safety": "PASS",
                "risk_flags": [],
                "reasons": [],
            }
        return {"data": data, "actual_requests": 1, "cache_hit": False}


def queue(account_id: str, content_type: str, current_text: str) -> dict[str, Any]:
    generation_mode = (
        "metrics_driven_pdca_text"
        if content_type == "pdca_text"
        else content_type
    )
    return {
        "queue_id": f"q-{account_id}-{content_type}",
        "account_id": account_id,
        "target_account_id": account_id,
        "platform": "threads",
        "generation_mode": generation_mode,
        "content_type": content_type,
        "public_post_text": current_text,
        "rights_status": "not_required",
        "permission_status": "not_required",
    }


def context(source_text: str) -> dict[str, Any]:
    return {
        "source_text": source_text,
        "permission_evidence_status": "NOT_REQUIRED",
        "classifier_model": "fixture-classifier",
        "generator_model": "fixture-generator",
        "review_model": "fixture-review",
        "read_errors": [],
    }


night_current = (
    "僕なら、本業と夜職を両立する時は、働ける日ではなく回復できる日から決めたい。\n\n"
    "無理なく続いた週の出勤数を基準にして、忙しい時だけ増やす形の方が調整しやすい。\n\n"
    "休みと睡眠を削らずに守れる出勤数を、自分の基準として決めてほしい。"
)
night_generated_without_boku = (
    "本業と夜職を両立する時は、働ける日ではなく、まず回復できる日から予定を決めるのがおすすめです。\n\n"
    "無理なく続けられた週の出勤数を基準にして、忙しい時だけ増やす方が調整しやすくなります。\n\n"
    "休みと睡眠を削らずに守れる出勤数を、自分の基準として決めておくことが大切です。"
)
original_result = HybridAiGate(
    ContractClient(night_generated_without_boku)
).evaluate(
    queue("night_scout", "original_text", night_current),
    context(night_current),
)
assert original_result.status == "PASS", original_result.audit()
assert "僕" in original_result.public_post_text, original_result.public_post_text
assert original_result.generation["scheduled_text_contract"]["status"] == "REPAIRED"

pdca_current = (
    "前回の投稿は101表示で、いいね1件・コメント0件・再投稿0件・引用0件でした。\n\n"
    "僕は、『夜職の条件を見る時は、表示額より引かれる金額を先に整理したい』という判断軸が具体的だったことが、"
    "読者の反応につながった可能性があると見ています。\n\n"
    "次は、同じテーマを入店前に確認する三つの項目へ絞り、表示数とコメント数が前回を上回るか確認します。"
)
pdca_generic = (
    "夜職の条件を見る時は、提示額より実際に引かれる金額を先に整理することが大切です。\n\n"
    "ノルマや控除、バックの計算方法を分けて聞くと、働いた後の金額を想像しやすくなります。\n\n"
    "入店前に費用を質問できるかどうかも、お店を選ぶ判断材料になります。"
)
pdca_result = HybridAiGate(ContractClient(pdca_generic)).evaluate(
    queue("night_scout", "pdca_text", pdca_current),
    context(pdca_current),
)
assert pdca_result.status == "PASS", pdca_result.audit()
assert pdca_result.public_post_text == pdca_current
contract = pdca_result.generation["scheduled_text_contract"]
assert contract["fallback_to_current_queue_text"] is True, contract
assert "pdca_measured_observation_missing" in contract["rejected_generated_contract_reasons"]

liver_current = (
    "初見がすぐ抜ける配信は、内容より最初に入りやすい説明があるかを見直したい。\n\n"
    "冒頭の挨拶、話題の説明、最初の質問を固定すると、毎回の入口を改善しやすい。\n\n"
    "初見がコメントしやすい入口を一つ整え、配信後に反応を確認してみましょう。"
)
liver_generated = (
    "初見さんがすぐ抜けてしまう時は、配信内容より最初に入りやすい説明があるかを見直してみましょう。\n\n"
    "冒頭の挨拶、今の話題、最初の質問を固定すると、毎回の入口を改善しやすくなります。\n\n"
    "初見さんがコメントしやすい入口を一つ整えて、配信後の反応を確認してみてください。"
)
liver_result = HybridAiGate(ContractClient(liver_generated)).evaluate(
    queue("liver_manager", "original_text", liver_current),
    context(liver_current),
)
assert liver_result.status == "PASS", liver_result.audit()
assert liver_result.public_post_text == liver_generated

assert scheduled_direct_caption_blockers(
    "liver_manager",
    "lm_1600_direct_media",
    "初見バトルで出会った人と仲良くなれないライバーさん。",
) == ["scheduled_direct_caption_too_short"]
assert scheduled_direct_caption_blockers(
    "night_scout",
    "ns_1800_direct_media",
    "正直に話します。銀座と赤坂、どっちもやばいです。",
) == [
    "scheduled_direct_account_domain_signal_missing",
    "scheduled_direct_caption_too_short",
]
assert scheduled_direct_caption_blockers(
    "liver_manager",
    "manual_e2e",
    "短い配信文",
) == []
valid_direct = (
    "配信で初見のリスナーが入りやすい空気を作るには、最初の挨拶と今の話題を短く伝えることが大切です。"
    "コメントしやすい質問を一つ置き、反応を見ながら会話を続けてみましょう。"
)
assert scheduled_direct_caption_blockers(
    "liver_manager",
    "lm_1600_direct_media",
    valid_direct,
) == []

assert abs(approved_clip_duration_seconds({
    "start_seconds": "352.68",
    "end_seconds": "363.56",
}) - 10.88) < 1e-9
assert approved_clip_duration_blockers({"duration_seconds": "10.88"}) == [
    "clip_duration_out_of_review_range"
]
assert approved_clip_duration_blockers({"duration_seconds": "12"}) == []
assert approved_clip_duration_blockers({"duration_seconds": "45"}) == []
assert approved_clip_duration_blockers({"duration_seconds": "45.01"}) == [
    "clip_duration_out_of_review_range"
]
assert approved_clip_duration_blockers({}) == ["clip_duration_missing"]

media_source = (ROOT / "scripts/run_media_production_pipeline.py").read_text(encoding="utf-8")
assert "duration_blockers = approved_clip_duration_blockers(clip)" in media_source
direct_source = (ROOT / "scripts/run_direct_reference_media_pipeline.py").read_text(encoding="utf-8")
assert "This is slot suitability, not evidence that the media asset is" in direct_source
assert "if uses_default_caption_service" in direct_source
print("PASS test_scheduled_preview_post_ai_contract.py")
