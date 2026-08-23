"""Beauty-account compliance and review-lane policy.

The beauty account may generate review candidates, but never bypasses human
review. Medical topics are separated from ordinary beauty content and all
policy evidence is account scoped.
"""
from __future__ import annotations

import re
from typing import Any


MEDICAL_TERMS = (
    "美容医療",
    "クリニック",
    "施術",
    "注射",
    "ボトックス",
    "ヒアルロン酸",
    "レーザー治療",
    "医師",
    "副作用",
)

PROHIBITED_CLAIMS = (
    "絶対に治る",
    "100%効果あり",
    "100%安全",
    "必ず変わる",
    "効果を保証",
    "副作用なし",
    "病院いらず",
    "薬と同じ効果",
    "飲むだけで痩せる",
    "キューティクルが閉じ",
    "効果が半減",
    "効果も半減",
    "効果的になるはず",
    "きっともっと綺麗",
    "きっと",
    "変わるはず",
    "感じるはず",
    "全然変わる",
    "格段に良くなる",
    "たった数分で",
    "たった数分でも",
    "仕上がりが変わる",
    "肌が疲れてるサイン",
    "効果を感じにくい",
    "全然違う",
    "良さを引き出し",
    "良さを引き出す",
    "逆効果",
    "肌が敏感",
    "肌がデリケート",
    "刺激になる",
    "肌を休ませ",
    "負担になっちゃう",
)

SALES_OR_PRESSURE_TERMS = (
    "LINEで相談",
    "DMして",
    "今すぐ購入",
    "お申し込み",
    "限定価格",
)

FABRICATED_EXPERIENCE_TERMS = (
    "私も前は",
    "私も昔",
    "私もそうだった",
    "私もつい",
)

FABRICATED_EXPERIENCE_PATTERNS = (
    r"私[、は].{0,80}ようにして(?:る|いる)",
    r"私[、は].{0,80}(?:愛用|使い続け|通って)",
)

UNVERIFIED_USAGE_TERMS = (
    "シートマスクの上から",
    "化粧水をつけるついでに",
    "たっぷり塗",
    "数分待",
    "数分長く",
)

ALLOWED_CTA_MARKERS = {
    "save": ("保存", "見返"),
    "like": ("いいね",),
    "follow": ("フォロー",),
}

BEAUTY_EMOJIS = ("🥺", "✨", "🤍", "🫶🏻", "😭", "💭")


def beauty_cta_allowed_for_sequence(sequence_number: int) -> bool:
    """Allow one light CTA on roughly ten percent of generated candidates."""
    return sequence_number > 0 and sequence_number % 10 == 0


def beauty_compliance_validation(text: str) -> dict[str, Any]:
    """Return beauty-specific compliance evidence without publishing anything."""
    value = str(text or "").strip()
    medical_hits = [term for term in MEDICAL_TERMS if term in value]
    prohibited_hits = [term for term in PROHIBITED_CLAIMS if term in value]
    pressure_hits = [term for term in SALES_OR_PRESSURE_TERMS if term in value]
    fabricated_hits = [term for term in FABRICATED_EXPERIENCE_TERMS if term in value]
    fabricated_hits.extend(
        match.group(0)
        for pattern in FABRICATED_EXPERIENCE_PATTERNS
        for match in re.finditer(pattern, value)
    )
    unverified_usage_hits = [term for term in UNVERIFIED_USAGE_TERMS if term in value]
    cta_hits = {
        cta_type: [term for term in markers if term in value]
        for cta_type, markers in ALLOWED_CTA_MARKERS.items()
    }
    cta_types = [cta_type for cta_type, hits in cta_hits.items() if hits]

    blocked_reasons: list[str] = []
    if prohibited_hits:
        blocked_reasons.append("beauty_prohibited_effect_or_medical_claim")
    if pressure_hits:
        blocked_reasons.append("beauty_sales_or_pressure_cta")
    if len(cta_types) > 1:
        blocked_reasons.append("beauty_multiple_cta_types")
    exclamation_count = value.count("!") + value.count("！")
    emoji_count = sum(value.count(emoji) for emoji in BEAUTY_EMOJIS)
    if exclamation_count > 1 or (exclamation_count and emoji_count):
        blocked_reasons.append("beauty_exclamatory_ad_tone")
    if "ねぇ、みんな" in value or "ねぇ、みんな" in value:
        blocked_reasons.append("beauty_overfamiliar_opening")
    if fabricated_hits:
        blocked_reasons.append("beauty_fabricated_personal_experience")
    if unverified_usage_hits:
        blocked_reasons.append("beauty_unverified_product_usage")

    requires_medical_review = bool(medical_hits)
    status = "BLOCKED" if blocked_reasons else (
        "REVIEW_REQUIRED" if requires_medical_review else "PASS"
    )
    return {
        "status": status,
        "account_id": "beauty_account",
        "review_lane": "BEAUTY_MEDICAL" if requires_medical_review else "BEAUTY_STANDARD",
        "requires_human_review": True,
        "medical_review_required": requires_medical_review,
        "medical_term_hits": medical_hits,
        "prohibited_claim_hits": prohibited_hits,
        "sales_or_pressure_hits": pressure_hits,
        "fabricated_experience_hits": fabricated_hits,
        "unverified_usage_hits": unverified_usage_hits,
        "cta_types": cta_types,
        "cta_type_count": len(cta_types),
        "emoji_count": emoji_count,
        "exclamation_count": exclamation_count,
        "blocked_reasons": blocked_reasons,
        "auto_ready_allowed": False,
    }
