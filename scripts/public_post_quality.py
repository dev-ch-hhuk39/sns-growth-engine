#!/usr/bin/env python3
"""Public post generation and final validation gates.

Only ``public_post_text`` may ever be handed to a publisher. Internal
analysis, reference metadata, and scoring notes must stay out of public text.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RULES_FILE = ROOT / "config/post_generation_rules.json"

INTERNAL_LEAK_TERMS = [
    "今回の切り口",
    "threads /",
    "night_work_scout",
    "night_scout",
    "liver_manager",
    "target_account_id",
    "source",
    "reference",
    "参照元",
    "source_url",
    "source_id",
    "queue_id",
    "result_id",
    "category",
    "usage_scope",
    "trend_signal",
    "clip_candidate",
    "投稿案",
    "生成",
    "分解して使う",
    "そのまま真似るのではなく",
    "構成・フック",
    "投稿アイデア",
    "LINE/DMへの導線は最後",
    "導線は最後",
    "AI",
    "内部",
    "metadata",
    "transcript",
    "youtube_video_id_missing",
    "PLAN_ONLY",
    "AUTO_READY",
    "WAITING_REVIEW",
    "dry-run",
    "apply",
    "score",
    "safety_score",
    "risk_score",
]

SOURCE_METADATA_PATTERNS = [
    r"\bthreads\s*/",
    r"\bx\.com/",
    r"\byoutube\.com/",
    r"\btiktok\.com/",
    r"\bhttps?://",
    r"\bsource[_-]?\w*",
    r"\bqueue[_-]?\w*",
    r"\bresult[_-]?\w*",
]

AGGRESSIVE_OR_RISKY_TERMS = [
    "絶対稼げる",
    "必ず稼げる",
    "100%稼げる",
    "確実に稼げる",
    "誰でも月収",
    "楽して稼げる",
    "保証します",
    "今すぐ応募",
    "即日で稼げる",
    "ノーリスク",
]

ACCOUNT_TERMS = {
    "night_scout": ("夜職", "キャバ", "店", "働く", "時給", "ノルマ", "担当", "相談", "出勤", "移籍"),
    "liver_manager": ("配信", "ライバー", "TikTok LIVE", "LIVE", "リスナー", "初見", "コメント", "事務所", "ギフト"),
}


def load_post_generation_rules(path: Path = RULES_FILE) -> dict[str, Any]:
    if not path.exists():
        return {"quality_thresholds": {}, "accounts": {}, "account_rotation": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def extract_public_post_text(value: Any) -> str:
    """Return public text only, even when passed structured generation output."""
    if isinstance(value, dict):
        return str(value.get("public_post_text", "")).strip()
    raw = str(value or "").strip()
    if raw.startswith("{") and "public_post_text" in raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return str(parsed.get("public_post_text", "")).strip()
        except json.JSONDecodeError:
            return ""
    return raw


def build_generation_output(
    *,
    internal_analysis: str,
    public_post_text: str,
    safety_notes: str = "",
    blocked_reasons: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "internal_analysis": internal_analysis,
        "public_post_text": public_post_text,
        "safety_notes": safety_notes,
        "blocked_reasons": list(blocked_reasons or []),
    }


def _contains_terms(text: str, terms: list[str]) -> list[str]:
    low = text.lower()
    return [term for term in terms if term and term.lower() in low]


def _risk_score(text: str) -> int:
    score = 0
    if _contains_terms(text, AGGRESSIVE_OR_RISKY_TERMS):
        score += 30
    if any(k in text for k in ("絶対", "必ず", "保証", "誰でも", "簡単に稼げる")):
        score += 15
    if any(k in text for k in ("晒す", "叩く", "詐欺", "未成年", "薬")):
        score += 30
    return min(100, score)


def _cta_pressure_score(text: str) -> int:
    score = 0
    if any(k in text for k in ("今すぐ", "絶対", "必ず", "急いで", "限定")):
        score += 25
    if text.count("DM") + text.count("LINE") >= 2:
        score += 20
    if any(k in text for k in ("応募", "登録", "申し込み")):
        score += 15
    return min(100, score)


def _naturalness_score(text: str) -> int:
    if not text.strip():
        return 0
    score = 86
    if "。" not in text:
        score -= 15
    if len(text) < 80 or len(text) > 520:
        score -= 18
    if len(text.splitlines()) > 16:
        score -= 10
    if re.search(r"[A-Za-z_]{12,}", text):
        score -= 25
    if _contains_terms(text, INTERNAL_LEAK_TERMS):
        score -= 50
    return max(0, min(100, score))


def _reader_value_score(text: str, account_id: str) -> int:
    value_terms = ("理由", "大事", "まず", "見る", "整理", "変わる", "選ぶ", "続かない", "入りやすい", "具体")
    score = 72 + min(18, sum(1 for term in value_terms if term in text) * 4)
    if len(text) < 80:
        score -= 20
    if account_id == "night_scout" and any(k in text for k in ("店", "時給", "ノルマ", "担当", "出勤", "相談")):
        score += 8
    if account_id == "liver_manager" and any(k in text for k in ("初見", "コメント", "配信", "リスナー", "空気")):
        score += 8
    return max(0, min(100, score))


def _account_fit_score(text: str, account_id: str) -> int:
    terms = ACCOUNT_TERMS.get(account_id, ())
    hits = sum(1 for term in terms if term in text)
    score = 68 + min(24, hits * 6)
    if account_id == "beauty_account":
        score = 0
    return max(0, min(100, score))


def final_public_post_validator(text: Any, account_id: str = "") -> dict[str, Any]:
    public_text = extract_public_post_text(text)
    reasons: list[str] = []
    internal_hits = _contains_terms(public_text, INTERNAL_LEAK_TERMS)
    metadata_hits = [p for p in SOURCE_METADATA_PATTERNS if re.search(p, public_text, re.IGNORECASE)]
    hashtag_count = len(re.findall(r"(?:^|\s)#\S+", public_text))
    risk = _risk_score(public_text)
    cta = _cta_pressure_score(public_text)
    natural = _naturalness_score(public_text)
    reader = _reader_value_score(public_text, account_id)
    fit = _account_fit_score(public_text, account_id)
    quality = min(100, int((natural + reader + fit + max(0, 100 - cta) + max(0, 100 - risk)) / 5))

    if internal_hits:
        reasons.append("internal_terms")
    if metadata_hits:
        reasons.append("source_metadata_or_url")
    if "これは投稿案" in public_text or "投稿案です" in public_text:
        reasons.append("draft_label")
    if hashtag_count > 4:
        reasons.append("too_many_hashtags")
    if risk > 10:
        reasons.append("risk_score_above_max")
    if cta > 30:
        reasons.append("cta_pressure_above_max")
    if len(public_text) < 80:
        reasons.append("too_short")
    if len(public_text) > 520:
        reasons.append("too_long")
    if natural < 80:
        reasons.append("naturalness_below_threshold")
    if reader < 80:
        reasons.append("reader_value_below_threshold")
    if fit < 80:
        reasons.append("account_fit_below_threshold")
    if quality < 85:
        reasons.append("quality_below_threshold")

    return {
        "status": "PASS" if not reasons else "BLOCKED",
        "blocked_reasons": sorted(set(reasons)),
        "public_post_text": public_text,
        "text_length": len(public_text),
        "internal_leak_check": {
            "status": "PASS" if not internal_hits else "BLOCKED",
            "hits": internal_hits,
            "internal_leak_score": len(internal_hits),
        },
        "source_metadata_check": {
            "status": "PASS" if not metadata_hits else "BLOCKED",
            "hits": metadata_hits,
        },
        "account_fit_check": {
            "status": "PASS" if fit >= 80 else "BLOCKED",
            "account_fit_score": fit,
        },
        "public_post_quality_score": quality,
        "reader_value_score": reader,
        "naturalness_score": natural,
        "account_fit_score": fit,
        "cta_pressure_score": cta,
        "risk_score": risk,
        "similarity_to_source": 0.0,
    }


def generate_reader_facing_post(account_id: str, index: int = 1) -> dict[str, Any]:
    """Deterministic account-specific public text for autonomous text-only posts."""
    if account_id == "liver_manager":
        variants = [
            (
                "配信で伸びない人ほど、最初から面白いことを言おうとしすぎる。\n\n"
                "でも初心者の配信で大事なのは、面白さより入りやすさ。\n\n"
                "入った瞬間に何を話していいかわからない。\n"
                "コメントしても拾われるかわからない。\n"
                "常連だけで盛り上がっていて入りづらい。\n\n"
                "この状態だと、初見はすぐ抜ける。\n\n"
                "まずは、来てくれてありがとう、今この話をしてるよ、気軽にコメントしてねを自然に言えること。\n\n"
                "配信は才能より、入りやすい空気を作れるかが大きい。"
            ),
            (
                "ライバーを始めたいのに動けない人は、配信内容より先に不安を整理した方がいい。\n\n"
                "何を話すか。\n"
                "誰も来なかったらどうするか。\n"
                "コメントが止まったらどうするか。\n"
                "生活リズムに無理がないか。\n\n"
                "ここが曖昧なまま始めると、数回でしんどくなる。\n\n"
                "最初から完璧に話す必要はない。\n"
                "続けられる時間と、初見が入りやすい一言を決めるだけでもかなり変わる。"
            ),
        ]
        text = variants[(index - 1) % len(variants)]
    else:
        variants = [
            (
                "夜職で店を選ぶ時、時給だけで決める子はけっこう危ない。\n\n"
                "時給が高くても、客層が合わない。\n"
                "ノルマがきつい。\n"
                "出勤ペースが合わない。\n"
                "担当に相談しづらい。\n"
                "雰囲気が自分に合わない。\n\n"
                "このどれかがズレると、結局続かない。\n\n"
                "大事なのは、条件が良い店じゃなくて、自分が続けられる店を選ぶこと。\n\n"
                "迷っているなら、入る前に一回整理した方がいい。"
            ),
            (
                "夜職を始める前に見てほしいのは、時給よりも続けられる条件。\n\n"
                "家から遠すぎないか。\n"
                "出勤ペースに無理がないか。\n"
                "客層が自分に合いそうか。\n"
                "困った時に担当へ相談できるか。\n\n"
                "ここを見ないまま入ると、条件は良いのにしんどい店になることがある。\n\n"
                "焦って決めるより、先に自分が無理なく働ける形を整理した方がいい。"
            ),
        ]
        text = variants[(index - 1) % len(variants)]
    return build_generation_output(
        internal_analysis=f"account={account_id}; deterministic reader-facing template; index={index}",
        public_post_text=text,
        safety_notes="Public text only. Internal analysis must not be posted.",
        blocked_reasons=[],
    )


def last_posted_account(posted_rows: list[dict[str, Any]], rotation_accounts: list[str]) -> str:
    latest: tuple[datetime, str] | None = None
    allowed = set(rotation_accounts)
    for row in posted_rows:
        account_id = str(row.get("account_id", ""))
        if account_id not in allowed:
            continue
        if str(row.get("platform", "")).lower() not in {"", "threads"}:
            continue
        if str(row.get("status", "")).upper() not in {"POSTED", "RECOVERED", ""}:
            continue
        raw = str(row.get("posted_at") or row.get("created_at") or row.get("collected_at") or "")
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            dt = datetime.min.replace(tzinfo=timezone.utc)
        if latest is None or dt > latest[0]:
            latest = (dt, account_id)
    return latest[1] if latest else ""


def account_rotation_order(
    accounts: list[str],
    config: dict[str, Any],
    posted_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    rotation = config.get("account_rotation_strategy", {})
    enabled = bool(rotation.get("account_rotation_enabled", False))
    rotation_accounts = [a for a in rotation.get("rotation_accounts", accounts) if a in accounts]
    if not enabled or not rotation_accounts:
        return {"enabled": False, "ordered_accounts": accounts, "selected_account": accounts[0] if accounts else "", "skipped_accounts": []}
    last = last_posted_account(posted_rows or [], rotation_accounts)
    if not last:
        last = str(rotation.get("last_posted_account_hint_for_dry_run", ""))
    if last in rotation_accounts and len(rotation_accounts) > 1:
        preferred = [a for a in rotation_accounts if a != last] + [last]
    else:
        preferred = rotation_accounts
    rest = [a for a in accounts if a not in preferred]
    ordered = preferred + rest
    return {
        "enabled": True,
        "strategy": rotation.get("rotation_strategy", "alternate_by_last_posted_account"),
        "last_posted_account": last,
        "ordered_accounts": ordered,
        "selected_account": ordered[0] if ordered else "",
        "skipped_accounts": [{"account_id": a, "reason": "account_rotation_not_first"} for a in ordered[1:]],
        "fallback_to_available_account": bool(rotation.get("fallback_to_available_account", True)),
    }


def public_preview(text: str, limit: int = 260) -> str:
    text = extract_public_post_text(text).strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "..."
