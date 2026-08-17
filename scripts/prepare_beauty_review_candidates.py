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
from generation.beauty_review_pipeline import select_beauty_route  # noqa: E402
from generation.beauty_voice import beauty_voice_prompt  # noqa: E402
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

SAFE_TOPIC_FALLBACKS = {
    TOPICS[0]: "スキンケアって、気になるものを一度に試したくなるんだけど\n個人的には、まず一つだけ変えるのが結構大事だと思う🥺\n\n肌の感じが変わった時に、どれが理由か分かりやすいし\nほんとに合うものも見つけやすくなる💭\n\n使い始めた日だけメモして\nその他はいつも通りで試してみてほしい🤍",
    TOPICS[1]: "夕方にベースメイクが崩れると、コスメを変えたくなるんだけど\n意外とファンデの量だけで変わることもある💭\n\n特に顎や小鼻は、重ねすぎるとヨレやすい気がする\n個人的には、薄く塗って必要なところだけ足すのが好き✨\n\n新しく買う前に\n明日は使う量だけ変えてみてほしい🤍",
    TOPICS[2]: "ヘアケアを増やしても髪がまとまらない時って\nほんとに商品だけが原因なのか迷うよね🥺\n\n個人的には、まず乾かす順番を見るのが結構大事\n根元から乾かして、毛先に熱を当てすぎないだけでも扱いやすさは変わるかも💭\n\nアイテムはそのままで\n一週間だけ乾かし方を比べてみてほしい✨",
    TOPICS[3]: "美容家電って、機能が多いほど良さそうに見えるんだけど\n個人的には、いつ使うかを先に決めるのが結構大事🥺\n\n朝のメイク前か、夜のスキンケア後か\n毎日の流れに入らないと、ほんとに出番が減りがち💭\n\n説明書で使えるタイミングと所要時間を見て\n無理なく続けられそうか比べてみてほしい🤍",
    TOPICS[4]: "新しいコスメが気になる時ほど\n個人的には、手持ちのメイクアイテムを一回並べてみるのがおすすめ✨\n\n下地、ファンデ、血色を足すもの、質感を変えるもの\n同じ役割が重なってると、ほんとに出番が少なくなるんだよね💭\n\n次に買うなら、今足りない役割を一つだけ決めてみてほしい🤍",
    TOPICS[5]: "サロンの仕上がり写真って素敵だけど\n次の日も自分で髪を整えられるかまでは、意外と分からないんだよね💭\n\n個人的には、普段のケア時間や苦手なセットを聞いてくれるかが結構大事\n家でのやり方まで説明があると、ほんとに安心する🤍\n\n予約前に、普段の手入れも相談できるか見てみてほしい✨",
    TOPICS[6]: "肌がゆらいでる気がする日って\n何か足したくなるんだけど、個人的には減らす方を先に考える🥺\n\n新しいスキンケアを重ねると、どれが合わないか分かりにくいんだよね\nこれ結構大事だから、ほんとに無理はしないでほしい💭\n\nまずは普段使っているものに戻して\n順番と量だけ確認してみてね🤍",
    TOPICS[7]: "メイク前の保湿って、多く塗るほど安心するんだけど\n個人的には、量と待ち時間を分けて見るのが結構大事💭\n\n肌がべたついたままベースメイクを重ねると\n意外と厚くなりやすい気がする🥺\n\nスキンケアは変えずに、薄くなじませて少し待つ\nまずはここだけ試してみてほしい✨",
}


def _slot_identity(slot_index: int, now: datetime | None = None) -> tuple[str, str, str]:
    current = (now or datetime.now(JST)).astimezone(JST)
    business_date = current.date().isoformat()
    slot_id = f"beauty_{'1130' if slot_index == 0 else '2030'}"
    queue_id = f"q_beauty_{business_date.replace('-', '')}_{slot_index + 1}_chadult_v1"
    return business_date, slot_id, queue_id


def _prompt(
    topic: str,
    sequence_number: int,
    route: str,
    route_context: dict | None = None,
    blocked: list[str] | None = None,
) -> str:
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
    internal_evidence = str((route_context or {}).get("internal_evidence", "")).strip()
    evidence_instruction = (
        "\n内部参考情報: " + internal_evidence
        + "\nこの情報のテーマ・構成・学習結果だけを使い、source名、URL、過去投稿、metrics、PDCAを公開本文に書かない。"
        if internal_evidence
        else ""
    )
    return f"""
Threadsの美容アカウント用に、読者向けの新規投稿を1件作ってください。
主題: {topic}
生成ルート: {route}
読者: 美容・コスメが好きな20〜30代女性
話者: 美容に詳しい、少しお姉さん寄りの女友達。一人称は「私」。
口調: {beauty_voice_prompt()}「ねぇ、みんな」の呼びかけ、広告臭、押し売り、説教、大げさな効果断定を禁止。実際にない個人体験を「私も〜した」と捏造しない。
構成: 悩みまたは気づきを1つ、理由、今日試せる具体的な行動。主題は1つに限る。
美容文脈: 「{context_terms[0]}」と「{context_terms[1]}」を、不自然な羅列にせず本文にどちらも入れる。
文字数: 140〜320文字。ハッシュタグなし。Markdownなし。
禁止: 美容医療、疾病・治療、薬機的効果、before/after保証、内部用語、参照元名、AIへの言及。「浸透する」「キューティクルが閉じる」「効果が半減」などの科学的な因果を言い切らない。美容家電は機種ごとに使用条件が異なるため、シートマスクや化粧水との併用方法を推測で教えない。
{cta}
{evidence_instruction}
{correction}
JSONで public_post_text と primary_topic だけを返してください。
""".strip()


def _canonical_beauty_source_ids() -> set[str]:
    path = ROOT / "config" / "source_accounts" / "default_sources.json"
    rows = json.loads(path.read_text(encoding="utf-8"))["sources"]
    return {
        str(row.get("source_id") or "")
        for row in rows
        if row.get("target_account_ids") == ["beauty_account"]
        and bool(row.get("canonical_source", True))
    }


def select_beauty_reference_context(rows: list[dict]) -> dict:
    """Select an individual Beauty source post from canonical sources only."""
    allowed_source_ids = _canonical_beauty_source_ids()
    selected = [
        dict(row)
        for row in rows
        if str(row.get("target_account_id") or row.get("account_id") or "") == "beauty_account"
        and str(row.get("source_id") or row.get("source_account_id") or "") in allowed_source_ids
        and str(row.get("source_post_id") or "").strip()
        and str(row.get("original_post_text") or row.get("post_text") or "").strip()
        and str(row.get("individual_post_url") or row.get("source_post_url") or row.get("source_url") or "").strip()
    ]
    if not selected:
        return {"status": "BLOCKED", "reason": "beauty_reference_source_post_missing"}
    row = selected[-1]
    return {
        "status": "PASS",
        "source_ids": [str(row.get("source_id") or row.get("source_account_id") or "")],
        "source_id": str(row.get("source_id") or row.get("source_account_id") or ""),
        "source_post_id": str(row.get("source_post_id") or ""),
        "source_url": str(row.get("individual_post_url") or row.get("source_post_url") or row.get("source_url") or ""),
        "internal_evidence": str(row.get("original_post_text") or row.get("post_text") or "")[:4000],
    }


def select_beauty_pdca_context(rows: list[dict]) -> dict:
    """Use only measured Beauty outcomes; public generation never quotes them."""
    selected = [
        dict(row)
        for row in rows
        if str(row.get("account_id") or "") == "beauty_account"
        and str(row.get("metrics_status") or "").upper() == "MEASURED"
        and str(row.get("result_id") or "").strip()
    ]
    if not selected:
        return {"status": "BLOCKED", "reason": "beauty_measured_pdca_evidence_missing"}
    row = selected[-1]
    evidence = {
        key: row.get(key)
        for key in ("theme", "hook_type", "post_type", "views", "likes", "comments", "posted_at")
        if row.get(key) not in (None, "")
    }
    return {
        "status": "PASS",
        "source_ids": [],
        "pdca_result_id": str(row.get("result_id") or ""),
        "internal_evidence": json.dumps(evidence, ensure_ascii=False, sort_keys=True),
    }


def load_route_context(route: str) -> dict:
    """Read only Beauty-scoped evidence; never substitute another account."""
    if route == "new_text_generation":
        return {"status": "PASS", "source_ids": [], "internal_evidence": ""}
    if route in {"direct_reference_media", "approved_source_clip"}:
        return {
            "status": "DELEGATED_MEDIA_ROUTE",
            "reason": "beauty_media_route_requires_prepared_approved_inventory",
        }
    try:
        from config_loader import get_config
        from sheets_client import SheetsClient
        from sheets_record_reader import read_records_safely

        config = get_config()
        client = SheetsClient(config["sheet_id"], config["sa_dict"], dry_run=False)
        if route == "reference_text_generation":
            rows = [dict(row) for row in read_records_safely(client, "source_posts")]
            return select_beauty_reference_context(rows)
        if route == "pdca_text_generation":
            rows = [dict(row) for row in read_records_safely(client, "posted_results")]
            return select_beauty_pdca_context(rows)
    except Exception as exc:  # fail closed without leaking credential details
        return {"status": "BLOCKED", "reason": f"beauty_route_context_unavailable:{type(exc).__name__}"}
    return {"status": "BLOCKED", "reason": "beauty_route_not_supported"}


def generate_candidate(*, slot_index: int, sequence_number: int) -> dict:
    business_date, slot_id, queue_id = _slot_identity(slot_index)
    topic_index = (datetime.now(JST).date().toordinal() * 2 + slot_index) % len(TOPICS)
    topic = TOPICS[topic_index]
    route = select_beauty_route(sequence_number)
    route_context = load_route_context(route)
    if route_context.get("status") != "PASS":
        return {
            "status": "BLOCKED",
            "reason": route_context.get("reason", "beauty_route_context_missing"),
            "generation_route": route,
        }
    if not os.environ.get("GEMINI_API_KEY", "").strip():
        return {"status": "BLOCKED", "reason": "GEMINI_API_KEY_MISSING"}
    blocked: list[str] = []
    for attempt in range(1, 6):
        response = call_gemini_json(
            _prompt(topic, sequence_number, route, route_context, blocked),
            temperature=0.65,
        )
        text = str(response.get("public_post_text", "")).strip()
        if not text:
            blocked = ["empty_llm_response"]
            continue
        candidate = build_beauty_review_candidate(
            route,
            public_post_text=text,
            sequence_number=sequence_number,
            source_ids=route_context.get("source_ids", []),
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
                "generation_route": route,
                "route_context": route_context,
            })
            return candidate
    fallback = build_beauty_review_candidate(
        route,
        public_post_text=SAFE_TOPIC_FALLBACKS[topic],
        sequence_number=sequence_number,
        source_ids=route_context.get("source_ids", []),
    )
    fallback_blocked = list(fallback["public_post_validator"].get("blocked_reasons", []))
    fallback_blocked.extend(fallback["beauty_compliance"].get("blocked_reasons", []))
    if not fallback_blocked and str(fallback["review_lane"]).upper() == "BEAUTY_STANDARD":
        fallback.update({
            "status": "WAITING_REVIEW",
            "queue_id": queue_id,
            "slot_id": slot_id,
            "business_date_jst": business_date,
            "primary_topic": topic,
            "generation_attempt": "safety_fallback",
            "generation_route": route,
            "route_context": route_context,
        })
        return fallback
    return {"status": "QUALITY_EXHAUSTED", "blocked_reasons": sorted(set(blocked + fallback_blocked))}


def queue_row(candidate: dict) -> dict:
    validation = candidate["public_post_validator"]
    text = candidate["public_post_text"]
    route = str(candidate.get("generation_route") or "new_text_generation")
    route_context = candidate.get("route_context") or {}
    media_required = route in {"direct_reference_media", "approved_source_clip"}
    return {
        "queue_id": candidate["queue_id"],
        "account_id": "beauty_account",
        "target_account_id": "beauty_account",
        "platform": "threads",
        "status": "WAITING_REVIEW",
        "priority": "1",
        "auto_publish": "false",
        "generation_mode": f"beauty_{route}",
        "content_type": route,
        "content_route": route,
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
        "voice_style_profile_version": validation["voice_persona_check"].get("style_profile_version", ""),
        "style_fingerprint_status": validation["voice_persona_check"]["status"],
        "style_fingerprint_score": validation["voice_persona_check"]["score"],
        "semantic_voice_status": "PENDING_HYBRID_AI_REVIEW",
        "semantic_voice_score": "",
        "review_lane": candidate["review_lane"],
        "primary_topic": candidate["primary_topic"],
        "slot_id": candidate["slot_id"],
        "business_date_jst": candidate["business_date_jst"],
        "media_required": str(media_required).lower(),
        "media_status": "AWAITING_APPROVED_MEDIA" if media_required else "NOT_REQUIRED",
        "pdca_account_scope": "beauty_account" if route == "pdca_text_generation" else "",
        "source_id": route_context.get("source_id", ""),
        "source_post_id": route_context.get("source_post_id", ""),
        "source_url": route_context.get("source_url", ""),
        "pdca_result_id": route_context.get("pdca_result_id", ""),
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
