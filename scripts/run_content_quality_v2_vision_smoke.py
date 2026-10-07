#!/usr/bin/env python3
"""Selected historical read-only editorial packages; no production clients imported."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from acquisition.models import SourcePostBundle  # noqa: E402
from build_media_first_review_pack import inspect_preview, selected_previews  # noqa: E402
from generation.content_quality_v2 import (  # noqa: E402
    fabricated_media_experience, generate_media_first_caption, prepare_media_context,
    remove_media_test, repair_style_only,
)
from generation.source_grounded_caption import (  # noqa: E402
    SourceGroundedCaptionService, account_rules,
)
from gemini_hybrid_client import GeminiHybridClient, GeminiHttpError, provider_error_evidence
from gemini_quota_diagnostics import FIELDS as QUOTA_FIELDS
from evidence_context_caption import PrivacyBoundedGeminiGroundedProvider
from public_post_quality import voice_persona_validation  # noqa: E402

ACCOUNTS = ("night_scout", "liver_manager", "beauty_account")
PRODUCTION_SECRETS = ("SPREADSHEET_ID", "SNS_MASTER_SHEET_ID", "SA_JSON_BASE64", "GCP_SA_JSON_BASE64",
                      "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET", "GITHUB_TOKEN", "THREADS_ACCESS_TOKEN")
SAFE_CAPTION_VALIDATION_ERRORS = {
    "no_bound_quote_options",
    "caption_quote_choice_invalid",
    "caption_quote_not_bound_to_visual_fact",
    "night_first_person_opening_missing",
    "night_cross_account_live_context",
    "night_cross_account_beauty_emoji",
    "liver_source_person_contact_not_actionable",
    "liver_next_stream_action_not_grounded",
    "liver_next_stream_action_not_source_specific",
    "liver_unobserved_context_added",
    "liver_formal_polite_tone",
    "liver_actionable_ending_missing",
    "beauty_followup_missing",
    "beauty_semantic_inference_unverified",
    "beauty_low_value_text_comparison",
    "beauty_selection_value_missing",
}


class SmokeGeminiClient(GeminiHybridClient):
    """Debug-only bounded transport and evidence; no production client changes."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.caption_evidence = {}
        self.caption_candidate = {}
        self.last_evidence = {}
        path = ROOT / "docs/fixtures/content_quality_v2_smoke_evidence.json"
        self.quota_basis = json.loads(path.read_text()).get("model_quota", {}) if path.exists() else {}

    def fallback_allowed(self, model):
        basis = self.quota_basis
        rows = basis.get("quota_violations", [])
        if not rows or model != "gemini-3.5-flash":
            return False
        try:
            until = datetime.fromisoformat(basis["observed_at"].replace("Z", "+00:00")) + timedelta(seconds=basis["retry_delay_seconds"])
        except (KeyError, TypeError, ValueError):
            return False
        return datetime.now(timezone.utc) < until and all(
            row.get("quota_model") == model and "PerProjectPerModel" in row.get("quota_id", "")
            and row.get("rate_limit_class") in {"DAILY_QUOTA_EXHAUSTED", "MODEL_QUOTA_EXHAUSTED"}
            for row in rows)

    def generate_json(self, **kwargs):
        facts = []
        caption = kwargs.get("operation") == "direct_reference_caption_generation"
        if caption:
            kwargs["retry_profile"] = "vision_relevance"
            prompt = kwargs["prompt"]
            start = prompt.find('{"target_account_id":')
            if start >= 0:
                source, _ = json.JSONDecoder().raw_decode(prompt[start:])
                media = source.get("media_first_input", {})
                ids = media.get("selected_post_angle", {}).get("anchor_fact_ids", [])
                facts = [f for f in media.get("media_context", {}).get("visual_facts", []) if f.get("id") in ids]
                quote_options = []
                for fact in facts:
                    texts = re.findall(r"「([^」]+)」", fact["text"]) or [fact["text"]]
                    for text in texts:
                        # Embedded visible text can contain separate overlay lines, but
                        # action/key-moment prose must never be split into English words.
                        # Otherwise a token such as "dispenses" can become the entire
                        # media anchor and produce an incoherent public caption.
                        if fact.get("type") == "visible_text":
                            excerpts = re.split(r"[\s。]+", text) if re.search(r"[\s。]", text) else [text]
                        else:
                            excerpts = re.split(r"[。\n]+", text) if re.search(r"[。\n]", text) else [text]
                        for part in excerpts:
                            cleaned = part.strip()
                            if fact.get("type") != "visible_text":
                                cleaned = re.sub(r"^\s*\d+[.)．]\s*", "", cleaned).strip()
                            if 8 <= len(cleaned) <= 80 and cleaned in fact["text"]:
                                quote_options.append({"fact_id": fact["id"], "text": cleaned})
                if not quote_options:
                    raise RuntimeError("no_bound_quote_options")
                beauty = kwargs["account_id"] == "beauty_account"
                properties = {
                    "quote_choice": {"type": "integer", "enum": list(range(len(quote_options)))},
                    "reader_takeaway": {"type": "string"},
                }
                required = ["quote_choice", "reader_takeaway"]
                if beauty:
                    properties["beauty_followup"] = {"type": "string"}
                    required.append("beauty_followup")
                kwargs["schema"] = {"type": "object", "properties": properties,
                                    "required": required, "additionalProperties": False}
                account_id = kwargs["account_id"]
                if account_id == "night_scout":
                    account_instruction = (
                        "Nightは男性の夜職・キャバクラ専門スカウト。reader_takeawayは必ず『僕なら』で始め、店選びに迷う夜職女性へ一対一で話す。"
                        "visual_facts内の具体語を二つ以上そのまま残し、採用基準・入店後の競争率・本人の強み等を分けて判断する。"
                        "一律に『避ける』『行くべき』と断定しない。『だと思う』『なんだよね』『が大事』等の自然な現場口調。"
                        "絵文字は禁止。配信、LIVE、ライブ、リスナー、コメント、初見、ギフト、『次の配信では』等の配信文脈は禁止。"
                        "『なのですね』『必要不可欠』『感じさせられます』等の講評・コンサル口調は禁止。"
                    )
                elif account_id == "liver_manager":
                    liver_action_terms = [
                        term for term in ("入室通知", "枠の規模", "運用")
                        if any(term in str(fact.get("text", "")) for fact in facts)
                    ]
                    account_instruction = (
                        "Liverは迷いに共感する女性先輩の口調。quote_choiceは『運用』『大事』のような抽象語だけの結論より、入室通知・コメント・初見など次回配信でそのまま操作を変えられる具体対象が書かれた視覚事実を優先する。"
                        "reader_takeawayに必ず『次の配信では』を含め、選んだ具体対象について視聴者自身が次回配信で行う一つの具体行動へ落とす。"
                        "その具体行動はvisual_factsに実際にある対象だけで組み立てる。元動画が『読む』『読まない』『やめる』の方向を明示していない場合は、その方向を勝手に決めず『枠の規模に合わせて読み上げルールを決める』等の判断行動にする。リスナー数・反応速度・配信時間などvisual_factsにない判断指標を足さない。"
                        f"『次の配信では』以降にはallowed_action_terms={liver_action_terms}の語を最低1つ、その表記のまま必ず含める。別の指標へ言い換えない。"
                        "reader_takeaway全体でもvisual_factsにない主語・心理・指標・機能を足さない。『リスナーが気を使う』『リスナー数』『視聴者数』『反応』『配信時間』『通知の設定』等をvisual_factsにないのに追加するのは禁止。"
                        "引用本文は原文のままでよいが、reader_takeaway自体では『です』『ます』調を使わない。『迷うよね』『〜かも』『〜だよ』『〜てね』のような自然な先輩口調にする。"
                        "元動画の出演者・質問先の固有名詞へ質問、相談、連絡、DMすることを行動案にしない。"
                        "最後は『試してみてね』『決めてみてね』『変えてみてね』等、視聴者へ直接促す自然な行動語尾で締める。"
                        "『〜してみるかも』のように自分語りで終えない。一般的なコミュニティ提案や『みんなで共有』は禁止。"
                    )
                elif account_id == "beauty_account":
                    account_instruction = (
                        "Beautyは少し美容に詳しい女友達の口調。自分が使用した体験・使用感・肌変化・効能は一切書かない。"
                        "quote_choiceでは、visible_actionやkey_moment由来の『手に出す』『スポイトから垂らす』『ボトルを持つ』等の具体的な使用場面が候補にあれば、商品名や成分表記だけの候補より優先する。"
                        "選んだquoteで実際に見える動作・見た目だけを話し、数字や商品名の意味を推測しない。『成分名』『成分』『数値』『名称』『濃度』『配合量』『配合されている』『効く』『効果』『使いやすい』『テクスチャー』『肌改善』『毛穴改善』『気に入ってる』『肌の調子がいい』『肌が整う』『取り入れている』等、観察できない意味ラベル・使用レビューは禁止。『量感』『液垂れ具合』『粘度』『伸び』『なじみ』『使いやすさ』等の物性・使用感も、visual factに明記されていなければ足さない。"
                        "reader_takeawayとbeauty_followupには選んだquoteの具体語を残す。公式サイト確認や文字列照合を目的にせず、動画で見える使い方・出し方・見た目を購入前に確認できるという読者価値へつなげる。"
                        "『文字数が違う』『英語と日本語で長さが違う』『公式サイトに同じ表記があるか』等、動画そのものから離れる低価値なメタ比較は禁止。"
                        "各1段落、句点『。』を使わず、1行44文字程度まで。長い場合は意味を変えず段落内で改行する。絵文字は🥺✨🤍🫶🏻😭💭のみ合計1〜4個。"
                        "自然な女友達口調としてhumanity markerの『意外と』『結構大事』『ほんとに』『気がする』から内容に合うものを最低2つ使い、さらに『だよね』『かも』『〜てみて』等のsoft endingを最低1つ使う。同じ位置に固定せず、不自然な埋め草にしない。広告・効能・定型句の埋め草は禁止。"
                    )
                else:
                    raise RuntimeError("unsupported_smoke_caption_account")
                kwargs["prompt"] = (
                    "未公開の日本語Media投稿を二つの部分で作る。quote_optionsの番号をquote_choiceで一つ選ぶ。引用本文は変更しない。"
                    "reader_takeawayはその引用に対する具体的な判断を45〜90文字、二文以内で書く。抽象論へ広げない。"
                    "引用の重要な具体語を残す。元投稿者の同伴や使用を自分の体験にしない。"
                    "一般化、独自の実績、医学的効能、成果保証、CTAは禁止。"
                    + account_instruction
                    + "『どこでも自分次第』『生き残るためには』『一緒に探そう』等の一般論や勧誘を加えない。観察できない因果・頻度を足さず、主観は主観のまま。JSONのみ。\n"
                    + json.dumps({
                        "account": account_id,
                        "visual_facts": facts,
                        "quote_options": quote_options,
                        **({"allowed_action_terms": liver_action_terms} if account_id == "liver_manager" else {}),
                    }, ensure_ascii=False))
        else:
            facts = []
        original_model = kwargs.get("model", "")
        fallback = (caption or kwargs.get("operation") == "vision_smoke_relevance") and self.fallback_allowed(original_model)
        if fallback:
            kwargs["model"] = "gemini-3.1-flash-lite"
        decision = {"requested_model": original_model, "model": kwargs.get("model", ""),
                    "fallback_used": fallback, "fallback_basis_run": self.quota_basis.get("origin_run_id", "") if fallback else ""}
        try:
            try:
                result = super().generate_json(**kwargs)
            except GeminiHttpError as primary_error:
                quota = primary_error.quota_diagnostics
                violations = quota.get("quota_violations", [])
                scoped = (not fallback and original_model == "gemini-3.5-flash" and bool(violations)
                    and primary_error.status_code == 429
                    and all(row.get("quota_model") == original_model
                            and "PerProjectPerModel" in row.get("quota_id", "")
                            and row.get("rate_limit_class") in {"DAILY_QUOTA_EXHAUSTED", "MODEL_QUOTA_EXHAUSTED"}
                            for row in violations))
                if not scoped:
                    raise
                retry_delay = quota.get("retry_delay_seconds")
                if isinstance(retry_delay, (int, float)) and retry_delay > 0:
                    self.quota_basis = {"observed_at": datetime.now(timezone.utc).isoformat(),
                        "retry_delay_seconds": retry_delay, "quota_violations": violations,
                        "origin_run_id": os.environ.get("GITHUB_RUN_ID", "current_request")}
                kwargs["model"] = "gemini-3.1-flash-lite"
                decision.update(model=kwargs["model"], fallback_used=True, fallback_basis_run="current_request",
                                primary_attempt_history=getattr(primary_error, "attempt_history", []))
                result = super().generate_json(**kwargs)
            if caption and facts:
                data = result["data"]
                choice = data.get("quote_choice")
                if not isinstance(choice, int) or isinstance(choice, bool) or not 0 <= choice < len(quote_options):
                    raise RuntimeError("caption_quote_choice_invalid")
                selected_quote = quote_options[choice]
                fact = next((f for f in facts if f["id"] == selected_quote["fact_id"]), None)
                quote = selected_quote["text"]
                takeaway = str(data.get("reader_takeaway", ""))
                beauty_followup = str(data.get("beauty_followup", "")) if kwargs["account_id"] == "beauty_account" else ""
                if kwargs["account_id"] == "beauty_account":
                    takeaway = re.sub(r"\n\s*\n+", "\n", takeaway.strip())
                    beauty_followup = re.sub(r"\n\s*\n+", "\n", beauty_followup.strip())
                if not fact or not 8 <= len(quote) <= 80 or quote not in fact["text"] or not takeaway:
                    raise RuntimeError("caption_quote_not_bound_to_visual_fact")
                self.caption_candidate = {
                    "quote_choice": choice,
                    "selected_quote": quote,
                    "reader_takeaway": takeaway,
                    **({"beauty_followup": beauty_followup} if beauty_followup else {}),
                }
                if kwargs["account_id"] == "night_scout":
                    if not takeaway.strip().startswith("僕なら"):
                        raise RuntimeError("night_first_person_opening_missing")
                    if re.search(r"(?:次の配信|配信|LIVE|ライブ|リスナー|コメント|初見|ギフト)", takeaway):
                        raise RuntimeError("night_cross_account_live_context")
                    if any(emoji in takeaway for emoji in ("🥺", "✨", "🤍", "🫶🏻", "😭", "💭")):
                        raise RuntimeError("night_cross_account_beauty_emoji")
                if kwargs["account_id"] == "liver_manager":
                    source_text = " ".join(item["text"] for item in facts)
                    source_names = set(re.findall(r"([一-龯ぁ-んァ-ヶA-Za-z0-9]{2,20}さん)", source_text))
                    if any(name in takeaway and re.search(rf"{re.escape(name)}.{{0,16}}(?:質問|聞|相談|連絡|DM)", takeaway)
                               for name in source_names):
                        raise RuntimeError("liver_source_person_contact_not_actionable")
                    # Voice-only repair: keep the same next-stream action while
                    # converting a weak self-directed ending into reader guidance.
                    takeaway = re.sub(
                        r"((?:決め|変え|合わせ|試し)て)みるかも([。！!😊✨🤍🫶🏻😭💭]*)$",
                        r"\1みてね\2",
                        takeaway.strip(),
                    )
                    if not ("次の配信" in takeaway and re.search(
                            r"(?:配信|入室|通知|コメント|初見|枠).{0,40}(?:決め|合わせ|変え|読む|読まない|試)", takeaway)):
                        raise RuntimeError("liver_next_stream_action_not_grounded")
                    action_tail = takeaway.split("次の配信", 1)[1] if "次の配信" in takeaway else ""
                    source_action_terms = [term for term in ("入室通知", "枠の規模", "運用") if term in source_text]
                    if source_action_terms and not any(term in action_tail for term in source_action_terms):
                        raise RuntimeError("liver_next_stream_action_not_source_specific")
                    unsupported_direction = (
                        re.search(r"(?:読み上げ|通知).{0,8}(?:を)?やめ", takeaway)
                        or re.search(r"(?:読み上げ|通知).{0,8}(?:ない|なくする)", takeaway)
                        or re.search(r"(?:必ず|毎回).{0,8}(?:読む|読み上げ)", takeaway)
                    )
                    decision_phrase = re.search(r"(?:読むか読まないか|読み上げるか読み上げないか).{0,12}(?:決め|選)", takeaway)
                    if unsupported_direction and not decision_phrase and not any(
                            phrase in source_text for phrase in ("読み上げをやめ", "読み上げない", "必ず読む", "毎回読む")):
                        raise RuntimeError("liver_unobserved_direction_added")
                    unobserved_terms = ("リスナー", "視聴者", "反応", "配信時間", "通知の設定", "入室通知の設定", "気を使う")
                    if any(term in takeaway and term not in source_text for term in unobserved_terms):
                        raise RuntimeError("liver_unobserved_context_added")
                    if re.search(r"(?:です|ます)(?:[。！!？?]|$)", takeaway):
                        raise RuntimeError("liver_formal_polite_tone")
                    if not re.search(
                            r"(?:試してみてね|決めてみてね|変えてみてね|合わせてみてね)[。！!😊✨🤍🫶🏻😭💭]*$",
                            takeaway.strip()):
                        raise RuntimeError("liver_actionable_ending_missing")
                if kwargs["account_id"] == "beauty_account":
                    if not beauty_followup:
                        raise RuntimeError("beauty_followup_missing")
                    beauty_text = takeaway + "\n" + beauty_followup
                    semantic_terms = ("成分名", "成分", "数値", "名称", "濃度", "配合量", "配合", "効く", "効果", "改善")
                    if any(term in beauty_text and term not in quote for term in semantic_terms):
                        raise RuntimeError("beauty_semantic_inference_unverified")
                    physical_terms = ("量感", "液垂れ具合", "粘度", "伸び", "なじみ", "使いやす", "出す時の感覚", "使用感")
                    if any(term in beauty_text and term not in quote for term in physical_terms):
                        raise RuntimeError("beauty_unobserved_physical_property")
                    if re.search(r"文字数|文字の長さ|英語.{0,20}日本語|日本語.{0,20}英語|公式(?:サイト|ページ).{0,24}(?:表記|記載|同じ)", beauty_text):
                        raise RuntimeError("beauty_low_value_text_comparison")
                    if not re.search(r"(?:動画|見える|映って|出す|垂ら|スポイト|手の甲|ボトル|使い方|出し方|見た目|確認|選ぶ|購入)", beauty_text):
                        raise RuntimeError("beauty_selection_value_missing")
                if fact.get("type") == "visible_text":
                    observation = f"この動画の「{quote}」という言葉。"
                elif kwargs["account_id"] == "beauty_account":
                    observation = f"この動画、{quote}"
                else:
                    observation = f"この動画では、{quote}。"
                if kwargs["account_id"] == "beauty_account":
                    observation = observation.removesuffix("。")
                claims = [observation, takeaway] + ([beauty_followup] if beauty_followup else [])
                public_post_text = observation + "\n\n" + takeaway + (("\n\n" + beauty_followup) if beauty_followup else "")
                result = {**result, "data": {"public_post_text": public_post_text,
                    "internal_analysis": {"core_topic": quote, "intended_audience": kwargs["account_id"],
                        "main_claims": claims, "factual_constraints": [fact["text"]], "prohibited_inferences": ["no invented experience or efficacy"]},
                    "claim_support": [{"caption_claim": c, "source_evidence": fact["text"], "anchor_fact_ids": [fact["id"]]} for c in claims],
                    "safety_notes": "quoted observation; no publish permission", "blocked_reasons": []}}
            self.last_evidence = {**decision, "attempt_count": result.get("actual_requests", 0),
                                  "attempt_history": result.get("attempt_history", [])}
            if caption:
                self.caption_candidate = {key: result.get("data", {}).get(key) for key in ("public_post_text", "claim_support", "internal_analysis", "blocked_reasons")}
                self.caption_evidence = {**decision, "provider_status": "PASS", "provider_http_status": 200,
                    "model": result.get("model", ""), "attempt_count": result.get("actual_requests", 0),
                    "attempt_history": result.get("attempt_history", [])}
            return result
        except (RuntimeError, ValueError, TypeError) as exc:
            self.last_evidence = decision
            if caption:
                validation_error = str(exc) if str(exc) in SAFE_CAPTION_VALIDATION_ERRORS else ""
                self.caption_evidence = {**decision, **provider_error_evidence(exc),
                    **getattr(exc, "quota_diagnostics", {}), "retry_status": getattr(exc, "retry_status", ""),
                    "attempt_count": getattr(exc, "attempt_count", 0),
                    "attempt_history": getattr(exc, "attempt_history", []),
                    "validation_error": validation_error}
            raise


def rebind_style_repair_claims(result: dict, repaired_text: str) -> dict:
    """Keep final public text and claim evidence in lock-step after style-only repair."""
    supports = result.get("claim_support", [])
    paragraphs = [part.strip() for part in str(repaired_text or "").split("\n\n") if part.strip()]
    if not isinstance(supports, list) or len(paragraphs) != len(supports):
        raise RuntimeError("style_repair_claim_support_shape_mismatch")
    rebound = [{**support, "caption_claim": paragraph}
               for support, paragraph in zip(supports, paragraphs)]
    updated = {**result, "public_post_text": repaired_text, "claim_support": rebound}
    analysis = result.get("internal_analysis")
    if isinstance(analysis, dict):
        updated["internal_analysis"] = {**analysis, "main_claims": paragraphs}
    return updated


def current_model_scoped_vision_fallback_allowed(vision: dict, primary_model: str) -> bool:
    """Allow one Smoke-only Vision fallback only for explicit model-scoped quota evidence."""
    violations = vision.get("quota_violations", [])
    return (
        primary_model == "gemini-3.5-flash"
        and vision.get("http_status") == 429
        and bool(violations)
        and all(
            row.get("quota_model") == primary_model
            and "PerProjectPerModel" in str(row.get("quota_id", ""))
            and row.get("rate_limit_class") in {"DAILY_QUOTA_EXHAUSTED", "MODEL_QUOTA_EXHAUSTED"}
            for row in violations
        )
    )


def smoke_previews(document: str, target_account: str = "all") -> list[dict]:
    if target_account not in (*ACCOUNTS, "all"):
        raise ValueError("invalid_target_account")
    accounts = ACCOUNTS if target_account == "all" else (target_account,)
    previews = selected_previews(document)
    result = [next(row for row in previews if row["account_id"] == account) for account in accounts]
    if len({row["media_asset_id"] for row in result}) != len(accounts):
        raise ValueError("distinct_selected_previews_required")
    return result


def relevance_review(media: dict, contract: dict, client: GeminiHybridClient) -> dict:
    context = prepare_media_context(media, account_id=media["account_id"])
    if context["visual_status"] != "VISUAL_VERIFIED":
        return {"status": "NOT_RUN", "provider_status": "NOT_RUN", "attempt_count": 0, "attempt_history": []}
    schema = {"type": "object", "properties": {
        **{key: {"type": "string"} for key in ("account_id", "reason", "audience_need", "content_pillar")},
        "status": {"type": "string", "enum": ["PASS", "RELEVANCE_UNVERIFIED"]},
        "anchor_fact_types": {"type": "array", "items": {"type": "string", "enum": [
            "visible_action", "key_moment", "visible_people_or_objects", "visible_text"]}},
    }, "required": ["account_id", "status", "reason", "audience_need", "content_pillar", "anchor_fact_types"]}
    prompt = (
        "検証済みの視覚事実と対象アカウントの読者・content pillarだけから関連性を判定。"
        "事実や音声、発言、効果を補完しない。ジャンルや人物の見た目だけではPASS不可。"
        "Nightは夜職女性の店・接客・条件・働き方の具体的な判断材料、"
        "Liverは次回配信で変えられる具体的な配信行動、Beautyは20〜30代女性の美容判断に役立つこと。"
        "visible_actionやkey_momentに対象アカウント固有の具体場面がある場合は、単なる商品名・人物・カテゴリ文字より優先してanchor_fact_typesへ含める。"
        "不明や対象外ならRELEVANCE_UNVERIFIED。無理に関連付けない。JSONのみ。\n"
        + json.dumps({"account_contract": contract, "visual_facts": context["visual_facts"]}, ensure_ascii=False))
    try:
        response = client.generate_json(model=os.environ.get("GEMINI_GENERATOR_MODEL", "gemini-3.5-flash"),
                                    prompt=prompt, schema=schema, operation="vision_smoke_relevance",
                                    account_id=media["account_id"], retry_profile="vision_relevance")
        return {**response["data"], "provider_status": "PASS", "provider_http_status": 200,
                "provider_error_type": "", "attempt_count": response.get("actual_requests", 0),
                "attempt_history": response.get("attempt_history", []),
                **getattr(client, "last_evidence", {})}
    except (RuntimeError, ValueError, TypeError) as exc:
        diagnostics = getattr(exc, "quota_diagnostics", {})
        safe = {key: diagnostics[key] for key in (*QUOTA_FIELDS, "quota_violations") if key in diagnostics}
        return {"status": "NOT_RUN", **provider_error_evidence(exc), **safe,
                "retry_status": getattr(exc, "retry_status", ""),
                **getattr(client, "last_evidence", {}),
                "attempt_history": getattr(exc, "attempt_history", []),
                "attempt_count": getattr(exc, "attempt_count", 0)}


def build_package(row: dict, directory: Path) -> dict:
    account = row["account_id"]
    config = json.loads((ROOT / "config/accounts" / f"{account}.json").read_text())
    contract = {**account_rules(account), "account_id": account,
                "content_pillars": config.get("content_categories", [])}
    evidence_path = ROOT / "docs/fixtures/content_quality_v2_smoke_evidence.json"
    saved = json.loads(evidence_path.read_text()).get("vision", []) if evidence_path.exists() else []
    evidence = next((p for p in saved if p.get("media_asset_id") == row["media_asset_id"] and p.get("account_id") == account), None)
    client = SmokeGeminiClient(max_attempts=1)
    primary_vision_model = os.environ.get("GEMINI_VISION_MODEL") or os.environ.get("GEMINI_GENERATOR_MODEL") or "gemini-3.5-flash"
    vision_model_override = "gemini-3.1-flash-lite" if client.fallback_allowed(primary_vision_model) else ""
    inspected = inspect_preview(row, directory, account_content_contract=contract, smoke_vision_evidence=evidence,
                                vision_model_override=vision_model_override)
    vision = inspected.get("vision", {})
    if not vision_model_override and current_model_scoped_vision_fallback_allowed(vision, primary_vision_model):
        primary_vision = dict(vision)
        retry_delay = vision.get("retry_delay_seconds")
        client.quota_basis = {
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "retry_delay_seconds": retry_delay if isinstance(retry_delay, (int, float)) and retry_delay > 0 else 60,
            "quota_violations": vision.get("quota_violations", []),
            "origin_run_id": os.environ.get("GITHUB_RUN_ID", "current_request"),
        }
        inspected = inspect_preview(
            row,
            directory,
            account_content_contract=contract,
            smoke_vision_evidence=evidence,
            vision_model_override="gemini-3.1-flash-lite",
        )
        vision = inspected.get("vision", {})
        if vision.get("fallback_used"):
            vision = {
                **vision,
                "fallback_basis_run": client.quota_basis["origin_run_id"],
                "primary_attempt_history": primary_vision.get("attempt_history", []),
                "primary_failure_class": primary_vision.get("failure_class", ""),
            }
            inspected["vision"] = vision
    elif vision.get("fallback_used"):
        vision = {**vision, "fallback_basis_run": client.quota_basis.get("origin_run_id", "")}
        inspected["vision"] = vision
    required = ("visual_summary", "key_moment")
    if vision.get("status") == "PASS" and (not isinstance(vision.get("visible_action"), str)
            or not all(isinstance(vision.get(key), str) and vision[key].strip() for key in required)):
        vision = {**vision, "status": "UNAVAILABLE", "failure_class": "invalid_response"}
    media = {**row, **vision, "media_type": "video", "content_hash": inspected.get("content_hash", ""),
             "vision_status": vision.get("status", "UNAVAILABLE"),
             "technical_status": "PASS" if inspected.get("status") == "PREVIEW_READ_OK" else "UNVERIFIED",
             "rights_status": "unknown", "permission_status": "unverified", "strict_relevance_review": True,
             "visual_evidence": {"status": "UNDERSTOOD" if vision.get("status") == "PASS" else "UNVERIFIED",
                                 "media_asset_id": row["media_asset_id"], "content_hash": inspected.get("content_hash", ""),
                                 "provider": vision.get("provider", "gemini"),
                                 "frame_hashes": [frame["sha256"] for frame in inspected.get("frames", [])]}}
    bundle = SourcePostBundle(source_post_id="", source_id="", target_account_id=account,
                              platform="", profile_url="", canonical_post_url="", external_post_id="",
                              original_post_text="", published_at="")
    media["account_relevance_review"] = relevance_review(media, contract, client)
    service = SourceGroundedCaptionService(PrivacyBoundedGeminiGroundedProvider(client=client),
                                          allow_deterministic_fallback=False, retry_primary_on_alignment_failure=False)
    result = generate_media_first_caption(
        media=media, account_id=account, account_content_contract=contract, recent_posts=[],
        editorial_draft=True, caption_generator=lambda **request: service.generate_media_context(bundle, **request))
    text = str(result.get("public_post_text") or "")
    style_repair = {"public_post_text": text, "repair_count": 0, "repairs": []}
    if text and account == "beauty_account":
        style_repair = repair_style_only(text, account)
        if style_repair["repair_count"]:
            text = style_repair["public_post_text"]
            result = rebind_style_repair_claims(result, text)
            anchor = remove_media_test(
                text, result.get("media_context", {}),
                result.get("post_angles", {}).get("selected", {}),
                result.get("claim_support", []))
            experience = fabricated_media_experience(text)
            reasons = [reason for reason in result.get("blocked_reasons", [])
                       if reason not in {"media_specific_anchor_missing", "source_creator_experience_reassigned"}]
            if anchor.get("status") != "PASS":
                reasons.append("media_specific_anchor_missing")
            reasons.extend(experience.get("reasons", []))
            result = {**result, "style_repair": style_repair, "remove_media_test": anchor,
                      "fabricated_experience_check": experience, "blocked_reasons": reasons,
                      "status": "PASS" if not reasons else "REVIEW_REQUIRED",
                      "public_post_text": text if not reasons else "",
                      "rejected_caption": "" if not reasons else text}
    style = voice_persona_validation(text, account) if text else {"status": "NOT_RUN"}
    if style.get("status") == "VOICE_PERSONA_PASS":
        style = {**style, "status": "PASS", "validator_status": "VOICE_PERSONA_PASS"}
    return {**row, "caption_candidate": client.caption_candidate, "caption_provider_evidence": client.caption_evidence,
            "smoke_vision_evidence": {"media_asset_id": row["media_asset_id"], "account_id": account,
                "content_hash": inspected.get("content_hash", ""), "vision": vision,
                "frame_hashes": media["visual_evidence"]["frame_hashes"]},
            "relevance_provider_evidence": media["account_relevance_review"], "vision": vision, "frames": media["visual_evidence"]["frame_hashes"],
            "result": result, "style": style, "fetch_status": inspected.get("status"),
            "failure_class": str(vision.get("failure_class") or result.get("provider_failure_class") or inspected.get("error_class") or "").upper()}


def summary(packages: list[dict]) -> dict:
    verified = sum(
        p["vision"].get("status") == "PASS"
        and p["result"].get("status") == "PASS"
        and p["result"].get("provider_name") == PrivacyBoundedGeminiGroundedProvider.provider_name
        and p["result"].get("provider_status") == "PASS"
        and bool(p["result"].get("public_post_text"))
        and p["result"].get("remove_media_test", {}).get("status") == "PASS"
        and p["result"].get("fabricated_experience_check", {}).get("status") == "PASS"
        for p in packages)
    e2e = sum(p["vision"].get("status") == "PASS"
              and p["result"].get("status") == "PASS"
              and p["result"].get("account_relevance", {}).get("status") == "PASS"
              and bool(p["result"].get("public_post_text"))
              and p["result"].get("remove_media_test", {}).get("status") == "PASS"
              and p["result"].get("remove_media_test", {}).get("media_anchor_status") == "PASS"
              and p["result"].get("fabricated_experience_check", {}).get("status") == "PASS"
              and p.get("style", {}).get("status") == "PASS" for p in packages)
    return {
        "EDITORIAL_E2E_PASS_COUNT": e2e,
        "TARGET_ACCOUNTS": [p.get("account_id", "") for p in packages],
        "VISION_TARGET_COUNT": len(packages),
        "VISION_VERIFIED_COUNT": sum(p["result"].get("media_context", {}).get("visual_status") == "VISUAL_VERIFIED" for p in packages),
        "RELEVANCE_PASS_COUNT": sum(p["result"].get("account_relevance", {}).get("status") == "PASS" for p in packages),
        "CAPTION_GENERATED_COUNT": sum(bool(p["result"].get("public_post_text")) for p in packages),
        "GITHUB_MODELS_CALLS": 0,
        "VERIFIED_MEDIA_PACKAGE_COUNT": verified,
        "FABRICATED_EXPERIENCE_COUNT": sum(p["result"].get("fabricated_experience_check", {}).get("status") == "BLOCKED" for p in packages),
        "GENERIC_CAPTION_SELECTED_COUNT": sum(bool(p["result"].get("public_post_text")) and p["result"].get("remove_media_test", {}).get("generic_caption_risk") == "HIGH" for p in packages),
        "MEDIA_FIRST_QUALITY_PROVEN": "YES" if packages and e2e == len(packages) and verified == len(packages) else "NO",
    }


def render(packages: list[dict]) -> str:
    lines = ["# Content Quality V2 Vision Smoke Review", "", "Internal editorial drafts only. No publish eligibility is granted.", ""]
    lines += [f"{key}={json.dumps(value) if isinstance(value, list) else value}" for key, value in summary(packages).items()] + [""]
    for package in packages:
        result, vision = package["result"], package["vision"]
        context = result.get("media_context", {})
        anchor = result.get("remove_media_test", {})
        caption_evidence = package.get("caption_provider_evidence", {})
        provider_failed = caption_evidence.get("provider_status") in {"UNAVAILABLE", "ERROR"}
        fields = {
            "MEDIA_FETCH_STATUS": package.get("fetch_status", ""),
            "SMOKE_VISION_EVIDENCE": package.get("smoke_vision_evidence", {}),
            "CAPTION_PROVIDER_EVIDENCE": caption_evidence,
            "CAPTION_CANDIDATE_FOR_REVIEW": package.get("caption_candidate", {}),
            "RELEVANCE_PROVIDER_EVIDENCE": package.get("relevance_provider_evidence", {}),
            "ACCOUNT": package["account_id"], "MEDIA_ASSET_ID": package["media_asset_id"],
            "MEDIA_PREVIEW": package["preview_url"], "VISION_PROVIDER": vision.get("provider", "gemini"),
            "VISION_MODEL": vision.get("model", ""),
            "VISION_REQUESTED_MODEL": vision.get("requested_model", vision.get("model", "")),
            "VISION_FALLBACK_USED": bool(vision.get("fallback_used")),
            "VISION_FALLBACK_BASIS_RUN": vision.get("fallback_basis_run", ""),
            "HTTP_STATUS": vision.get("http_status", ""),
            "PROVIDER_ERROR_TYPE": vision.get("provider_error_type", ""),
            "RESPONSE_SCHEMA_STATUS": vision.get("response_schema_status", "NOT_RUN"),
            **{key.upper(): vision.get(key, "") for key in (
                "raw_response_type", "parse_stage", "schema_error", "missing_fields", "empty_fields",
                "field", "expected_type", "actual_type", "normalizations", "attempt_count")},
            "VISION_STATUS": vision.get("status", "NOT_RUN"), "REPRESENTATIVE_FRAME_HASHES": package["frames"],
            **{key.upper(): vision.get(key, "UNVERIFIED") for key in ("visual_summary", "visible_action", "key_moment", "main_topic")},
            "VISUAL_FACTS": context.get("visual_facts", []),
            "VISUAL_EVIDENCE_STATUS": context.get("visual_evidence", {}).get("status", "UNVERIFIED"),
            "EDITORIAL_DRAFT_ELIGIBILITY": result.get("editorial_draft_eligibility", {}),
            "PUBLISH_ELIGIBILITY": result.get("publish_eligibility", {}),
            "RELEVANCE_STATUS": result.get("account_relevance", {}).get("status", "NOT_RUN"),
            **{key.upper(): vision.get(key, "") for key in (
                "provider_http_status", "provider_error_status", "rate_limit_class", "quota_metric",
                "quota_id", "quota_model", "quota_location", "quota_limit_value", "retry_delay_seconds", "retry_status")},
            "QUOTA_VIOLATIONS": vision.get("quota_violations", []),
            "VISION_ATTEMPT_HISTORY": vision.get("attempt_history", []),
            "VISION_ATTEMPT_COUNT": vision.get("attempt_count", 0),
            **{"RELEVANCE_" + key.upper(): result.get("account_relevance", {}).get(key, "")
               for key in ("attempt_count", "review_status", "decision_class", "reason", "audience_need",
                           "content_pillar", "anchor_fact_types", "provider_status", "provider_http_status", "provider_error_type")},
            **{"RELEVANCE_" + key.upper(): package.get("relevance_provider_evidence", {}).get(key, [] if key in ("quota_violations", "attempt_history") else "")
               for key in ("provider_error_status", "rate_limit_class", "quota_metric", "quota_id", "quota_model",
                           "quota_location", "quota_limit_value", "retry_delay_seconds", "retry_status",
                           "quota_violations", "attempt_history")},
            "WHY_THIS_ACCOUNT_SHOULD_POST_THIS": result.get("account_relevance", {}).get("why_this_account_should_post_this", "UNVERIFIED"),
            "POST_ANGLE_OPTIONS": result.get("post_angles", {}).get("options", []),
            "SELECTED_ANGLE": result.get("post_angles", {}).get("selected", {}),
            "ANCHOR_FACT_IDS": anchor.get("anchor_fact_ids", []),
            "PUBLIC_CAPTION": result.get("public_post_text") or "NOT_GENERATED_OR_REJECTED",
            "CAPTION_PROVIDER": result.get("provider_name", "NOT_RUN"),
            "CAPTION_PROVIDER_STATUS": result.get("provider_status", "NOT_RUN"),
            "MEDIA_ANCHOR_STATUS": anchor.get("media_anchor_status", "NOT_RUN"),
            "CLAIM_SUPPORT": result.get("claim_support", []), "REMOVE_MEDIA_TEST": "NOT_RUN" if provider_failed else anchor.get("status", "NOT_RUN"),
            "GENERIC_CAPTION_RISK": "UNVERIFIED" if provider_failed else anchor.get("generic_caption_risk", "UNVERIFIED"),
            "FABRICATED_EXPERIENCE_CHECK": {"status": "NOT_RUN"} if provider_failed else result.get("fabricated_experience_check", {"status": "NOT_RUN"}),
            "ACCOUNT_STYLE_CHECK": package["style"],
            "STYLE_REPAIR": result.get("style_repair", {"repair_count": 0, "repairs": []}),
            "FAILURE_CLASS": package["failure_class"] or "NONE",
            "WARNINGS": [warning for warning in [package["failure_class"], *result.get("blocked_reasons", [])] if warning],
        }
        lines += [f"## {package['account_id']}", ""]
        for name, value in fields.items():
            lines += [f"{name}=", "", str(value) if isinstance(value, str) else json.dumps(value, ensure_ascii=False), ""]
        lines += ["OWNER_GRADE=[ ]A [ ]B [ ]C", "OWNER_REASON=", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target-account", choices=(*ACCOUNTS, "all"), default="all")
    args = parser.parse_args()
    if os.environ.get("GITHUB_ACTIONS") != "true" or not os.environ.get("RUNNER_TEMP"):
        raise SystemExit("RUNNER_ONLY")
    if any(os.environ.get(key) for key in PRODUCTION_SECRETS):
        raise SystemExit("PRODUCTION_CREDENTIAL_PRESENT")
    for key in ("BUFFERED_POSTING_ENABLED", "PUBLISH_ENABLED", "ALLOW_REAL_THREADS_POST", "ALLOW_REAL_X_POST",
                "ALLOW_MEDIA_POSTS", "ALLOW_CLOUDINARY_UPLOAD"):
        if os.environ.get(key, "false").lower() != "false":
            raise SystemExit("PRODUCTION_GATE_ENABLED")
    print("GEMINI_API_KEY_PRESENT=" + str(bool(os.environ.get("GEMINI_API_KEY"))).lower())
    previews = smoke_previews((ROOT / "docs/CONTENT_QUALITY_V2_REVIEW_PACK.md").read_text(), args.target_account)
    root = Path(os.environ["RUNNER_TEMP"]) / "cq-v2-vision-smoke"
    packages = [build_package(row, root / row["account_id"]) for row in previews]
    review = render(packages)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(review, encoding="utf-8")
    print(review)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as handle:
            handle.write(review)
    # Irrelevant media is a valid Vision proof, but never a successful media package.
    vision_pass = bool(packages) and summary(packages)["VISION_VERIFIED_COUNT"] == len(previews)
    relevant_drafts_pass = all(p["result"].get("status") == "PASS" and p.get("style", {}).get("status") == "PASS" for p in packages
                              if p["result"].get("account_relevance", {}).get("status") == "PASS")
    providers_available = all(p.get("relevance_provider_evidence", {}).get("provider_status")
                              not in {"UNAVAILABLE", "ERROR", "FAILED", "BLOCKED"} for p in packages)
    return 0 if vision_pass and relevant_drafts_pass and providers_available else 1


if __name__ == "__main__":
    raise SystemExit(main())
