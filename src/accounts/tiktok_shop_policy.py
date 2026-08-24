"""TikTok Shop evidence, review, CTA, and customer-language contracts."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "config/tiktok_shop_policy.json"
OFFICIAL_CLASSES = {"official_fact", "official_case_study"}
MARKET_CLASSES = {"market_observation", "market_estimate"}
ALLOWED_EVIDENCE_CLASSES = OFFICIAL_CLASSES | MARKET_CLASSES | {
    "operator_case_study", "observed_creator_content", "observed_seller_content",
    "internal_experiment", "global_hypothesis",
}


@lru_cache(maxsize=1)
def load_policy() -> dict[str, Any]:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def validate_evidence(record: Mapping[str, Any]) -> dict[str, Any]:
    evidence_class = str(record.get("evidence_class") or record.get("source_type") or "").strip()
    reasons: list[str] = []
    if evidence_class not in ALLOWED_EVIDENCE_CLASSES:
        reasons.append("evidence_class_invalid")
    for field in ("source_url", "source_publisher", "source_date", "verified_at"):
        if not str(record.get(field) or "").strip():
            reasons.append(f"{field}_missing")
    official = str(record.get("official_status") or "").lower() == "official"
    if evidence_class in MARKET_CLASSES and official:
        reasons.append("market_estimate_misrepresented_as_official")
    if evidence_class in OFFICIAL_CLASSES and not official:
        reasons.append("official_source_not_verified")
    if str(record.get("freshness_status") or "").upper() in {"STALE", "UNKNOWN"}:
        reasons.append("time_sensitive_fact_requires_review")
    return {"status": "PASS" if not reasons else "BLOCKED", "blocked_reasons": reasons}


def requires_human_review(candidate: Mapping[str, Any], *, published_count: int) -> tuple[bool, list[str]]:
    policy = load_policy()
    reasons: list[str] = []
    if published_count < 20:
        reasons.append("FIRST_20_POSTS_REQUIRE_HUMAN_REVIEW")
    route = str(candidate.get("generation_mode") or candidate.get("content_type") or "").lower()
    topic = str(candidate.get("topic_category") or candidate.get("primary_topic") or "").lower()
    permanent = {str(value).lower() for value in policy["permanent_human_review_topics"]}
    if any(value in route or value in topic for value in permanent):
        reasons.append("PERMANENT_REVIEW_CATEGORY")
    return bool(reasons), reasons


def cta_phase(*, beginner_posts: int, creator_posts: int, repeated_pain_count: int) -> int:
    phase2 = load_policy()["cta_phases"]["2"]
    if (
        beginner_posts >= int(phase2["minimum_beginner_posts"])
        and creator_posts >= int(phase2["minimum_creator_posts"])
        and repeated_pain_count >= int(phase2["minimum_repeated_pain_count"])
    ):
        return 2
    return 1


def account_customer_language(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for row in rows:
        account_id = str(row.get("account_id") or "").strip()
        if not account_id:
            raise ValueError("account_namespace_missing")
        if account_id == "tiktok_shop":
            selected.append(dict(row))
    return selected


def new_customer_language_record(**values: Any) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    row = {**values, "account_id": "tiktok_shop", "created_at": now, "updated_at": now}
    if not str(row.get("raw_customer_language") or "").strip():
        raise ValueError("raw_customer_language_missing")
    return row
