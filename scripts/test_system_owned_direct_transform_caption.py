#!/usr/bin/env python3
from __future__ import annotations

# ruff: noqa: E402 - standalone regression configures repository import paths.

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

from build_media_activation_review_evidence import (
    EvidenceDraft,
    _runtime_direct_caption_builder,
    build_direct_draft,
    finalize_draft,
)
from direct_caption_policy import direct_caption_mode, queue_caption_mode
from generation.source_copyedit import validate_source_preserving_public_post
from generation_quality_gates import (
    evaluate_generation_quality,
    topic_coherence_validator,
)
from media_post_validator import validate_media_post
from prepare_media_activation_candidates import candidate_blockers
from process_threads_queue import build_media_validation_plan
from public_post_quality import final_public_post_validator

os.environ["GITHUB_MODELS_ENABLED"] = "false"

source_text = (
    "キャバで働く時、時給やノルマだけで店を決めると、"
    "客層が合わず、担当にも相談しづらく、出勤の負担が"
    "強くなることがある。自分に合う店かを見て働く方がいい。"
)
ocr_text = (
    "キャバで働く時、合わない店を選ぶと自分の努力だけでは"
    "どうにもならないことがある。客層が合わない。"
    "担当に相談しづらい。出勤の圧が強い。"
)
sibling_text = (
    "夜職で担当や相談できる環境を選ぶとき、実際の話を"
    "判断材料として整理しておきたい。\n\n"
    "担当へ相談できる環境か確認して考える材料にしてください。"
)

post = {
    "source_post_id": "sp_system_owned_direct_transform",
    "source_id": "system_owned_night_scout_direct_transform",
    "target_account_id": "night_scout",
    "platform": "threads",
    "profile_url": "https://example.invalid/system-owned",
    "canonical_post_url": "https://example.invalid/system-owned/direct",
    "external_post_id": "system-owned-direct",
    "original_post_text": source_text,
    "published_at": "2026-07-29T04:10:10+00:00",
    "detail_status": "COMPLETE",
    "collection_backend": "system_owned",
    "content_hash": "1234567890abcdef",
}
media = {
    "source_post_media_id": "spm_system_owned_direct_transform_0",
    "source_post_id": post["source_post_id"],
    "media_index": "0",
    "media_asset_id": "ma_system_owned_direct_transform_0",
    "media_type": "image",
    "canonical_post_url": post["canonical_post_url"],
    "original_media_url": "https://media.example.invalid/original.png",
    "storage_url": "https://media.example.invalid/direct.png",
    "cloudinary_status": "UPLOADED",
    "media_understanding": {
        "status": "PASS",
        "ocr_text": ocr_text,
    },
}
source = {
    "source_id": post["source_id"],
    "source_type": "system_owned",
}
permission = {
    "permission_id": "perm_system_owned_direct_transform",
    "source_id": post["source_id"],
    "account_id": "night_scout",
    "rights_status": "approved_creator_clip",
    "permission_status": "approved",
    "evidence_reference": "user-explicit-test",
    "allow_download": "TRUE",
    "allow_cloudinary_storage": "TRUE",
    "allow_original_repost": "TRUE",
    "allow_new_caption": "TRUE",
}

external_mode = direct_caption_mode(
    post={**post, "source_id": "src_external_creator"},
    source={"source_id": "src_external_creator"},
    permission={**permission, "source_id": "src_external_creator"},
)
owned_mode = direct_caption_mode(
    post=post,
    source=source,
    permission=permission,
)
registered_mode = direct_caption_mode(
    post={**post, "source_id": "src_registered_creator"},
    source={
        "source_id": "src_registered_creator",
        "registered_owner_scope_id": "owner-scope-1",
        "permission_status": "approved",
        "provenance_required": True,
        "original_author_match_required": True,
        "allow_new_caption": True,
    },
    permission={},
)
registered_without_provenance_mode = direct_caption_mode(
    post={**post, "source_id": "src_registered_incomplete"},
    source={
        "source_id": "src_registered_incomplete",
        "registered_owner_scope_id": "owner-scope-1",
        "permission_status": "approved",
        "allow_new_caption": True,
    },
    permission={},
)

captured_plan: dict[str, object] = {}


def media_validator(plan: dict[str, object]) -> dict[str, object]:
    captured_plan.update(plan)
    return validate_media_post(plan)


builder = _runtime_direct_caption_builder()
draft = build_direct_draft(
    account_id="night_scout",
    selection=(post, media, source),
    permission=permission,
    recent_posts=[sibling_text],
    caption_builder=builder,
    public_validator=validate_source_preserving_public_post,
    transform_public_validator=final_public_post_validator,
    media_validator=media_validator,
)
sibling = EvidenceDraft(
    account_id="night_scout",
    route="approved_source_clip",
    source={},
    public_post_text=sibling_text,
    caption={},
    public_validation={},
    media_validation={},
    media_evidence_text="担当へ相談できる環境",
    media_evidence_summary={},
    structure_variant="exact_clip_grounded",
    blockers=[],
)
candidate, diagnostic = finalize_draft(
    draft,
    batch_id="system_owned_direct_transform_test",
    history=[],
    sibling_drafts=[draft, sibling],
    quality_evaluator=evaluate_generation_quality,
    topic_validator=topic_coherence_validator,
    candidate_validator=candidate_blockers,
)
queue_plan = build_media_validation_plan(
    {
        "generation_mode": "direct_reference_media",
        "transformation_type": "transform",
        "rights_status": "approved_creator_clip",
        "permission_status": "approved",
        "content_type": "direct_image",
        "publisher_media_type": "IMAGE",
        "alignment_status": draft.caption.get("semantic_alignment", {}).get(
            "status", ""
        ),
        "final_alignment_score": draft.caption.get(
            "semantic_alignment", {}
        ).get("final_alignment_score", ""),
        "main_claim_coverage": draft.caption.get("semantic_alignment", {}).get(
            "main_claim_coverage", ""
        ),
        "unsupported_claim_count": draft.caption.get(
            "semantic_alignment", {}
        ).get("unsupported_claim_count", ""),
        "source_copy_similarity": draft.caption.get(
            "semantic_alignment", {}
        ).get("source_copy_similarity", ""),
        "recent_post_similarity": draft.caption.get(
            "semantic_alignment", {}
        ).get("recent_post_similarity", ""),
    },
    "night_scout",
    {
        "effective_media_url": media["storage_url"],
        "effective_media_urls": [media["storage_url"]],
        "media_asset_id": media["media_asset_id"],
        "media_type": "image",
    },
    draft.public_post_text,
)

checks = [
    (
        "external direct remains source preserving",
        external_mode == "source_copyedit",
    ),
    (
        "system-owned new-caption direct uses transform",
        owned_mode == "transform",
    ),
    (
        "registered approved source uses new commentary",
        registered_mode == "transform",
    ),
    (
        "registered source without provenance remains source preserving",
        registered_without_provenance_mode == "source_copyedit",
    ),
    (
        "runtime uses exact-evidence deterministic provider",
        draft.caption.get("provider_name") == "deterministic_evidence_context",
    ),
    (
        "runtime builder records transform",
        draft.caption.get("source_mode") == "transform",
    ),
    (
        "transform public validator passes",
        draft.public_validation.get("status") == "PASS",
    ),
    (
        "transform media validator passes",
        draft.media_validation.get("status") == "PASS",
    ),
    (
        "media validation receives transform",
        captured_plan.get("caption_mode") == "transform",
    ),
    (
        "batch-aware final candidate passes",
        candidate is not None and diagnostic.get("status") == "PASS",
    ),
    (
        "candidate persists transform provenance",
        candidate is not None
        and candidate.get("transformation_type") == "transform",
    ),
    (
        "queue worker preserves transform mode",
        queue_plan.get("caption_mode") == "transform",
    ),
    (
        "legacy queue remains source preserving",
        queue_caption_mode({}, direct_reference=True) == "source_copyedit",
    ),
]

failed = [name for name, passed in checks if not passed]
for name, passed in checks:
    print(f"  {'PASS' if passed else 'FAIL'} {name}")
if failed:
    print(
        {
            "failed": failed,
            "draft_blockers": draft.blockers,
            "diagnostic": diagnostic,
            "caption": draft.caption,
            "public_validation": draft.public_validation,
            "media_validation": draft.media_validation,
        }
    )
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
