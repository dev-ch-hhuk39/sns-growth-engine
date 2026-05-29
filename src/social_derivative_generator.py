"""
social_derivative_generator.py - X / Threads 向け派生投稿生成ロジック

処理フロー:
  1. status 条件に合う drafts を取得
  2. platform ごとに social_derivative テンプレートを取得
  3. Gemini でplatform別投稿文を生成
  4. X は 120 文字以内に正規化
  5. Threads は 1行目フック＋2行空け本文に正規化
  6. 重複 draft_id + platform の derivative はスキップ
  7. social_derivatives に保存
  8. logs に記録

Gemini 失敗時はスキップして全体クラッシュさせない。
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sheets_client import SheetsClient, MockSheetsClient

import llm_client
from prompt_loader import (
    build_derivative_variables,
    get_derivative_template,
    render_prompt,
)
from publish_decision import decide_derivative_status

X_MAX_CHARS = 120


def generate_social_derivatives(
    sheets: "SheetsClient | MockSheetsClient",
    account_id: str | None = None,
    platforms: list[str] | None = None,
    status: list[str] | None = None,
    limit: int = 5,
    dry_run: bool = False,
) -> list[dict]:
    """READY な drafts から X / Threads 向け派生投稿を生成して保存する。

    Returns: 生成・保存した derivative 辞書のリスト。
    """
    if platforms is None:
        platforms = ["x", "threads"]
    if status is None:
        status = ["READY"]

    results: list[dict] = []

    for s in status:
        drafts = sheets.get_drafts(account_id=account_id, status=s, limit=limit)
        print(f"\n[derivative_generator] status={s} drafts: {len(drafts)} 件")

        for draft in drafts:
            draft_id = draft.get("draft_id", "")
            acct_id = draft.get("account_id", "")
            account = sheets.get_account(acct_id) or {}

            for platform in platforms:
                if sheets.find_social_derivative(draft_id, platform) is not None:
                    print(f"  [skip] 重複 draft_id={draft_id} platform={platform}")
                    continue

                tmpl = get_derivative_template(sheets, platform)
                if not tmpl:
                    print(f"  [skip] platform={platform} テンプレートなし")
                    continue

                template_text = tmpl.get("prompt_text", "")
                variables = build_derivative_variables(account, draft)
                variables["platform"] = platform
                prompt = render_prompt(template_text, variables)

                print(f"  [{acct_id}] draft_id={draft_id} platform={platform} 生成中...")

                raw = llm_client.call_gemini_json(
                    prompt=prompt,
                    temperature=0.8,
                    platform=platform,
                )

                if "_error" in raw:
                    err = raw["_error"]
                    print(f"  [error] Gemini 失敗: {err}")
                    sheets.log(
                        "generate_derivatives", "ERROR",
                        f"Gemini失敗: {err}",
                        account_id=acct_id,
                        details=f"draft_id={draft_id} platform={platform}",
                    )
                    continue

                derivative = _normalize_derivative(raw, draft, account, platform)
                der_status = decide_derivative_status(derivative, draft, account)
                derivative["status"] = der_status

                der_id = sheets.append_social_derivative(derivative)
                derivative["derivative_id"] = der_id

                sheets.log(
                    "generate_derivatives", "OK",
                    f"derivative生成: platform={platform} status={der_status}",
                    account_id=acct_id,
                    details=f"draft_id={draft_id} derivative_id={der_id}",
                )

                print(f"  [ok] derivative_id={der_id} platform={platform} status={der_status}")
                results.append(derivative)

    print(f"\n[derivative_generator] 生成完了: {len(results)} 件")
    return results


def _normalize_derivative(
    raw: dict,
    draft: dict,
    account: dict,
    platform: str,
) -> dict:
    """Gemini 出力を social_derivatives スキーマに正規化する。"""
    text = str(raw.get("text", ""))
    platform_lower = platform.lower()

    if platform_lower == "x":
        text = _truncate_x(text)
    elif platform_lower == "threads":
        text = _normalize_threads(text, draft)

    return {
        "draft_id":    draft.get("draft_id", ""),
        "account_id":  account.get("account_id", draft.get("account_id", "")),
        "platform":    platform_lower,
        "text":        text,
        "hashtags":    str(raw.get("hashtags", "")),
        "reason":      str(raw.get("reason", "")),
    }


def _truncate_x(text: str) -> str:
    """X 投稿を 120 文字以内に収める。超過時は末尾を省略して「…」を付ける。"""
    text = text.strip()
    if len(text) <= X_MAX_CHARS:
        return text
    return text[: X_MAX_CHARS - 1] + "…"


def _normalize_threads(text: str, draft: dict) -> str:
    """Threads 投稿のフォーマットを確認・修正する。

    要件: 1行目にキャッチーなコピー → 2行空け → 本文
    Gemini が正しいフォーマットで返せば変更しない。
    フォーマット崩れの場合は draft.title をフックとして先頭に置く。
    """
    text = text.strip()

    # 2行空き（空行2行 = \n\n\n）が含まれているか確認
    if "\n\n\n" in text or "\n\n" in text:
        return text

    # フォーマット不正 → draft.title をフックにして再構成
    hook = draft.get("title", "").strip()
    if hook:
        return f"{hook}\n\n\n{text}"
    return text
