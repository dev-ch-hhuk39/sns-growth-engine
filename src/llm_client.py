"""
llm_client.py - Gemini API クライアント（v2 専用）

環境変数:
  GEMINI_API_KEY  : 必須（MOCK_LLM=true または DRY_RUN=true 時は不要）
  GEMINI_MODEL    : オプション（デフォルト: gemini-2.5-flash）
  DRY_RUN         : true の場合、モックレスポンスを返す（シート書き込みも止まる）
  MOCK_LLM        : true の場合、LLM 呼び出しのみモックにする（シート書き込みは行う）

APIキーはログ・例外メッセージに絶対に出力しない。
"""
from __future__ import annotations

import json
import os
import re
import requests

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-2.5-flash"

_DRY_RUN_DRAFT_JSON = {
    "title": "【DRY_RUN】テスト投稿",
    "body_md": "これはDRY_RUNモードのモック投稿です。\n\n\n実際のGeminiレスポンスはDRY_RUN=falseで取得されます。",
    "content": "DRY_RUNモックコンテンツ",
    "cta_text": "相談はLINEで",
    "thumbnail_copy": "",
    "pv_score": 75,
    "cv_score": 65,
    "brand_risk_score": 10,
    "score": 70,
    "score_reason": "DRY_RUNモック値",
    "ai_review": "DRY_RUNのため評価なし",
    "post_mode": "mixed",
}

_DRY_RUN_DERIVATIVE_JSON = {
    "platform": "threads",
    "text": "【DRY_RUN】モック投稿文\n\n\nこれはDRY_RUNモードのサンプルです。",
    "hashtags": "",
    "status": "READY",
    "reason": "DRY_RUNモック",
}

_MOCK_DERIVATIVE_X = {
    "platform": "x",
    "text": "【MOCK】夜職で迷ってるなら読んで。店選びを間違えると3年後の年収が全然違う。",
    "hashtags": "",
    "status": "READY",
    "reason": "MOCK_LLMモック",
}

_MOCK_DERIVATIVE_THREADS = {
    "platform": "threads",
    "text": "店選びを間違えると3年後の年収が全然違う\n\n\nキャバを始めたての子に必ず伝えること。\n\n面接でどの店を選ぶかで、1年後の月収が平均20万円変わる。\n理由は簡単で、バック率・客層・店のサポート体制が全部変わるから。\n\n迷ったら気軽に相談して。",
    "hashtags": "",
    "status": "READY",
    "reason": "MOCK_LLMモック",
}


def call_gemini(prompt: str, system_prompt: str | None = None,
                temperature: float = 0.9, max_tokens: int = 8192) -> str:
    """Gemini REST API を呼び出してテキストを返す。"""
    if _is_mock():
        return json.dumps(_DRY_RUN_DRAFT_JSON, ensure_ascii=False)

    api_key = _get_api_key()
    model = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL).strip()
    url = f"{GEMINI_API_BASE}/{model}:generateContent?key={api_key}"

    contents: list[dict] = []
    if system_prompt:
        contents.append({"role": "user", "parts": [{"text": system_prompt}]})
        contents.append({"role": "model", "parts": [{"text": "了解しました。指示に従います。"}]})
    contents.append({"role": "user", "parts": [{"text": prompt}]})

    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        },
    }

    try:
        resp = requests.post(url, json=payload, timeout=90)
        resp.raise_for_status()
    except requests.HTTPError as e:
        raise RuntimeError(f"Gemini API エラー (HTTP {e.response.status_code})") from e
    except requests.RequestException as e:
        raise RuntimeError(f"Gemini API 接続エラー") from e

    data = resp.json()
    candidates = data.get("candidates", [])
    if not candidates:
        finish = data.get("promptFeedback", {}).get("blockReason", "不明")
        raise RuntimeError(f"Gemini API のレスポンスが空 (blockReason={finish})")

    text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
    return text.strip()


def call_gemini_json(prompt: str, system_prompt: str | None = None,
                     temperature: float = 0.7,
                     dry_run_mock: dict | None = None,
                     platform: str | None = None) -> dict:
    """Gemini API を呼び出して JSON をパースして返す。

    失敗時は {"_error": ..., "_raw": ...} を返す（例外を投げない）。
    dry_run_mock が指定されると MOCK 時にそれを返す。
    platform を指定すると、モック応答が platform-aware になる。
    """
    if _is_mock():
        if dry_run_mock is not None:
            return dict(dry_run_mock)
        if platform == "x":
            return dict(_MOCK_DERIVATIVE_X)
        if platform == "threads":
            return dict(_MOCK_DERIVATIVE_THREADS)
        return dict(_DRY_RUN_DRAFT_JSON)

    try:
        raw = call_gemini(prompt, system_prompt, temperature=temperature)
        return extract_json(raw)
    except Exception as e:
        return {"_error": str(e), "_raw": ""}


def extract_json(text: str) -> dict:
    """テキストから JSON を抽出してパースする。

    以下の形式に対応:
      1. ```json { ... } ``` ブロック
      2. ``` { ... } ``` ブロック
      3. { から } までを直接抽出
      4. テキスト全体を直接パース
    """
    # パターン1・2: コードブロック内の JSON
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # パターン3: { ... } を抽出（ネストを考慮して最外のペアを探す）
    start = text.find("{")
    if start != -1:
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break

    # パターン4: 全体をパース
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    return {"_error": "JSONパース失敗", "_raw": text[:500]}


# ------------------------------------------------------------------ #
# プライベートヘルパー
# ------------------------------------------------------------------ #

def _is_mock() -> bool:
    """DRY_RUN または MOCK_LLM が有効なら True を返す。"""
    dry = os.environ.get("DRY_RUN", "false").strip().lower() in ("1", "true", "yes")
    mock = os.environ.get("MOCK_LLM", "false").strip().lower() in ("1", "true", "yes")
    return dry or mock


def _is_dry_run() -> bool:
    return os.environ.get("DRY_RUN", "false").strip().lower() in ("1", "true", "yes")


def _get_api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise ValueError("GEMINI_API_KEY が未設定です")
    return key
