#!/usr/bin/env python3
"""Account-specific normalization for scheduled media captions."""
from __future__ import annotations

import re
from typing import Any

NOISE_PATTERNS = (
    r"[\[【（(]\s*(?:音楽|拍手|笑い|BGM|music|applause)\s*[\]】）)]",
    r"(?:えー|えっと|あの|まあ|その)(?=[、,\s])",
)
ORGANIZATION_PATTERN = re.compile(
    r"[A-Za-z0-9ぁ-んァ-ヶ一-龥ー]{2,24}(?:グループ|株式会社|合同会社|事務所)"
)
QUOTE_PATTERN = re.compile(r"[「『\"“](.*?)[」』\"”]", re.DOTALL)


def _text(value: Any) -> str:
    return str(value or "").strip()


def clean_source_text(value: Any) -> str:
    text = _text(value)
    for pattern in NOISE_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    text = ORGANIZATION_PATTERN.sub("", text)
    text = re.sub(r"\b(?:僕たち|私たち|我々)\b", "", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip(" 　、,。\n")


def _claim_from_caption(text: str) -> str:
    quoted = [clean_source_text(item) for item in QUOTE_PATTERN.findall(text)]
    quoted = [item for item in quoted if len(item) >= 12]
    if quoted:
        claim = quoted[0]
    else:
        lines = [clean_source_text(item) for item in text.splitlines()]
        lines = [item for item in lines if len(item) >= 12]
        claim = max(lines, key=len, default="")
    claim = re.sub(r"^(?:この場面では|実際の言葉は|判断するときに確認したいのは)", "", claim)
    claim = re.sub(r"(?:と話されています|という話があります|という部分です)$", "", claim)
    return claim.strip(" 　、,。\"'」』")[:110]


def normalize_scheduled_caption(account_id: str, text: Any, *, media_origin: str = "") -> dict[str, Any]:
    source = clean_source_text(text)
    claim = _claim_from_caption(source)
    blockers: list[str] = []
    if not claim or len(claim) < 16:
        blockers.append("caption_claim_too_short_after_noise_removal")
    if re.search(r"[\[【（(](?:音楽|拍手|BGM)", source, flags=re.IGNORECASE):
        blockers.append("transcript_noise_remaining")
    if ORGANIZATION_PATTERN.search(source):
        blockers.append("unapproved_organization_name_remaining")

    if blockers:
        return {
            "status": "BLOCKED",
            "public_post_text": "",
            "blocked_reasons": blockers,
            "source_text": source,
        }

    if account_id == "night_scout":
        if media_origin == "direct_reference":
            hook = "キャバを始めたての子に伝えたい。"
            closing = "僕なら、数字だけで決めず、実際に続けられる店かまで確認して選ぶ。"
        else:
            hook = "現役キャバ嬢に伝えたい。"
            closing = "僕なら、この話をそのまま受け取らず、自分の店選びや働き方に置き換えて考える。"
        public_text = f"{hook}\n\n{claim}。\n\n{closing}"
    elif account_id == "liver_manager":
        if media_origin == "direct_reference":
            hook = "配信を伸ばしたいライバーに伝えたい。"
            closing = "次の配信では、ここから一つだけ行動に落として試してみてください。"
        else:
            hook = "ライバーの配信改善で大事なこと。"
            closing = "この場面を参考に、次の配信で変えることを一つだけ決めてみてください。"
        public_text = f"{hook}\n\n{claim}。\n\n{closing}"
    else:
        return {
            "status": "BLOCKED",
            "public_post_text": "",
            "blocked_reasons": ["unsupported_account"],
            "source_text": source,
        }

    return {
        "status": "PASS",
        "public_post_text": public_text,
        "blocked_reasons": [],
        "source_text": source,
        "claim": claim,
        "policy_version": "scheduled_caption_policy_v1",
    }
