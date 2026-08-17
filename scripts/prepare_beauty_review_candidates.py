#!/usr/bin/env python3
"""Prepare Beauty Threads candidates for review.

The command is idempotent per JST date/slot.  It may append one validated
WAITING_REVIEW row to Sheets, but never promotes or publishes it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from generation.beauty_review_pipeline import build_beauty_review_batch  # noqa: E402
from generation.beauty_review_pipeline import build_beauty_review_candidate  # noqa: E402
from llm_client import call_gemini_json  # noqa: E402

JST = timezone(timedelta(hours=9))
TOPICS = (
    "スキンケアを一度に変えすぎない判断基準",
    "ベースメイク崩れを塗る量から見直す",
    "ヘアケアは商品より乾かし方を先に整える",
    "美容家電を使う時間から選ぶ",
    "コスメを買い足す前に手持ちの役割を整理する",
    "サロンは仕上がり写真より再現性で選ぶ",
    "肌がゆらぐ日は足すより減らす",
    "メイク前の保湿は量と待ち時間を分けて見る",
)

TOPIC_CONTEXT_TERMS = {
    TOPICS[0]: ("スキンケア", "肌"),
    TOPICS[1]: ("メイク", "ファンデ"),
    TOPICS[2]: ("ヘアケア", "髪"),
    TOPICS[3]: ("美容家電", "スキンケア"),
    TOPICS[4]: ("コスメ", "メイク"),
    TOPICS[5]: ("サロン", "髪"),
    TOPICS[6]: ("肌", "スキンケア"),
    TOPICS[7]: ("メイク", "肌"),
}


def _slot_identity(slot_index: int, now: datetime | None = None) -> tuple[str, str, str]:
    current = (now or datetime.now(JST)).astimezone(JST)
    business_date = current.date().isoformat()
    slot_id = f"beauty_{'1130' if slot_index == 0 else '2030'}"
    queue_id = f"q_beauty_{business_date.replace('-', '')}_{slot_index + 1}"
    return business_date, slot_id, queue_id


def _prompt(topic: str, sequence_number: int, blocked: list[str] | None = None) -> str:
    cta = (
        "最後に保存を促す軽いCTAを1つだけ入れる。"
        if sequence_number % 10 == 0
        else "CTAは入れない。"
    )
    context_terms = TOPIC_CONTEXT_TERMS[topic]
    correction = ""
    if blocked:
        correction = (
            "\n前回は品質基準を満たしませんでした。感嘆符と「きっと」「〜はず」の結果予測を削除し、320文字以内にしてください。"
            f"本文に「{context_terms[0]}」と「{context_terms[1]}」を、羅列ではなく自然な文脈で必ず入れ、"
            "読者が今日試せる行動を1つ示して作り直してください。"
        )
    return f"""
Threadsの美容アカウント用に、読者向けの新規投稿を1件作ってください。
主題: {topic}
読者: 美容・コスメが好きな20〜30代女性
話者: 美容に詳しい、少しお姉さん寄りの女友達。一人称は「私」。
口調: 女性的で柔らかい口語。「ねぇ、みんな」の呼びかけ、感嘆符、広告臭、押し売り、説教、大げさな効果断定を禁止。
構成: 悩みまたは気づきを1つ、理由、今日試せる具体的な行動。主題は1つに限る。
美容文脈: 「{context_terms[0]}」と「{context_terms[1]}」を、不自然な羅列にせず本文にどちらも入れる。
文字数: 140〜320文字。ハッシュタグなし。Markdownなし。
禁止: 美容医療、疾病・治療、薬機的効果、before/after保証、内部用語、参照元名、AIへの言及。「浸透する」「キューティクルが閉じる」「効果が半減」などの科学的な因果を言い切らない。
{cta}
{correction}
JSONで public_post_text と primary_topic だけを返してください。
""".strip()


def generate_candidate(*, slot_index: int, sequence_number: int) -> dict:
    business_date, slot_id, queue_id = _slot_identity(slot_index)
    topic_index = (datetime.now(JST).date().toordinal() * 2 + slot_index) % len(TOPICS)
    topic = TOPICS[topic_index]
    if not os.environ.get("GEMINI_API_KEY", "").strip():
        return {"status": "BLOCKED", "reason": "GEMINI_API_KEY_MISSING"}
    blocked: list[str] = []
    for attempt in range(1, 6):
        response = call_gemini_json(
            _prompt(topic, sequence_number, blocked),
            temperature=0.85,
        )
        text = str(response.get("public_post_text", "")).strip()
        candidate = build_beauty_review_candidate(
            "new_text_generation",
            public_post_text=text,
            sequence_number=sequence_number,
        )
        blocked = list(candidate["public_post_validator"].get("blocked_reasons", []))
        blocked.extend(candidate["beauty_compliance"].get("blocked_reasons", []))
        if text and not blocked and str(candidate["review_lane"]).upper() == "BEAUTY_STANDARD":
            candidate.update({
                "status": "WAITING_REVIEW",
                "queue_id": queue_id,
                "slot_id": slot_id,
                "business_date_jst": business_date,
                "primary_topic": str(response.get("primary_topic") or topic),
                "generation_attempt": attempt,
            })
            return candidate
    return {"status": "QUALITY_EXHAUSTED", "blocked_reasons": sorted(set(blocked))}


def queue_row(candidate: dict) -> dict:
    validation = candidate["public_post_validator"]
    text = candidate["public_post_text"]
    return {
        "queue_id": candidate["queue_id"],
        "account_id": "beauty_account",
        "target_account_id": "beauty_account",
        "platform": "threads",
        "status": "WAITING_REVIEW",
        "priority": "1",
        "auto_publish": "false",
        "generation_mode": "beauty_new_text_generation",
        "content_route": "new_text_generation",
        "public_post_text": text,
        "generated_by": "prepare_beauty_review_candidates.py",
        "validator_status": validation["status"],
        "internal_leak_status": validation["internal_leak_check"]["status"],
        "account_fit_status": validation["account_fit_check"]["status"],
        "public_post_quality_score": validation["public_post_quality_score"],
        "reader_value_score": validation["reader_value_score"],
        "naturalness_score": validation["naturalness_score"],
        "cta_pressure_score": validation["cta_pressure_score"],
        "voice_persona_status": validation["voice_persona_check"]["status"],
        "voice_persona_score": validation["voice_persona_check"]["score"],
        "review_lane": candidate["review_lane"],
        "primary_topic": candidate["primary_topic"],
        "slot_id": candidate["slot_id"],
        "business_date_jst": candidate["business_date_jst"],
        "media_required": "false",
        "media_reuse_risk": "not_applicable",
        "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "generation_attempt": candidate["generation_attempt"],
    }


def apply_candidate(candidate: dict) -> dict:
    from config_loader import get_config
    from sheets_client import SheetsClient

    config = get_config()
    client = SheetsClient(config["sheet_id"], config["sa_dict"], dry_run=False)
    existing = client.get_queue_item(candidate["queue_id"])
    if existing:
        same = str(existing.get("content_hash", "")) == queue_row(candidate)["content_hash"]
        return {"status": "ALREADY_EXISTS" if same else "CONFLICT", "queue_id": candidate["queue_id"], "read_after_write": same}
    row = queue_row(candidate)
    client.append_queue_item(row)
    saved = client.get_queue_item(candidate["queue_id"]) or {}
    exact = all(str(saved.get(key, "")) == str(row.get(key, "")) for key in ("queue_id", "account_id", "status", "public_post_text", "content_hash"))
    return {"status": "APPLIED" if exact else "READ_AFTER_WRITE_FAILED", "queue_id": candidate["queue_id"], "read_after_write": exact}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sequence-start", type=int, default=0)
    parser.add_argument("--slot-index", type=int, choices=[0, 1])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-prepare", action="store_true")
    args = parser.parse_args()
    if args.slot_index is not None:
        sequence_number = args.sequence_start or (datetime.now(JST).date().toordinal() * 2 + args.slot_index + 1)
        candidate = generate_candidate(slot_index=args.slot_index, sequence_number=sequence_number)
        result = {"mode": "apply" if args.apply else "dry-run", "candidate": candidate, "would_post": False}
        if candidate.get("status") in {"BLOCKED", "QUALITY_EXHAUSTED"}:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1
        if args.apply:
            if not args.confirm_prepare:
                result["apply_result"] = {"status": "BLOCKED", "reason": "--apply requires --confirm-prepare"}
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 1
            result["apply_result"] = apply_candidate(candidate)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if not args.apply or result["apply_result"].get("read_after_write") else 1
    result = build_beauty_review_batch(sequence_start=args.sequence_start)
    result["dry_run"] = True
    result["would_write_sheets"] = False
    result["would_post"] = False
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["all_public_validators_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
