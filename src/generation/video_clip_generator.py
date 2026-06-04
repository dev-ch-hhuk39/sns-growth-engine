"""
video_clip_generator.py - クリップ候補からX/Threads投稿文を生成する（Phase 2.24）

設計:
  - video_clip_candidates タブのクリップ候補を入力とする
  - Gemini でX/Threads向け投稿文を生成する
  - mock_llm=True の場合は固定サンプルを返す（実API呼び出しなし）
  - 権利ゲート: rights_status=unknown/not_allowed は READY に昇格しない
  - media_reuse_risk=high も READY に昇格しない
  - 全投稿は WAITING_REVIEW 状態でキューに追加する（READY は人間レビュー後のみ）
  - 生成後: draft → social_derivatives → queue (WAITING_REVIEW) の順で保存
  - テキストポリシーチェック実施（X: soft=120/hard=140, Threads: soft=600/hard=800）
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from text_policy import check_text_policy

JST = timezone(timedelta(hours=9))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_uuid() -> str:
    return str(uuid.uuid4())[:8]


# --------------------------------------------------------------------------- #
# プロンプト
# --------------------------------------------------------------------------- #

_SYSTEM_PROMPT = """あなたはSNSコンテンツライターです。
動画クリップの情報から、X（旧Twitter）とThreads向けの投稿文を生成してください。

重要なルール:
- 本文の模倣ではなく「勝ち要素・切り口」を参考にする
- 視聴者の感情・行動を引き出す文体
- CTAは控えめに（強引な営業文は禁止）
"""

_USER_PROMPT_TEMPLATE = """以下のクリップ情報から、SNS投稿文を生成してください。

## クリップ情報
- アカウント: {account_id}
- クリップタイトル: {clip_title}
- フック: {hook}
- なぜ有効か: {why_it_works}
- ターゲットペルソナ: {target_persona}
- X投稿の切り口: {x_post_angle}
- Threads投稿の切り口: {threads_post_angle}
- 文字起こし抜粋: {transcript_excerpt}

## 出力形式（JSONで返すこと）
{{
  "x_text": "X向け投稿文（120文字以内）",
  "threads_text": "Threads向け投稿文（600文字以内）",
  "title": "下書きタイトル（30字以内）",
  "hypothesis": "この投稿が効果的な理由（50字以内）",
  "media_strategy": "none / reference_image のいずれか"
}}
"""

_MOCK_GENERATION = {
    "x_text": "[MOCK] 夜職を検討中の方へ。スカウト目線で語る「稼げる子の共通点」とは？気になる方はDMを。",
    "threads_text": "[MOCK] 業界歴10年のスカウトマンが語る本音。稼げる子と稼げない子の差は○○だけ。最初のお店選びで将来が変わる。詳しくはプロフィールから。",
    "title": "[MOCK] クリップ生成テスト下書き",
    "hypothesis": "スカウト目線の本音トークは信頼感を生む",
    "media_strategy": "none",
}


# --------------------------------------------------------------------------- #
# 権利ゲート
# --------------------------------------------------------------------------- #

def _is_rights_blocked(candidate: dict[str, Any]) -> bool:
    """rights_status=unknown/not_allowed または media_reuse_risk=high は READY 昇格禁止。"""
    rights = str(candidate.get("rights_status", "unknown")).lower()
    risk = str(candidate.get("media_reuse_risk", "low")).lower()
    if rights in ("unknown", "not_allowed"):
        return True
    if risk == "high":
        return True
    return False


# --------------------------------------------------------------------------- #
# 生成コア
# --------------------------------------------------------------------------- #

def generate_from_clip(
    candidate: dict[str, Any],
    account: dict[str, Any],
    *,
    mock_llm: bool = True,
) -> dict[str, Any]:
    """クリップ候補1件からX/Threads投稿文を生成する。

    Returns:
        {"x_text": str, "threads_text": str, "title": str, "hypothesis": str, "media_strategy": str}
    """
    if mock_llm:
        return dict(_MOCK_GENERATION)

    try:
        from llm_client import call_gemini_json
    except ImportError:
        return dict(_MOCK_GENERATION)

    account_id = str(account.get("account_id", ""))
    prompt = _USER_PROMPT_TEMPLATE.format(
        account_id=account_id,
        clip_title=str(candidate.get("clip_title", ""))[:50],
        hook=str(candidate.get("hook", ""))[:100],
        why_it_works=str(candidate.get("why_it_works", ""))[:100],
        target_persona=str(candidate.get("target_persona", ""))[:50],
        x_post_angle=str(candidate.get("x_post_angle", ""))[:100],
        threads_post_angle=str(candidate.get("threads_post_angle", ""))[:200],
        transcript_excerpt=str(candidate.get("transcript_excerpt", ""))[:300],
    )
    result = call_gemini_json(system_prompt=_SYSTEM_PROMPT, user_prompt=prompt)
    if isinstance(result, dict):
        return result
    return dict(_MOCK_GENERATION)


def _check_and_truncate(text: str, platform: str) -> tuple[str, str]:
    """テキストをポリシーチェックして (text, policy_status) を返す。"""
    policy = check_text_policy(text, platform)
    if policy.status == "FAIL":
        hard = 140 if platform == "x" else 800
        text = text[:hard]
        policy = check_text_policy(text, platform)
    return text, policy.status


# --------------------------------------------------------------------------- #
# 保存パイプライン
# --------------------------------------------------------------------------- #

def save_clip_generation_result(
    client: Any,
    candidate: dict[str, Any],
    generation: dict[str, Any],
    *,
    account_id: str,
    dry_run: bool = True,
) -> dict[str, Any]:
    """生成結果を draft → social_derivatives → queue (WAITING_REVIEW) の順で保存する。

    権利ゲートに引っかかる場合は draft_status=WAITING_REVIEW のまま保存し、
    queue には追加しない。

    Returns:
        {"draft_id": str, "queue_ids": list, "rights_blocked": bool}
    """
    clip_id = str(candidate.get("clip_id", ""))
    rights_blocked = _is_rights_blocked(candidate)

    x_text, x_policy = _check_and_truncate(generation.get("x_text", ""), "x")
    threads_text, threads_policy = _check_and_truncate(generation.get("threads_text", ""), "threads")

    draft_status = "WAITING_REVIEW"
    draft_id = f"d-{_short_uuid()}"

    draft_data = {
        "draft_id": draft_id,
        "account_id": account_id,
        "title": generation.get("title", "クリップ生成下書き")[:100],
        "body_md": threads_text,
        "content": x_text,
        "status": draft_status,
        "generation_mode": "video_clip",
        "hypothesis": generation.get("hypothesis", ""),
        "media_strategy": generation.get("media_strategy", "none"),
        "video_clip_id": clip_id,
        "source_video_url": str(candidate.get("source_video_url", "")),
        "source_time_range": f"{candidate.get('start_time', '')}~{candidate.get('end_time', '')}",
        "confidence_level": "MEDIUM",
        "ai_publish_recommendation": "review",
        "notes": f"clip_id={clip_id} rights_blocked={rights_blocked}",
    }

    if dry_run:
        print(
            f"[dry-run] save_draft: draft_id={draft_id!r} "
            f"clip_id={clip_id!r} rights_blocked={rights_blocked}"
        )
    else:
        client.save_draft(
            account_id=account_id,
            title=draft_data["title"],
            body_md=draft_data["body_md"],
            **{k: v for k, v in draft_data.items()
               if k not in ("account_id", "title", "body_md")},
        )

    queue_ids: list[str] = []

    if not rights_blocked:
        for platform, text, policy in [("x", x_text, x_policy), ("threads", threads_text, threads_policy)]:
            sd_id = f"sd-{_short_uuid()}"
            sd_data = {
                "derivative_id": sd_id,
                "draft_id": draft_id,
                "account_id": account_id,
                "platform": platform,
                "text": text,
                "hashtags": "",
                "status": "WAITING_REVIEW",
                "reason": "video_clip_generation",
                "char_count": str(len(text)),
                "text_policy_status": policy,
                "video_clip_id": clip_id,
                "source_time_range": draft_data["source_time_range"],
            }
            if dry_run:
                print(
                    f"[dry-run] append_social_derivative: "
                    f"platform={platform!r} chars={len(text)} policy={policy!r}"
                )
            else:
                client.append_social_derivative(sd_data)

            q_id = f"q-{_short_uuid()}"
            q_data = {
                "queue_id": q_id,
                "draft_id": draft_id,
                "account_id": account_id,
                "platform": platform,
                "priority": "3",
                "status": "WAITING_REVIEW",
                "generation_mode": "video_clip",
                "confidence_level": "MEDIUM",
                "ai_publish_recommendation": "review",
                "text_policy_status": policy,
                "video_clip_id": clip_id,
                "rights_status": str(candidate.get("rights_status", "unknown")),
                "permission_status": str(candidate.get("permission_status", "unknown")),
            }
            if dry_run:
                print(
                    f"[dry-run] append_queue_item: "
                    f"platform={platform!r} status=WAITING_REVIEW"
                )
            else:
                client.append_queue_item(q_data)
            queue_ids.append(q_id)
    else:
        print(
            f"[rights-gate] clip_id={clip_id!r} "
            f"rights_status={candidate.get('rights_status', '?')!r} "
            f"media_reuse_risk={candidate.get('media_reuse_risk', '?')!r} "
            f"→ queue 追加スキップ（人間レビュー必要）"
        )

    if not dry_run:
        client.update_video_clip_candidate(
            clip_id,
            text_generation_status="done",
            generated_draft_id=draft_id,
            generated_at=_now(),
        )

    return {"draft_id": draft_id, "queue_ids": queue_ids, "rights_blocked": rights_blocked}


# --------------------------------------------------------------------------- #
# バッチ処理
# --------------------------------------------------------------------------- #

def generate_from_clips_batch(
    candidates: list[dict[str, Any]],
    client: Any,
    account: dict[str, Any],
    *,
    mock_llm: bool = True,
    dry_run: bool = True,
) -> dict[str, Any]:
    """複数クリップ候補から一括生成・保存する。

    Returns:
        {"total": int, "generated": int, "rights_blocked": int, "errors": int}
    """
    account_id = str(account.get("account_id", ""))
    total = len(candidates)
    generated = rights_blocked_count = errors = 0

    for c in candidates:
        clip_id = c.get("clip_id", "?")
        try:
            gen = generate_from_clip(c, account, mock_llm=mock_llm)
            result = save_clip_generation_result(
                client, c, gen,
                account_id=account_id,
                dry_run=dry_run,
            )
            generated += 1
            if result["rights_blocked"]:
                rights_blocked_count += 1
            print(
                f"[clip-generator] clip_id={clip_id!r} "
                f"draft_id={result['draft_id']!r} "
                f"rights_blocked={result['rights_blocked']}"
            )
        except Exception as e:
            print(f"[ERROR] generate_from_clip 失敗 (clip_id={clip_id!r}): {e}")
            errors += 1

    return {
        "total": total,
        "generated": generated,
        "rights_blocked": rights_blocked_count,
        "errors": errors,
    }
