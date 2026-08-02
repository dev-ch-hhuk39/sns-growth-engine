#!/usr/bin/env python3
"""Regression: real domain terms must enable deterministic clip captions."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

os.environ["GITHUB_MODELS_ENABLED"] = "false"

from acquisition.contracts import ProviderResult
from generation.source_grounded_caption import (
    DeterministicGroundedProvider,
    SourceGroundedCaptionService,
)
from run_media_production_pipeline import (
    _build_final_caption_bundle,
    _generate_final_media_caption,
)


class DisabledPrimaryProvider:
    provider_name = "disabled_primary_test"
    provider_version = "1"

    def generate(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> ProviderResult[dict[str, Any]]:
        return ProviderResult(
            self.provider_name,
            self.provider_version,
            "UNAVAILABLE",
            reason="external_model_disabled_for_test",
        )


def check(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise AssertionError(message)

    print(f"  PASS {message}")


def build_caption(
    *,
    account_id: str,
    clip_id: str,
    source_video_id: str,
    source_id: str,
    platform: str,
    source_url: str,
    title: str,
    description: str,
    transcript_excerpt: str,
) -> dict[str, Any]:
    clip = {
        "clip_candidate_id": clip_id,
        "source_video_id": source_video_id,
        "account_id": account_id,
        "clip_status": "MEDIA_READY",
        "rights_status": "approved_creator_clip",
        "permission_status": "approved",
        "transcript_grounded": "TRUE",
        "transcript_excerpt": transcript_excerpt,
        "start_seconds": "10",
        "end_seconds": "40",
    }

    source_video = {
        "source_video_id": source_video_id,
        "source_id": source_id,
        "account_id": account_id,
        "platform": platform,
        "canonical_video_url": source_url,
        "rights_status": "approved_creator_clip",
        "permission_status": "approved",
        "title": title,
        "description_preview": description,
    }

    media_asset = {
        "media_id": f"ma_{clip_id}",
        "video_clip_id": clip_id,
        "account_id": account_id,
        "upload_status": "UPLOADED",
        "storage_url": (
            "https://res.cloudinary.com/example/video/"
            f"upload/{clip_id}.mp4"
        ),
        "rights_status": "approved_creator_clip",
        "permission_status": "approved",
        "media_type": "video",
        "duration_seconds": "30",
        "aspect_ratio": "9:16",
    }

    bundle, excerpt, reasons = (
        _build_final_caption_bundle(
            clip=clip,
            source_video=source_video,
            account_id=account_id,
            media_asset=media_asset,
        )
    )

    check(
        bundle is not None,
        f"{account_id} caption bundle exists",
    )

    check(
        not reasons,
        f"{account_id} caption bundle has no blockers",
    )

    service = SourceGroundedCaptionService(
        generation_provider=DisabledPrimaryProvider(),
        fallback_provider=DeterministicGroundedProvider(),
        allow_deterministic_fallback=False,
        retry_primary_on_alignment_failure=False,
    )

    return _generate_final_media_caption(
        clip=clip,
        source_video=source_video,
        media_asset=media_asset,
        account_id=account_id,
        recent_posts=[],
        caption_service=service,
        max_attempts=1,
    )


def main() -> int:
    provider = DeterministicGroundedProvider()

    check(
        "風俗嬢"
        in provider.EVIDENCE_TERMS["night_scout"],
        "night_scout includes actual nightlife terms",
    )

    check(
        "ライバー"
        in provider.EVIDENCE_TERMS["liver_manager"],
        "liver_manager includes actual creator terms",
    )

    night_caption = build_caption(
        account_id="night_scout",
        clip_id="clip_test_night_domain_terms",
        source_video_id="sv_test_night_domain_terms",
        source_id="src_test_night_domain_terms",
        platform="youtube",
        source_url=(
            "https://www.youtube.com/watch?v=8Xmkojfw90Q"
        ),
        title=(
            "国内NO.1風俗嬢VSクイーン "
            "キャバ嬢転身を巡り大激論"
        ),
        description="風俗嬢からキャバ嬢への転身を考える対談",
        transcript_excerpt=(
            "風俗嬢からキャバ嬢へ移るなら、"
            "次の場所を探す前に、"
            "今いる場所を辞めたい理由や"
            "不満を整理する。"
            "今のままで変えられることと、"
            "移らないと変わらないことを分ける。"
            "新しい場所で増やしたいこと、"
            "減らしたいこと、避けたいことを"
            "それぞれ書き出す。"
            "移籍先は同じ悩みを繰り返さない"
            "選択肢かを比べて決める。"
        ),
    )

    check(
        night_caption.get("status") == "PASS",
        "night_scout deterministic caption passes",
    )

    check(
        bool(
            str(
                night_caption.get(
                    "public_post_text",
                    "",
                )
            ).strip()
        ),
        "night_scout public caption is non-empty",
    )

    check(
        night_caption.get("caption_provider")
        == "deterministic_grounded_fallback",
        "night_scout uses deterministic fallback",
    )

    parent_only_caption = build_caption(
        account_id="night_scout",
        clip_id="clip_test_parent_metadata_only",
        source_video_id="sv_test_parent_metadata_only",
        source_id="src_test_parent_metadata_only",
        platform="youtube",
        source_url=(
            "https://www.youtube.com/watch?v=8Xmkojfw90Q"
        ),
        title=(
            "国内NO.1風俗嬢VSクイーン "
            "キャバ嬢転身を巡り大激論"
        ),
        description=(
            "風俗嬢からキャバ嬢への転身を考える対談"
        ),
        transcript_excerpt=(
            "夏に向けたボディメイクについて"
            "話している。"
        ),
    )

    check(
        parent_only_caption.get("status")
        == "REVIEW_REQUIRED",
        (
            "parent title cannot enable an "
            "unrelated clip caption"
        ),
    )

    check(
        "account_relevant_source_evidence_missing"
        in parent_only_caption.get(
            "blocked_reasons",
            [],
        ),
        (
            "parent-only grounding failure "
            "is auditable"
        ),
    )

    liver_caption = build_caption(
        account_id="liver_manager",
        clip_id="clip_test_liver_domain_terms",
        source_video_id="sv_test_liver_domain_terms",
        source_id="src_test_liver_domain_terms",
        platform="tiktok",
        source_url=(
            "https://www.tiktok.com/"
            "@example/video/7657837310339222792"
        ),
        title=(
            "団結は1コインから生まれる "
            "#tiktoklive #ライバー"
        ),
        description=(
            "TikTok LIVEの団結枠とライバーの話"
        ),
        transcript_excerpt=(
            "配信では少額の投げ銭やギフトを"
            "お願いする前に、リスナーがまた"
            "参加したくなる関係を作る。"
            "コメントへ丁寧に反応し、"
            "常連だけで会話を固めず、"
            "初めて来た人も参加できる"
            "余白を残す。"
            "目標の理由と楽しめる企画を伝え、"
            "ギフトの有無に関係なく反応し、"
            "次回も話せる話題や約束を残す。"
        ),
    )

    check(
        liver_caption.get("status") == "PASS",
        "liver_manager deterministic caption passes",
    )

    check(
        bool(
            str(
                liver_caption.get(
                    "public_post_text",
                    "",
                )
            ).strip()
        ),
        "liver_manager public caption is non-empty",
    )

    check(
        liver_caption.get("caption_provider")
        == "deterministic_grounded_fallback",
        "liver_manager uses deterministic fallback",
    )

    check(
        float(
            liver_caption.get(
                "final_alignment_score",
                0,
            )
            or 0
        )
        >= 0.9,
        "liver_manager caption remains strongly grounded",
    )

    print(
        "PASS "
        "test_deterministic_caption_domain_terms.py"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
