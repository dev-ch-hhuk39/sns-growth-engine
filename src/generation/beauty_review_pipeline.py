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
        "スキンケアを増やしているのに肌が安定しない時は、"
        "足りないものより重ねすぎを見た方がいいかも。\n\n"
        "化粧水、美容液、クリームを一度に変えると、どれが合わないのか分からなくなるんだよね。"
        "私ならまず一つだけ残して、一週間の肌の変化を見る。無理に増やさなくて大丈夫。"
    ),
    "reference_text_generation": (
        "夕方にファンデが崩れると、コスメの持ちだけを疑いたくなるよね。\n\n"
        "でも、厚く塗るほど皮脂と混ざってヨレやすいこともある。"
        "まずはメイク前の保湿を薄くなじませて、ファンデを預けすぎないところから試してみて。"
        "アイテムを買い足す前に塗る量を見直すと、意外と変わるかも。"
    ),
    "pdca_text_generation": (
        "髪の手触りが変わらない時、ヘアケアを全部変える必要はないんだよね。\n\n"
        "トリートメントの種類より、洗った後に長く濡れたままにしていないかをまず確認してみて。"
        "毛先から水分をやさしく取って、根元から乾かす。このひとつを続けてから、次のアイテムを比べるので大丈夫。"
    ),
    "direct_reference_media": (
        "美容家電は機能が多いほどいい、とは限らないんだよね。\n\n"
        "大事なのは、自分のスキンケアのどこに入れるか。"
        "朝は時間がないのか、夜にじっくり使えるのかで、続く機種は変わる。"
        "私ならまず使う時間を決めて、その時間に無理なく続けられる一台を選ぶよ。"
    ),
    "approved_source_clip": (
        "サロンを選ぶ時は、仕上がりの写真だけで決めない方がいいかも。\n\n"
        "髪質や普段のメイク、朝にかけられる時間まで聞いてくれるかで、家で再現できるかが変わるんだよね。"
        "まずはカウンセリングで普段の手入れまで伝えてみて。"
        "その日だけじゃなく、次の日も自分で整えられる仕上がりが一番使いやすいよ。"
    ),
}


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
