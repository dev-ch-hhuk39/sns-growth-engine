"""
prompt_loader.py - プロンプトテンプレートの取得・変数展開

Google Sheets の prompt_templates タブからテンプレートを取得する。
接続できない場合は seeds.py のデフォルトテンプレートにフォールバックする。

変数置換構文: {{variable_name}}
未定義の変数は空文字に置換する（例外を投げない）。
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sheets_client import SheetsClient, MockSheetsClient

from seeds import PROMPT_TEMPLATE_SEEDS


def get_prompt_template(
    sheets: "SheetsClient | MockSheetsClient | None",
    template_name: str,
    account_id: str | None = None,
    version: str | None = None,
) -> dict | None:
    """prompt_templates からテンプレート辞書を返す。

    sheets が None または取得失敗時は seeds.py のデフォルトにフォールバックする。
    version を指定すると完全一致で絞り込む。
    """
    candidates: list[dict] = []

    if sheets is not None:
        try:
            rows = sheets.get_prompt_templates(account_id=account_id, active_only=True)
            candidates = [r for r in rows if r.get("template_name") == template_name]
        except Exception as e:
            print(f"[prompt_loader] Sheetsからのテンプレート取得失敗。fallback使用: {e}")

    if not candidates:
        candidates = [
            r for r in PROMPT_TEMPLATE_SEEDS
            if r.get("template_name") == template_name
            and str(r.get("active", "")).upper() == "TRUE"
        ]
        if account_id is not None:
            filtered = [r for r in candidates if r.get("account_id") in (account_id, "")]
            candidates = filtered if filtered else candidates

    if not candidates:
        return None

    if version:
        versioned = [r for r in candidates if r.get("version") == version]
        if versioned:
            candidates = versioned

    # 最後のバージョンを優先（バージョン番号の辞書順で最後）
    candidates = sorted(candidates, key=lambda r: str(r.get("version", "")))
    return candidates[-1]


def get_draft_generation_template(
    sheets: "SheetsClient | MockSheetsClient | None",
    account_id: str,
) -> dict | None:
    """アカウントに対応する下書き生成テンプレートを返す。"""
    template_name_map = {
        "night_scout": "draft_generation_night_scout_v1",
        "liver_manager": "draft_generation_liver_manager_v1",
    }
    template_name = template_name_map.get(account_id)
    if not template_name:
        return None
    return get_prompt_template(sheets, template_name, account_id=account_id)


def get_derivative_template(
    sheets: "SheetsClient | MockSheetsClient | None",
    platform: str,
) -> dict | None:
    """platform に対応する social_derivative テンプレートを返す。"""
    template_name_map = {
        "x": "social_derivative_x_v1",
        "threads": "social_derivative_threads_v1",
    }
    template_name = template_name_map.get(platform.lower())
    if not template_name:
        return None
    return get_prompt_template(sheets, template_name)


def get_scoring_template(
    sheets: "SheetsClient | MockSheetsClient | None",
) -> dict | None:
    """スコアリングテンプレートを返す。"""
    return get_prompt_template(sheets, "draft_scoring_v1")


def render_prompt(template_text: str, variables: dict[str, Any]) -> str:
    """{{variable}} 形式のプレースホルダーを variables で置換する。

    未定義の変数は空文字に置換する（例外なし）。
    """
    def replacer(m: re.Match) -> str:
        key = m.group(1).strip()
        val = variables.get(key)
        if val is None:
            return ""
        return str(val)

    return re.sub(r"\{\{(\w+)\}\}", replacer, template_text)


def build_draft_variables(account: dict, category: dict, reference: dict | None = None) -> dict:
    """下書き生成プロンプト用の変数辞書を構築する。"""
    ref = reference or {}
    return {
        "account_id":           account.get("account_id", ""),
        "account_name":         account.get("account_name", ""),
        "platform":             account.get("platform", "x,threads"),
        "target_persona":       account.get("target_persona", ""),
        "tone":                 account.get("tone", ""),
        "line_url":             account.get("line_url", ""),
        "cta_text":             account.get("cta_text", "相談はLINEで↓"),
        "category_name":        category.get("category_name", ""),
        "category_description": category.get("description", ""),
        "reference_summary":    ref.get("text", ""),
        "reference_hook":       ref.get("extracted_hook", ""),
        "reference_pain":       ref.get("extracted_pain", ""),
        "reference_desire":     ref.get("extracted_desire", ""),
        "reusable_pattern":     ref.get("reusable_pattern", ""),
    }


def build_derivative_variables(account: dict, draft: dict) -> dict:
    """social_derivative プロンプト用の変数辞書を構築する。"""
    return {
        "account_id":     account.get("account_id", ""),
        "account_name":   account.get("account_name", ""),
        "target_persona": account.get("target_persona", ""),
        "tone":           account.get("tone", ""),
        "line_url":       account.get("line_url", ""),
        "cta_text":       account.get("cta_text", "相談はLINEで↓"),
        "title":          draft.get("title", ""),
        "body_md":        draft.get("body_md", ""),
        "platform":       "",
    }
