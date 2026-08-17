#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

from hybrid_ai_gate import HybridAiGate  # noqa: E402
from run_direct_reference_media_pipeline import scheduled_direct_caption_blockers  # noqa: E402
from run_media_production_pipeline import (  # noqa: E402
    approved_clip_duration_blockers,
    approved_clip_duration_seconds,
)


class PromptCaptureClient:
    def __init__(self, generated_text: str) -> None:
        self.generated_text = generated_text
        self.actual_request_count = 0
        self.review_prompt = ""

    def generate_json(self, **kwargs: Any) -> dict[str, Any]:
        self.actual_request_count += 1
        operation = kwargs["operation"]
        if operation == "classify":
            data = {
                "decision": "PASS",
                "target_account_match": "PASS",
                "target_audience_match": "PASS",
                "source_audience": "night_work_job_seeker",
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
            self.review_prompt = kwargs["prompt"]
            data = {
                "decision": "PASS",
                "natural_japanese": "PASS",
                "source_grounding": "PASS",
                "account_fit": "PASS",
                "public_safety": "PASS",
                "voice_persona": "PASS",
                "voice_persona_score": 95,
                "identity_fit": "PASS",
                "interpersonal_distance": "PASS",
                "register_fit": "PASS",
                "conversational_naturalness": "PASS",
                "risk_flags": [],
                "reasons": [],
            }
        return {"data": data, "actual_requests": 1, "cache_hit": False}


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
                "voice_persona": "PASS",
                "voice_persona_score": 95,
                "identity_fit": "PASS",
                "interpersonal_distance": "PASS",
                "register_fit": "PASS",
                "conversational_naturalness": "PASS",
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
    "本業と夜職を両立したい子に伝えたい。\n\n"
    "僕なら、働ける日より回復できる日から決めるんだよね。無理なく続いた週の出勤数を基準にして、忙しい時だけ増やす方が調整しやすい。\n\n"
    "休みと睡眠を削らずに守れる出勤数を、自分の基準にするのが大事だよ。"
)
night_generated_without_boku = (
    "本業と夜職を両立したい子は、働ける日より回復できる日から予定を決めた方がいい。\n\n"
    "無理なく続いた週の出勤数を基準にして、忙しい時だけ増やす方が調整しやすいんだよね。\n\n"
    "休みと睡眠を削らずに守れる出勤数を、自分の基準にするのが大事だよ。"
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

# Scheduled owned Direct media must preserve the Night Scout first-person voice after AI rewriting.
direct_queue = queue("night_scout", "direct_reference_media", night_current)
direct_queue.update({
    "generation_mode": "direct_reference_media",
    "media_origin": "direct_reference",
    "ownership": "system_owned",
    "source_id": "system_owned_night_scout_fixture",
})
direct_context = context(night_current)
direct_context["permission_evidence_status"] = "APPROVED"
direct_result = HybridAiGate(ContractClient(night_generated_without_boku)).evaluate(
    direct_queue,
    direct_context,
)
assert direct_result.status == "PASS", direct_result.audit()
assert "僕" in direct_result.public_post_text, direct_result.public_post_text
assert direct_result.generation["scheduled_text_contract"]["status"] == "REPAIRED"

pdca_current = (
    "僕なら、夜職の条件を見る時は提示額より、引かれる金額を先に聞くんだよね。\n\n"
    "ノルマ、控除、バックの計算を分けて聞くと、働いた後の手取りを想像しやすい。\n\n"
    "入店前に質問できるかも、お店選びの大事な判断材料だよ。"
)
pdca_generated = (
    "僕は、時給を見る時ほど控除も一緒に聞いてほしいんだよね。\n\n"
    "ノルマとバックの条件まで分けると、実際の手取りがイメージしやすい。\n\n"
    "お店を決める前に、給料から引かれる項目を一つずつ確認するのが大事だよ。"
)
pdca_result = HybridAiGate(ContractClient(pdca_generated)).evaluate(
    queue("night_scout", "pdca_text", pdca_current),
    context("過去のmetricsと仮説は内部学習用"),
)
assert pdca_result.status == "PASS", pdca_result.audit()
assert pdca_result.public_post_text == pdca_generated
assert "前回の投稿" not in pdca_result.public_post_text
assert "表示数" not in pdca_result.public_post_text

# PDCA evidence stays internal; the public post must be ordinary new content.
prompt_client = PromptCaptureClient(pdca_generated)
prompt_result = HybridAiGate(prompt_client).evaluate(
    queue("night_scout", "pdca_text", pdca_current),
    context("過去のmetricsと仮説は内部学習用"),
)
assert prompt_result.status == "PASS", prompt_result.audit()
assert "内部学習のみ" in prompt_client.review_prompt, prompt_client.review_prompt
assert "独立した通常の新規コンテンツ" in prompt_client.review_prompt, prompt_client.review_prompt

liver_current = (
    "初見さんがすぐ抜けると、内容が悪いのかなって不安になるよね。\n\n"
    "でも、冒頭の挨拶、今の話題、最初の質問を決めるだけで入口は作りやすい。\n\n"
    "私なら次の配信で一つだけ整えるかな。全部変えなくて大丈夫。反応を見ながら試してみてね。"
)
liver_generated = (
    "初見さんがすぐ抜けると、何を変えればいいか迷うよね。\n\n"
    "私は、冒頭の挨拶、今の話題、最初の質問を一つずつ決めるかな。入口が分かるとコメントもしやすい。\n\n"
    "次の配信では一つだけ試してみてね。全部変えなくて大丈夫だよ。"
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
