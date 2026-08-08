"""Source-grounded reference rewriting for SNS reference posts.

This module is intentionally side-effect free except for the Gemini HTTPS call.
It never publishes, uploads media, or writes Google Sheets.

The source material is the semantic boundary. Video references require a
transcript; YouTube/TikTok metadata alone is not considered semantically ready.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from typing import Any

import requests

DEFAULT_MODEL = "gemini-3.6-flash"
MAX_PRIMARY_CHARS = 18000
MAX_SUPPLEMENTARY_CHARS = 1200
VIDEO_PLATFORMS = {"youtube", "youtube_shorts", "tiktok"}
TEXT_PLATFORMS = {"threads", "x", "twitter"}
INTERNAL_SOURCE_PLATFORMS = {"system_generated", "system_generated_owned"}
DEFAULT_MIN_INTERVAL_SECONDS = 13.0
DEFAULT_MAX_ATTEMPTS = 4
_GEMINI_RATE_LOCK = threading.Lock()
_LAST_GEMINI_REQUEST_AT = 0.0


class ReferenceRewriteError(RuntimeError):
    """Raised when a source cannot safely produce a grounded rewrite."""


def _clean(value: Any) -> str:
    return re.sub(r"\r\n?", "\n", str(value or "")).strip()


def _platform(source: dict[str, Any]) -> str:
    value = _clean(source.get("source_platform") or source.get("platform")).lower()
    if value:
        return value
    url = _clean(source.get("post_url") or source.get("source_url")).lower()
    if "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    if "tiktok.com" in url:
        return "tiktok"
    if "threads.net" in url:
        return "threads"
    if "x.com" in url or "twitter.com" in url:
        return "x"
    return "unknown"


def _first(source: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = _clean(source.get(key))
        if value:
            return value
    return ""


def reference_source_eligibility(source: dict[str, Any]) -> dict[str, Any]:
    """Reject internal/self-generated and known platform boilerplate before LLM use."""
    platform = _platform(source)
    source_account_id = _clean(source.get("source_account_id")).lower()
    post_text = _first(
        source,
        (
            "source_text",
            "text",
            "post_text",
            "original_post_text",
            "caption",
            "content",
            "投稿本文",
        ),
    )
    normalized = re.sub(r"\s+", " ", post_text).strip().lower()
    if platform in INTERNAL_SOURCE_PLATFORMS or source_account_id == "system_generated":
        return {"eligible": False, "reason": "internal_or_self_generated_source", "platform": platform}
    threads_markers = (
        "join threads to share ideas",
        "log in with your instagram",
    )
    if any(marker in normalized for marker in threads_markers):
        return {"eligible": False, "reason": "threads_login_boilerplate", "platform": platform}
    return {"eligible": True, "reason": "", "platform": platform}


def build_source_material(source: dict[str, Any]) -> str:
    """Build canonical semantic source material without inventing topic text."""
    eligibility = reference_source_eligibility(source)
    if not eligibility["eligible"]:
        raise ReferenceRewriteError(f"reference source is ineligible: {eligibility['reason']}")
    platform = str(eligibility["platform"])
    transcript = _first(
        source,
        (
            "transcript",
            "video_transcript",
            "audio_transcript",
            "transcript_text",
            "文字起こし",
            "動画文字起こし",
        ),
    )
    post_text = _first(
        source,
        (
            "source_text",
            "text",
            "post_text",
            "original_post_text",
            "caption",
            "content",
            "投稿本文",
        ),
    )
    title = _first(source, ("title", "動画タイトル"))
    visual_text = _first(source, ("ocr_text", "visual_text", "画面テキスト"))
    description = _first(source, ("description", "video_description", "概要欄"))

    if platform in VIDEO_PLATFORMS and not transcript:
        raise ReferenceRewriteError(
            f"{platform} reference requires transcript; metadata/caption alone is not enough"
        )
    if platform in TEXT_PLATFORMS and not post_text:
        raise ReferenceRewriteError(f"{platform} reference has no actual post text")
    if not transcript and not post_text:
        raise ReferenceRewriteError("reference has no usable source text or transcript")

    parts: list[tuple[str, str]] = []
    if title:
        parts.append(("title", title[:500]))
    if post_text:
        parts.append(("post_text_or_caption", post_text[:MAX_PRIMARY_CHARS]))
    if transcript:
        parts.append(("transcript", transcript[:MAX_PRIMARY_CHARS]))
    if visual_text:
        parts.append(("visual_text", visual_text[:3000]))
    # Description is deliberately supplementary: YouTube descriptions often
    # contain sponsors, links, and boilerplate unrelated to the video content.
    if description and description not in {post_text, transcript}:
        parts.append(("supplementary_description", description[:MAX_SUPPLEMENTARY_CHARS]))

    seen: set[str] = set()
    rendered: list[str] = []
    for label, value in parts:
        normalized = re.sub(r"\s+", " ", value).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        rendered.append(f"[{label}]\n{value}")
    material = "\n\n".join(rendered).strip()
    if not material:
        raise ReferenceRewriteError("reference source material is empty after normalization")
    return material


def _account_rules(account_id: str) -> str:
    if account_id == "night_scout":
        return (
            "読者はキャバクラ・夜職の女性。元ソースの中心テーマを変えず、夜職の読者に"
            "自然につながる場合だけ書き換える。1行目は具体的で強いフック。続けて空行を2つ。"
            "僕という一人称は自然な場合だけ使う。プロのスカウト目線だが押し売りしない。"
        )
    if account_id == "liver_manager":
        return (
            "読者はTikTok LIVEなどの配信者。元ソースの中心テーマを変えず、配信者の改善や判断に"
            "自然につながる場合だけ書き換える。実務的で簡潔なマネージャー目線にする。"
        )
    return "対象アカウントの読者に自然に合う文体へ変換する。"


def build_reference_rewrite_prompt(
    *,
    account_id: str,
    source_material: str,
    source_score: dict[str, Any] | None = None,
    target_platform: str = "threads",
    slot_theme: str = "reference_text",
) -> str:
    score = source_score or {}
    score_context = " / ".join(
        _clean(score.get(key))
        for key in ("category", "reusable_pattern", "reason")
        if _clean(score.get(key))
    )[:1000]
    return f"""あなたはSNS編集者です。以下のSOURCEを元に、{target_platform}向け投稿を1本だけ作成してください。

最重要ルール:
- SOURCEの中心テーマ・出来事・主張を意味上の境界にする。
- SOURCEと無関係な一般論、固定テンプレの話題、別テーマのノウハウへ置き換えない。
- SOURCEにない固有事実、数字、人物関係、実績を追加しない。
- 原文を長くコピーせず、意味と切り口を保ちながら十分に言い換える。
- 元投稿URL、アカウントID、参照元、スコア、生成工程など内部情報は本文に出さない。
- SOURCEを対象読者向けに自然に変換できない場合は、本文の代わりに __SKIP_SOURCE__ だけを返す。
- 80〜500文字程度。完成した投稿本文だけを返す。解説やJSONは不要。

アカウント方針:
{_account_rules(account_id)}

スロット: {slot_theme}
選定補助情報（SOURCEの意味より優先してはいけない）: {score_context or '(none)'}

SOURCE:
---
{source_material}
---
"""


def _api_key() -> str:
    key = _clean(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
    if not key:
        raise ReferenceRewriteError("GEMINI_API_KEY (or GOOGLE_API_KEY) is not configured")
    return key


def _env_float(name: str, default: float) -> float:
    try:
        return float(_clean(os.getenv(name)) or default)
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(_clean(os.getenv(name)) or default)
    except (TypeError, ValueError):
        return default


def _pace_gemini_request() -> None:
    global _LAST_GEMINI_REQUEST_AT
    minimum = max(0.0, _env_float("REFERENCE_GEMINI_MIN_INTERVAL_SECONDS", DEFAULT_MIN_INTERVAL_SECONDS))
    if minimum <= 0:
        return
    with _GEMINI_RATE_LOCK:
        now = time.monotonic()
        remaining = minimum - (now - _LAST_GEMINI_REQUEST_AT)
        if _LAST_GEMINI_REQUEST_AT > 0 and remaining > 0:
            time.sleep(remaining)
        _LAST_GEMINI_REQUEST_AT = time.monotonic()


def _retry_delay_seconds(response: requests.Response | None, attempt: int) -> float:
    if response is not None:
        retry_after = _clean(response.headers.get("Retry-After"))
        if retry_after:
            try:
                return min(max(float(retry_after), 0.0), 60.0)
            except ValueError:
                pass
        try:
            payload = response.json()
            details = (payload.get("error") or {}).get("details") or []
            for detail in details:
                value = _clean(detail.get("retryDelay")) if isinstance(detail, dict) else ""
                match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)s", value)
                if match:
                    return min(max(float(match.group(1)), 0.0), 60.0)
        except (ValueError, TypeError, AttributeError):
            pass
    return min(4.0 * (2 ** max(0, attempt - 1)), 45.0)


def _safe_gemini_error_detail(response: requests.Response) -> str:
    """Return bounded API diagnostics without logging request headers or secrets."""
    try:
        payload = response.json()
    except (ValueError, TypeError, AttributeError):
        return ""
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return ""
    status = _clean(error.get("status"))[:80]
    message = _clean(error.get("message"))[:260]
    # Defensive redaction even though Google error messages normally do not echo keys.
    message = re.sub(r"AIza[0-9A-Za-z_-]{20,}", "[REDACTED_API_KEY]", message)
    message = re.sub(r"(?i)(api[_ -]?key\s*[=:]\s*)[^\s,&]+", r"\1[REDACTED]", message)
    message = re.sub(r"(?i)([?&]key=)[^&\s]+", r"\1[REDACTED]", message)
    if status and message:
        return f"{status}: {message}"
    return status or message


def _call_gemini(
    prompt: str,
    *,
    model: str | None = None,
    temperature: float = 0.35,
    max_output_tokens: int = 2048,
    response_schema: dict[str, Any] | None = None,
) -> str:
    model_name = _clean(model or os.getenv("REFERENCE_GEMINI_MODEL") or DEFAULT_MODEL)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
    generation_config: dict[str, Any] = {
        "temperature": temperature,
        "maxOutputTokens": max_output_tokens,
    }
    if model_name.startswith("gemini-3"):
        thinking_level = _clean(os.getenv("REFERENCE_GEMINI_THINKING_LEVEL") or "low").lower()
        if thinking_level not in {"minimal", "low", "medium", "high"}:
            raise ReferenceRewriteError(
                "REFERENCE_GEMINI_THINKING_LEVEL must be minimal, low, medium, or high"
            )
        generation_config["thinkingConfig"] = {"thinkingLevel": thinking_level}
    if response_schema is not None:
        # The v1beta generateContent endpoint accepts the long-standing
        # responseMimeType + responseSchema pair broadly. Keep the semantic
        # judge structured/fail-closed without relying on a newer responseFormat
        # rollout that can return INVALID_ARGUMENT in some projects.
        generation_config["responseMimeType"] = "application/json"
        generation_config["responseSchema"] = response_schema
    max_attempts = max(1, min(_env_int("REFERENCE_GEMINI_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS), 6))
    last_status = 0
    for attempt in range(1, max_attempts + 1):
        _pace_gemini_request()
        response: requests.Response | None = None
        try:
            response = requests.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": _api_key(),
                },
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": generation_config,
                },
                timeout=60,
            )
        except requests.RequestException as exc:
            if attempt >= max_attempts:
                raise ReferenceRewriteError(f"Gemini request failed: {exc.__class__.__name__}") from exc
            time.sleep(_retry_delay_seconds(None, attempt))
            continue
        last_status = response.status_code
        if response.status_code in {429, 500, 502, 503, 504} and attempt < max_attempts:
            time.sleep(_retry_delay_seconds(response, attempt))
            continue
        if response.status_code >= 400:
            detail = _safe_gemini_error_detail(response)
            suffix = f" ({detail})" if detail else ""
            raise ReferenceRewriteError(
                f"Gemini API returned HTTP {response.status_code}{suffix}"
            )
        try:
            payload = response.json()
        except (ValueError, TypeError) as exc:
            raise ReferenceRewriteError("Gemini response could not be parsed") from exc
        if not isinstance(payload, dict):
            raise ReferenceRewriteError("Gemini response was not a JSON object")
        candidates = payload.get("candidates") or []
        if not isinstance(candidates, list) or not candidates:
            prompt_feedback = payload.get("promptFeedback") or {}
            block_reason = _clean(prompt_feedback.get("blockReason")) if isinstance(prompt_feedback, dict) else ""
            suffix = f" (promptBlockReason={block_reason})" if block_reason else ""
            raise ReferenceRewriteError(f"Gemini returned no candidates{suffix}")
        candidate = candidates[0] if isinstance(candidates[0], dict) else {}
        content = candidate.get("content") if isinstance(candidate, dict) else {}
        parts = content.get("parts") if isinstance(content, dict) else []
        if not isinstance(parts, list):
            parts = []
        visible_parts = []
        for part in parts:
            if not isinstance(part, dict) or part.get("thought") is True:
                continue
            value = _clean(part.get("text"))
            if value:
                visible_parts.append(value)
        result_text = "".join(visible_parts).strip()
        if not result_text:
            finish_reason = _clean(candidate.get("finishReason")) or "UNKNOWN"
            finish_message = _clean(candidate.get("finishMessage"))[:180]
            usage = payload.get("usageMetadata") or {}
            thoughts = usage.get("thoughtsTokenCount") if isinstance(usage, dict) else None
            output_tokens = usage.get("candidatesTokenCount") if isinstance(usage, dict) else None
            diagnostics = [f"finishReason={finish_reason}"]
            if isinstance(thoughts, int):
                diagnostics.append(f"thoughtsTokenCount={thoughts}")
            if isinstance(output_tokens, int):
                diagnostics.append(f"candidatesTokenCount={output_tokens}")
            if finish_message:
                diagnostics.append(f"finishMessage={finish_message}")
            raise ReferenceRewriteError(
                "Gemini returned no visible text (" + ", ".join(diagnostics) + ")"
            )
        return result_text
    raise ReferenceRewriteError(f"Gemini API returned HTTP {last_status or 'unknown'}")

def _parse_json_object(raw: str) -> dict[str, Any]:
    text = _clean(raw)
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ReferenceRewriteError("semantic fidelity response was not JSON")
    try:
        value = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ReferenceRewriteError("semantic fidelity JSON could not be parsed") from exc
    if not isinstance(value, dict):
        raise ReferenceRewriteError("semantic fidelity response must be an object")
    return value


def judge_semantic_fidelity(
    *,
    source_material: str,
    draft: str,
    model: str | None = None,
) -> dict[str, Any]:
    prompt = f"""SOURCEとDRAFTの意味整合性を厳格に判定してください。
判定基準:
1. DRAFTの中心テーマ・出来事・主張がSOURCEの合理的な言い換え/応用になっているか。
2. SOURCEと無関係な一般論や別テーマへ差し替わっていないか。
3. SOURCEにない具体的事実・数字・人物関係を追加していないか。
4. 原文を長くコピーしていないか。

JSONだけ返してください。形式:
{{"pass": true, "reason": "短い理由"}}

SOURCE:
---
{source_material}
---

DRAFT:
---
{draft}
---
"""
    response_schema = {
        "type": "object",
        "properties": {
            "pass": {"type": "boolean"},
            "reason": {"type": "string"},
        },
        "required": ["pass", "reason"],
    }
    raw = _call_gemini(
        prompt,
        model=model,
        temperature=0.0,
        max_output_tokens=1024,
        response_schema=response_schema,
    )
    result = _parse_json_object(raw)
    passed = result.get("pass") is True
    reason = _clean(result.get("reason"))[:300]
    return {"pass": passed, "reason": reason or ("semantic match" if passed else "semantic mismatch")}


def _post_design(text: str) -> dict[str, Any]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    hook = paragraphs[0] if paragraphs else text[:80]
    closing = paragraphs[-1] if len(paragraphs) > 1 else ""
    body = "\n\n".join(paragraphs[1:-1]) if len(paragraphs) > 2 else (paragraphs[1] if len(paragraphs) == 2 else "")
    return {
        "hook_text": hook,
        "body_text": body,
        "closing_text": closing,
        "cta_intent": "none",
        "key_claims": [],
    }


def rewrite_reference_post(
    *,
    account_id: str,
    source: dict[str, Any],
    source_score: dict[str, Any] | None = None,
    target_platform: str = "threads",
    slot_theme: str = "reference_text",
    model: str | None = None,
) -> dict[str, Any]:
    """Generate one source-faithful draft and fail closed on semantic mismatch."""
    source_material = build_source_material(source)
    prompt = build_reference_rewrite_prompt(
        account_id=account_id,
        source_material=source_material,
        source_score=source_score,
        target_platform=target_platform,
        slot_theme=slot_theme,
    )
    draft = _clean(_call_gemini(prompt, model=model, temperature=0.35, max_output_tokens=2048))
    if draft == "__SKIP_SOURCE__" or "__SKIP_SOURCE__" in draft:
        raise ReferenceRewriteError("source cannot be transformed without changing its central topic")
    if len(draft) < 40:
        raise ReferenceRewriteError("generated draft is too short")

    fidelity = judge_semantic_fidelity(source_material=source_material, draft=draft, model=model)
    if not fidelity["pass"]:
        raise ReferenceRewriteError(f"semantic fidelity blocked: {fidelity['reason']}")

    source_hash = hashlib.sha256(source_material.encode("utf-8")).hexdigest()
    structure_variant = int(source_hash[:2], 16) % 6
    model_name = _clean(model or os.getenv("REFERENCE_GEMINI_MODEL") or DEFAULT_MODEL)
    return {
        "public_post_text": draft,
        "source_text": source_material,
        "source_sha256": source_hash,
        "generation_model": model_name,
        "generation_strategy": "source_grounded_gemini_v1",
        "feature_schema_version": "source_grounded_v1",
        "generation_policy": {
            "policy": "source_grounded_gemini_v1",
            "semantic_fidelity_required": True,
            "unrelated_fallback_allowed": False,
        },
        "grounding_summary": {
            "generation_strategy": "source_grounded_gemini_v1",
            "structure_variant": structure_variant,
            "quality_topic": "",
            "semantic_fidelity": fidelity,
        },
        "post_design": _post_design(draft),
        "semantic_fidelity": fidelity,
    }
