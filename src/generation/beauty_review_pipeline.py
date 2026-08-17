"""Prepare beauty-account candidates for human review across five routes."""
from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from public_post_quality import final_public_post_validator  # noqa: E402
from accounts.beauty_policy import (  # noqa: E402
    beauty_compliance_validation,
    beauty_cta_allowed_for_sequence,
)

PIPELINE_CONFIG = ROOT / "config/beauty_account_pipeline.json"

ROUTES = (
    "new_text_generation",
    "reference_text_generation",
    "pdca_text_generation",
    "direct_reference_media",
    "approved_source_clip",
)

DEFAULT_ROUTE_TEXTS = {
    "new_text_generation": (
        "スキンケアを増やしたのに肌が安定しない時って\n"
        "ほんとに何を変えればいいか迷うんだよね🥺\n\n"
        "個人的には、足すより一つだけ残すのが結構大事\n"
        "一度に変えると、どれが合わないか分かりにくい気がする💭\n\n"
        "使い始めた日をメモして\n"
        "その他はいつも通りで試してみてほしい🤍"
    ),
    "reference_text_generation": (
        "夕方にファンデが崩れると\nコスメの持ちだけを疑いたくなるんだけど💭\n\n"
        "個人的には、まず塗る量を見るのが結構大事\n"
        "厚く重ねるほど、頜や小鼻はヨレやすい気がする🥺\n\n"
        "アイテムを買い足す前に\n明日は使う量だけ変えてみてほしい✨"
    ),
    "pdca_text_generation": (
        "ヘアケアを変えても髪の手触りが同じだと\nほんとに次は何を買うか迷うよね🥺\n\n"
        "個人的には、商品より乾かす順番を先に見る\n"
        "毛先の水分をやさしく取って根元から乾かすの、これ結構大事💭\n\n"
        "今のアイテムはそのままで\n一週間だけ順番を比べてみてほしい✨"
    ),
    "direct_reference_media": (
        "美容家電って機能が多いほど良さそうに見えるんだけど\n個人的には、使う時間を先に決めるのが結構大事🥺\n\n"
        "朝のメイク前か、夜のスキンケア後か\n"
        "毎日の流れに入らないと、ほんとに出番が減りがち💭\n\n"
        "所要時間と使えるタイミングを見て\n無理なく続けられそうか比べてみてほしい🤍"
    ),
    "approved_source_clip": (
        "サロンの仕上がり写真って素敵だけど\n"
        "次の日も自分で髪を整えられるかまでは、意外と分からないんだよね💭\n\n"
        "個人的には、普段の手入れや苦手なセットを聞いてくれるかが結構大事\n"
        "家でのやり方まで分かると、ほんとに安心する🤍\n\n"
        "予約前に、普段のケアも相談できるか見てみてほしい✨"
    ),
}


def select_beauty_route(sequence_number: int, *, config: dict[str, Any] | None = None) -> str:
    """Select one of all five production routes from the canonical weighted mix."""
    pipeline = config or load_pipeline_config()
    weighted = pipeline["generation_routes"]
    if set(weighted) != set(ROUTES):
        raise ValueError("beauty_generation_routes_incomplete")
    total = sum(int(weighted[route]["weight"]) for route in ROUTES)
    if total != 100:
        raise ValueError("beauty_generation_route_weights_must_sum_to_100")
    from generation.content_mix_planner import plan_operational_threads_routes

    canonical_mix = {
        "operational_threads_slot_mix": {
            "beauty_account": {route: int(weighted[route]["weight"]) for route in ROUTES}
        }
    }
    plan = plan_operational_threads_routes("beauty_account", 100, config=canonical_mix)
    return plan[(max(1, int(sequence_number)) - 1) % len(plan)]


def load_pipeline_config() -> dict[str, Any]:
    return json.loads(PIPELINE_CONFIG.read_text(encoding="utf-8"))


def _candidate_id(route: str) -> str:
    return f"beauty_review_{route}_{uuid.uuid4().hex[:10]}"


def build_beauty_review_candidate(
    route: str,
    *,
    public_post_text: str | None = None,
    sequence_number: int = 1,
    source_ids: list[str] | None = None,
    media_permission_approved: bool = False,
) -> dict[str, Any]:
    if route not in ROUTES:
        raise ValueError(f"unsupported_beauty_route:{route}")

    text = str(public_post_text or DEFAULT_ROUTE_TEXTS[route]).strip()
    cta_applied = beauty_cta_allowed_for_sequence(sequence_number)
    if cta_applied and not any(marker in text for marker in ("保存", "いいね", "フォロー")):
        text = f"{text}\n\nあとで見返せるように、保存しておくと便利だよ。"

    compliance = beauty_compliance_validation(text)
    validator = final_public_post_validator(text, "beauty_account")
    media_route = route in {"direct_reference_media", "approved_source_clip"}
    media_gate = "PASS" if media_permission_approved else (
        "AWAITING_APPROVED_MEDIA" if media_route else "NOT_REQUIRED"
    )
    return {
        "candidate_id": _candidate_id(route),
        "account_id": "beauty_account",
        "platform": "threads",
        "generation_route": route,
        "status": "WAITING_REVIEW",
        "public_post_text": text,
        "source_ids": list(source_ids or []),
        "style_profile_version": "chadult_beauty_voice_v1",
        "pdca_account_scope": "beauty_account" if route == "pdca_text_generation" else "",
        "cross_account_learning": False,
        "pdca_public_metrics_allowed": False,
        "cta_applied": cta_applied,
        "beauty_compliance": compliance,
        "public_post_validator": validator,
        "review_lane": compliance["review_lane"],
        "media_permission_gate": media_gate,
        "auto_ready_allowed": False,
        "publisher_eligible": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

def build_beauty_review_batch(
    *,
    sequence_start: int = 1,
    text_overrides: dict[str, str] | None = None,
    source_ids: list[str] | None = None,
) -> dict[str, Any]:
    candidates = [
        build_beauty_review_candidate(
            route,
            public_post_text=(text_overrides or {}).get(route),
            sequence_number=sequence_start + index,
            source_ids=source_ids,
        )
        for index, route in enumerate(ROUTES)
    ]
    return {
        "account_id": "beauty_account",
        "status": "WAITING_REVIEW",
        "candidate_count": len(candidates),
        "generation_routes": list(ROUTES),
        "all_public_validators_pass": all(
            row["public_post_validator"]["status"] == "PASS" for row in candidates
        ),
        "all_candidates_waiting_review": all(
            row["status"] == "WAITING_REVIEW" for row in candidates
        ),
        "candidates": candidates,
        "safety": {
            "real_post": False,
            "auto_ready": False,
            "scheduled_publish": False,
            "cross_account_pdca": False,
        },
    }
