"""
reference_based_generator.py — reference_based / original_hypothesis 投稿生成（Phase 2.14）

generation_jobs の各レコードに対してGemini APIを呼び出し、
投稿文を生成して drafts タブに保存する。

安全ガード:
  MOCK_LLM=true または DRY_RUN=true の場合、実APIを呼び出さない。
  文字数ポリシー違反時は最大2回リライトし、失敗後は WAITING_REVIEW 状態で保存する。
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from llm_client import call_gemini_json
from seeds import ACCOUNT_FORBIDDEN_KEYWORDS
from text_policy import check_text_policy

JST = timezone(timedelta(hours=9))

_MAX_REWRITE_ATTEMPTS = 2

_CHAR_LIMITS = {
    "x": {"soft": 120, "hard": 140},
    "threads": {"soft": 500, "hard": 800},
}

_MOCK_GENERATION_RESPONSE = {
    "content": "[MOCK] テスト投稿文です。参考投稿の勝ち要素を活かしました。",
    "title": "テスト下書き",
    "cta_text": "",
    "hypothesis": "",
    "media_strategy": "none",
    "generation_notes": "mock response",
}


# ------------------------------------------------------------------ #
# プロンプト構築
# ------------------------------------------------------------------ #

def _get_account_ng_block(account_id: str) -> str:
    """アカウント固有の禁止キーワードブロックを生成する。"""
    kws = ACCOUNT_FORBIDDEN_KEYWORDS.get(account_id, [])
    if not kws:
        return ""
    lines = "\n".join(f"- {kw}" for kw in kws)
    return f"\n## アカウント固有禁止事項（{account_id}）\n以下のキーワード・テーマを投稿本文・CTAに含めないこと:\n{lines}"


def build_reference_based_prompt(
    job: dict,
    score: dict,
    account: dict,
    platform: str,
) -> str:
    """reference_based モードのGeminiプロンプトを構築する。"""
    limits = _CHAR_LIMITS.get(platform, {"soft": 120, "hard": 140})
    soft = limits["soft"]
    hard = limits["hard"]

    if platform == "x":
        char_constraint = f"{soft}文字以内（絶対に{hard}文字を超えないこと）"
    else:
        char_constraint = f"{soft}文字以内（推奨）、{hard}文字を超えないこと"

    account_id = account.get("account_id", "")
    ng_block = _get_account_ng_block(account_id)

    return f"""あなたはSNSコンテンツライターです。
以下の「参考投稿分析」を読み、その勝ち要素を活かした新しい投稿文を書いてください。

## アカウント情報
- アカウントID: {account_id}
- プラットフォーム: {platform}
- ターゲットペルソナ: {account.get("target_persona", "")}
- トーン: {account.get("tone", "")}
- ジャンル: {account.get("main_genre", "")}

## 参考投稿分析
- フックスタイル: {score.get("hook_style", "")}
- コンテンツアングル: {score.get("content_angle", "")}
- バズ理由: {score.get("why_it_grew", "")}
- 再現ヒント: {score.get("replay_tip", "")}
- バズスコア: {score.get("buzz_score", 0)}

## 文字数制約
{char_constraint}

## 禁止事項
- 参考投稿のテキストを直接コピー・引用しないこと
- 元投稿のアカウント名・固有名詞をそのまま使わないこと{ng_block}

## 出力形式（JSONのみ）
{{"content":"投稿本文","title":"タイトル（任意）","cta_text":"CTA（省略可）","media_strategy":"none","generation_notes":"生成メモ"}}"""


def build_original_hypothesis_prompt(
    job: dict,
    account: dict,
    platform: str,
    hypothesis_hint: str = "",
) -> str:
    """original_hypothesis モードのGeminiプロンプトを構築する。"""
    limits = _CHAR_LIMITS.get(platform, {"soft": 120, "hard": 140})
    soft = limits["soft"]
    hard = limits["hard"]

    if platform == "x":
        char_constraint = f"{soft}文字以内（絶対に{hard}文字を超えないこと）"
    else:
        char_constraint = f"{soft}文字以内（推奨）、{hard}文字を超えないこと"

    account_id = account.get("account_id", "")
    ng_block = _get_account_ng_block(account_id)

    return f"""あなたはSNSコンテンツライターです。
以下の「アカウント情報」をもとに、オリジナルの投稿文を書いてください。

## アカウント情報
- アカウントID: {account_id}
- プラットフォーム: {platform}
- ターゲットペルソナ: {account.get("target_persona", "")}
- トーン: {account.get("tone", "")}
- ジャンル: {account.get("main_genre", "")}

## 仮説テーマ（任意）
{hypothesis_hint or "（自由に設定してください）"}

## 文字数制約
{char_constraint}{ng_block}

## 出力形式（JSONのみ）
{{"content":"投稿本文","title":"タイトル（任意）","cta_text":"CTA（省略可）","hypothesis":"採用した仮説","media_strategy":"none","generation_notes":"生成メモ"}}"""


# ------------------------------------------------------------------ #
# レスポンスパース
# ------------------------------------------------------------------ #

def parse_generation_response(raw: dict | str) -> dict[str, Any]:
    """Gemini レスポンス（dict or JSON文字列）を正規化する。"""
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {}
    else:
        data = raw or {}

    return {
        "content": str(data.get("content", "")).strip(),
        "title": str(data.get("title", "")).strip(),
        "cta_text": str(data.get("cta_text", "")).strip(),
        "hypothesis": str(data.get("hypothesis", "")).strip(),
        "media_strategy": str(data.get("media_strategy", "none")).strip() or "none",
        "generation_notes": str(data.get("generation_notes", "")).strip(),
    }


# ------------------------------------------------------------------ #
# 生成フロー
# ------------------------------------------------------------------ #

def _call_with_rewrite(
    prompt: str,
    platform: str,
    mock_response: dict,
    max_attempts: int = _MAX_REWRITE_ATTEMPTS,
) -> tuple[dict, str]:
    """プロンプトを実行し、文字数ポリシーを満たすまで最大 max_attempts 回リライトする。

    Returns:
        (parsed_response, final_text_policy_status)
    """
    current_prompt = prompt
    last_response = mock_response.copy()
    last_status = "FAIL"

    for attempt in range(1, max_attempts + 2):
        raw = call_gemini_json(current_prompt, dry_run_mock=mock_response)
        parsed = parse_generation_response(raw)
        content = parsed["content"]

        if not content:
            continue

        policy = check_text_policy(content, platform)
        last_response = parsed
        last_status = policy.status

        if policy.status in ("OK", "WARN"):
            return parsed, policy.status

        if attempt <= max_attempts:
            limits = _CHAR_LIMITS.get(platform, {"soft": 120, "hard": 140})
            hard = limits["hard"]
            current_prompt = (
                f"{prompt}\n\n"
                f"## 再試行指示（試行 {attempt}/{max_attempts}）\n"
                f"前回の生成文は{policy.char_count}文字で{hard}文字制限を超えました。\n"
                f"必ず{hard}文字以内に収めてください。"
            )

    return last_response, last_status


def generate_from_reference(
    job: dict,
    score: dict,
    account: dict,
    platform: str,
) -> dict[str, Any]:
    """reference_based モードで投稿文を生成する。

    Returns:
        生成結果dict（content, title, cta_text, media_strategy,
                      generation_notes, text_policy_status, generation_mode）
    """
    prompt = build_reference_based_prompt(job, score, account, platform)
    parsed, policy_status = _call_with_rewrite(
        prompt=prompt,
        platform=platform,
        mock_response=_MOCK_GENERATION_RESPONSE,
    )
    return {
        **parsed,
        "generation_mode": "reference_based",
        "text_policy_status": policy_status,
        "reference_post_id": str(job.get("reference_post_id", "")),
        "reference_post_score_id": str(job.get("reference_post_score_id", "")),
    }


def generate_original_hypothesis(
    job: dict,
    account: dict,
    platform: str,
    hypothesis_hint: str = "",
) -> dict[str, Any]:
    """original_hypothesis モードで投稿文を生成する。

    Returns:
        生成結果dict（content, title, cta_text, media_strategy,
                      hypothesis, generation_notes, text_policy_status, generation_mode）
    """
    prompt = build_original_hypothesis_prompt(
        job=job, account=account, platform=platform, hypothesis_hint=hypothesis_hint
    )
    parsed, policy_status = _call_with_rewrite(
        prompt=prompt,
        platform=platform,
        mock_response=_MOCK_GENERATION_RESPONSE,
    )
    return {
        **parsed,
        "generation_mode": "original_hypothesis",
        "text_policy_status": policy_status,
        "reference_post_id": "",
        "reference_post_score_id": "",
    }


# ------------------------------------------------------------------ #
# 下書き正規化
# ------------------------------------------------------------------ #

def normalize_generated_draft(
    generation_result: dict,
    job: dict,
    account_id: str,
    generation_model: str = "",
) -> dict[str, Any]:
    """生成結果を drafts タブ保存用 dict に変換する。

    text_policy_status が FAIL の場合は status="WAITING_REVIEW" にする。
    """
    policy_status = str(generation_result.get("text_policy_status", "OK"))
    if policy_status == "FAIL":
        draft_status = "WAITING_REVIEW"
    else:
        draft_status = "DRAFT"

    return {
        "draft_id": str(uuid.uuid4()),
        "account_id": account_id,
        "title": str(generation_result.get("title", "")).strip() or "生成下書き",
        "body_md": str(generation_result.get("content", "")).strip(),
        "content": str(generation_result.get("content", "")).strip(),
        "cta_text": str(generation_result.get("cta_text", "")).strip(),
        "status": draft_status,
        "generation_model": generation_model or "gemini",
        "generation_mode": str(generation_result.get("generation_mode", "reference_based")),
        "hypothesis": str(generation_result.get("hypothesis", "")).strip(),
        "media_strategy": str(generation_result.get("media_strategy", "none")),
        "notes": str(generation_result.get("generation_notes", "")),
        "rewrite_count": "0",
    }


# ------------------------------------------------------------------ #
# ジョブ実行
# ------------------------------------------------------------------ #

def execute_generation_job(
    job: dict,
    scores_by_id: dict[str, dict],
    account: dict,
    client: Any,
    dry_run: bool = True,
) -> dict[str, Any]:
    """1件の generation_job を実行して draft を保存する。

    Returns:
        {"job_id": str, "draft_id": str, "status": str, "text_policy_status": str}
    """
    job_id = str(job.get("job_id", ""))
    account_id = str(job.get("account_id", ""))
    platform = str(job.get("platform", "x"))
    mode = str(job.get("generation_mode", "reference_based"))

    if mode == "reference_based":
        ref_score_id = str(job.get("reference_post_score_id", ""))
        score = scores_by_id.get(ref_score_id, {})
        result = generate_from_reference(
            job=job, score=score, account=account, platform=platform
        )
    else:
        result = generate_original_hypothesis(
            job=job, account=account, platform=platform
        )

    draft = normalize_generated_draft(
        generation_result=result,
        job=job,
        account_id=account_id,
    )

    draft_id = draft["draft_id"]
    text_policy = result.get("text_policy_status", "OK")

    if not dry_run:
        client.save_draft(
            account_id=account_id,
            title=draft["title"],
            body_md=draft["body_md"],
            **{k: v for k, v in draft.items() if k not in ("account_id", "title", "body_md")},
        )
        client.update_generation_job(
            job_id=job_id,
            status="done",
            generated_draft_id=draft_id,
            generated_at=datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        )
    else:
        print(
            f"[dry-run] execute_generation_job: "
            f"job_id={job_id[:8]}... "
            f"mode={mode} "
            f"policy={text_policy} "
            f"content={draft['body_md'][:40]!r}..."
        )

    return {
        "job_id": job_id,
        "draft_id": draft_id,
        "status": draft["status"],
        "text_policy_status": text_policy,
        "generation_mode": mode,
    }


def execute_generation_jobs(
    jobs: list[dict],
    scores: list[dict],
    account: dict,
    client: Any,
    dry_run: bool = True,
) -> list[dict[str, Any]]:
    """複数の generation_job を実行する。

    Returns:
        各ジョブの実行結果リスト
    """
    scores_by_id = {str(s.get("score_id", "")): s for s in scores}
    results = []
    for job in jobs:
        try:
            result = execute_generation_job(
                job=job,
                scores_by_id=scores_by_id,
                account=account,
                client=client,
                dry_run=dry_run,
            )
            results.append(result)
        except Exception as e:
            job_id = str(job.get("job_id", "?"))
            print(f"[ERROR] execute_generation_job 失敗 job_id={job_id[:8]}...: {e}")
            results.append({
                "job_id": job_id,
                "draft_id": "",
                "status": "FAILED",
                "text_policy_status": "FAIL",
                "generation_mode": job.get("generation_mode", ""),
            })
    return results
