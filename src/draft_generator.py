"""
draft_generator.py - SNS投稿下書き生成ロジック

処理フロー:
  1. active accounts を取得（account_id 指定で絞り込み可）
  2. content_categories から active カテゴリをランダム選択
  3. reference_posts があれば活用（なければカテゴリベースのみ）
  4. prompt_templates から生成プロンプトを取得
  5. Gemini で draft JSON を生成
  6. publish_decision で status を判定
  7. drafts に保存
  8. logs に記録

dry_run=True のとき書き込みはすべてスキップ（SheetsClient/MockSheetsClient に委ねる）。
Gemini 失敗時はスキップしてログに残す（全体クラッシュしない）。
"""
from __future__ import annotations

import os
import random
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sheets_client import SheetsClient, MockSheetsClient

import llm_client
from prompt_loader import (
    build_draft_variables,
    get_draft_generation_template,
    render_prompt,
)
from publish_decision import decide_draft_status


def generate_drafts(
    sheets: "SheetsClient | MockSheetsClient",
    account_id: str | None = None,
    limit: int = 5,
    dry_run: bool = False,
) -> list[dict]:
    """アクティブアカウントごとに下書きを生成して drafts に保存する。

    Returns: 生成・保存した draft 辞書のリスト（dry_run 含む）。
    """
    mock_llm = os.environ.get("MOCK_LLM", "false").strip().lower() in ("1", "true", "yes")
    results: list[dict] = []

    accounts = sheets.get_active_accounts()
    if account_id:
        accounts = [a for a in accounts if a.get("account_id") == account_id]

    if not accounts:
        print(f"[draft_generator] 対象アカウントが見つかりません: account_id={account_id}")
        return results

    per_account = max(1, limit // len(accounts))

    for account in accounts:
        acct_id = account.get("account_id", "")
        print(f"\n[draft_generator] アカウント: {acct_id}")

        categories = sheets.get_active_categories(acct_id)
        if not categories:
            print(f"  [skip] active カテゴリがありません")
            sheets.log("generate_drafts", "WARN", f"カテゴリなし", account_id=acct_id)
            continue

        ref_posts = sheets.get_reference_posts(account_id=acct_id, status="ready", limit=10)

        tmpl = get_draft_generation_template(sheets, acct_id)
        if not tmpl:
            print(f"  [skip] プロンプトテンプレートが見つかりません")
            sheets.log("generate_drafts", "WARN", f"テンプレートなし", account_id=acct_id)
            continue

        template_text = tmpl.get("prompt_text", "")
        template_name = tmpl.get("template_name", "")

        for i in range(per_account):
            category = random.choice(categories)
            ref = random.choice(ref_posts) if ref_posts else None

            variables = build_draft_variables(account, category, ref)
            prompt = render_prompt(template_text, variables)

            print(f"  [{i+1}/{per_account}] カテゴリ: {category.get('category_name')} 生成中...")

            mock_draft = {
                **llm_client._DRY_RUN_DRAFT_JSON,
                "category_id": category.get("category_id", ""),
            }

            raw = llm_client.call_gemini_json(
                prompt=prompt,
                temperature=0.9,
                dry_run_mock=mock_draft,
            )

            if "_error" in raw:
                err_msg = raw["_error"]
                print(f"  [error] Gemini 生成失敗: {err_msg}")
                sheets.log("generate_drafts", "ERROR", f"Gemini失敗: {err_msg}", account_id=acct_id)
                continue

            draft = _normalize_draft(raw, account, category, template_name)
            status = decide_draft_status(draft, account)
            draft["status"] = status

            draft_id = sheets.save_draft(
                account_id=acct_id,
                title=draft.get("title", ""),
                body_md=draft.get("body_md", ""),
                **{k: v for k, v in draft.items()
                   if k not in ("title", "body_md", "account_id", "draft_id")},
            )
            draft["draft_id"] = draft_id

            if ref and not dry_run:
                try:
                    sheets.update_reference_post_status(ref.get("id", ""), "used")
                except Exception as e:
                    print(f"  [warn] reference_post status 更新失敗: {e}")

            sheets.log(
                "generate_drafts", "OK",
                f"draft生成: {draft.get('title', '')[:30]} status={status}",
                account_id=acct_id,
                details=f"draft_id={draft_id} score={draft.get('score')} category={category.get('category_name')}",
            )

            print(f"  [ok] draft_id={draft_id} status={status} score={draft.get('score')}")
            results.append(draft)

    print(f"\n[draft_generator] 生成完了: {len(results)} 件")
    return results


def _normalize_draft(
    raw: dict,
    account: dict,
    category: dict,
    template_name: str,
) -> dict:
    """Gemini JSON 出力を drafts スキーマに合わせて正規化する。"""
    def safe_int(val: Any, default: int = 0) -> int:
        try:
            return int(float(str(val))) if val not in ("", None) else default
        except (ValueError, TypeError):
            return default

    score = safe_int(raw.get("score") or raw.get("pv_score"), 0)
    pv_score = safe_int(raw.get("pv_score"), score)
    cv_score = safe_int(raw.get("cv_score"), 0)
    brand_risk = safe_int(raw.get("brand_risk_score"), 50)

    return {
        "account_id":        account.get("account_id", ""),
        "title":             str(raw.get("title", ""))[:200],
        "body_md":           str(raw.get("body_md", raw.get("content", ""))),
        "content":           str(raw.get("content", raw.get("body_md", ""))),
        "cta_text":          str(raw.get("cta_text", account.get("cta_text", ""))),
        "thumbnail_copy":    str(raw.get("thumbnail_copy", "")),
        "source_refs":       category.get("category_id", ""),
        "generation_model":  os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
        "prompt_version":    template_name,
        "pv_score":          str(pv_score),
        "cv_score":          str(cv_score),
        "brand_risk_score":  str(brand_risk),
        "score":             str(score),
        "score_reason":      str(raw.get("score_reason", "")),
        "ai_review":         str(raw.get("ai_review", "")),
        "post_mode":         str(raw.get("post_mode", "mixed")),
    }
