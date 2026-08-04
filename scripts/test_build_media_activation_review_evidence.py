#!/usr/bin/env python3
"""Focused contracts for the review-only media activation evidence builder."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

MODULE_PATH = Path(__file__).with_name("build_media_activation_review_evidence.py")
spec = importlib.util.spec_from_file_location("review_evidence", MODULE_PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def permission(source_id: str = "src") -> dict[str, Any]:
    return {
        "permission_id": f"perm_{source_id}",
        "source_id": source_id,
        "rights_status": "approved_creator_clip",
        "permission_status": "approved",
        "evidence_reference": f"owner_attestation_{source_id}",
    }


def direct_selection(account_id: str = "liver_manager"):
    if account_id == "night_scout":
        original_text = "夜職で店を選ぶ時は、時給と控除、客層を確認して体験入店することが大事です。"
        visual_summary = "夜職の店選びについて、時給と控除、客層を説明している"
        visible_text = "夜職 店 時給 控除 客層"
    else:
        original_text = "配信で初見が入りやすい挨拶とコメントの入口を作ることが大事です。"
        visual_summary = "配信者が初見への挨拶とコメントについて話している"
        visible_text = "初見 コメント 配信"
    post = {
        "source_post_id": f"sp_{account_id}",
        "source_id": f"src_{account_id}",
        "target_account_id": account_id,
        "platform": "threads",
        "canonical_post_url": "https://www.threads.com/post/example",
        "external_post_id": "example",
        "original_post_text": original_text,
        "content_hash": "abc123",
    }
    media = {
        "media_asset_id": f"ma_{account_id}_direct",
        "source_post_media_id": f"spm_{account_id}",
        "storage_url": "https://cdn.example/direct.mp4",
        "original_media_url": "https://cdn.example/original.mp4",
        "media_type": "video",
        "duration_seconds": "20",
        "aspect_ratio": "1:1",
        "media_understanding": {
            "status": "PASS",
            "visual_summary": visual_summary,
            "visible_text": visible_text,
        },
    }
    source = {"source_id": post["source_id"]}
    return post, media, source


def clip_selection(account_id: str = "liver_manager"):
    transcript = (
        "夜職で店を選ぶ時は、時給と控除、客層を確認して体験入店すると判断しやすいです。"
        if account_id == "night_scout"
        else "配信で初見に挨拶してコメントの入口を作ると、リスナーが参加しやすくなります。"
    )
    clip = {
        "clip_candidate_id": f"clip_{account_id}",
        "source_video_id": f"sv_{account_id}",
        "source_id": f"src_clip_{account_id}",
        "transcript_grounded": "true",
        "transcript_excerpt": transcript,
        "start_seconds": "10",
        "end_seconds": "30",
    }
    video = {
        "source_video_id": clip["source_video_id"],
        "source_id": clip["source_id"],
        "canonical_video_url": "https://www.tiktok.com/@creator/video/1234567890",
        "platform": "tiktok",
    }
    asset = {
        "media_asset_id": f"ma_{account_id}_clip",
        "storage_url": "https://cdn.example/clip.mp4",
        "duration_seconds": "20",
        "aspect_ratio": "9:16",
        "width": "1080",
        "height": "1920",
        "video_stream_count": "1",
        "audio_stream_count": "1",
        "media_probe_status": "PASS",
    }
    return clip, video, asset


def caption(packet: dict[str, Any], recent: list[str]) -> dict[str, Any]:
    del recent
    route = packet["route"]
    text = (
        "配信で初見が入りやすくなるには、最初の挨拶とコメントの入口を用意することが大事です。\n\n"
        "次の配信では、答えやすい質問を一つ決めて反応を確認してみてください。"
        if route == "approved_source_clip"
        else "配信で初見が入りやすい挨拶とコメントの入口を作ることが大事です。"
    )
    return {
        "status": "PASS",
        "public_post_text": text,
        "provider_name": "test_provider",
        "provider_version": "1",
        "claim_support": [{"caption_claim": text, "source_evidence": packet["media_evidence_text"]}],
        "semantic_alignment": {
            "status": "PASS",
            "final_alignment_score": 0.95,
            "main_claim_coverage": 1.0,
            "unsupported_claim_count": 0,
            "source_copy_similarity": 0.3,
            "recent_post_similarity": 0.1,
        },
        "public_post_hash": mod._sha_text(text),
    }


def public_validator(text: Any, account_id: str) -> dict[str, Any]:
    del account_id
    return {
        "status": "PASS" if str(text).strip() else "BLOCKED",
        "blocked_reasons": [],
        "internal_leak_check": {"status": "PASS"},
        "account_fit_check": {"status": "PASS"},
    }


def media_validator(plan: dict[str, Any]) -> dict[str, Any]:
    required = (
        plan.get("media_asset_id")
        and plan.get("media_url")
        and plan.get("alignment_status") == "PASS"
        and float(plan.get("main_claim_coverage") or 0) >= 1.0
        and int(float(plan.get("unsupported_claim_count") if plan.get("unsupported_claim_count") not in (None, "") else 1)) == 0
    )
    return {"status": "PASS" if required else "BLOCKED", "blocked_reasons": [] if required else ["invalid_media_plan"]}


def quality(
    account_id: str,
    text: str,
    compared: list[str],
    *,
    batch_compared: list[dict[str, Any]],
    structure_variant: str,
    visual_text: str,
    primary_topic: str,
) -> dict[str, Any]:
    del account_id, text, compared, batch_compared, visual_text, primary_topic
    return {
        "status": "PASS",
        "batch_diversity_status": "PASS",
        "batch_similarity_score": 0.1,
        "primary_topic": "comment_activation",
        "supporting_topics": ["first_viewer_retention"],
        "topic_confidence": 0.9,
        "topic_coherence_status": "PASS",
        "topic_coherence_score": 100,
        "structure_variant": structure_variant,
        "hook_topic_match": True,
        "closing_topic_match": True,
        "visual_topic": "comment_activation",
        "visual_topic_match": True,
        "quality_gate_version": "generation_quality_v3",
        "diversity_blocked_reasons": [],
        "topic_blocked_reasons": [],
    }


def topic_validator(account_id: str, text: str, *, visual_text: str, primary_topic: str):
    del account_id, text, visual_text
    return {
        "status": "PASS",
        "visual_topic": primary_topic,
        "visual_topic_match": True,
    }


def candidate_validator(row: dict[str, Any]) -> list[str]:
    blockers = []
    for field in (
        "public_post_text",
        "permission_evidence",
        "media_asset_id",
        "media_url",
        "primary_topic",
        "visual_text_hash",
    ):
        if not str(row.get(field, "")).strip():
            blockers.append(f"{field}_missing")
    if row.get("status") != "WAITING_REVIEW":
        blockers.append("status_not_waiting_review")
    if str(row.get("auto_publish")).lower() != "false":
        blockers.append("auto_publish_not_false")
    for field in (
        "validator_status",
        "internal_leak_status",
        "account_fit_status",
        "alignment_status",
        "batch_diversity_status",
        "topic_coherence_status",
    ):
        if row.get(field) != "PASS":
            blockers.append(f"{field}_not_pass")
    if not row.get("visual_topic_match") or not row.get("visual_cta_match"):
        blockers.append("visual_not_matched")
    return blockers


def activation_planner(rows: list[dict[str, Any]]) -> dict[str, Any]:
    expected = {(a, r) for a in mod.ACCOUNTS for r in mod.ROUTES}
    actual = {(row["account_id"], row["content_route"]) for row in rows}
    return {
        "status": "PASS" if actual == expected and len(rows) == 4 else "BLOCKED",
        "row_count": len(rows),
        "rows": rows,
    }


def plan(**overrides: Any):
    direct = {account: direct_selection(account) for account in mod.ACCOUNTS}
    clips = {account: clip_selection(account) for account in mod.ACCOUNTS}
    permissions = {}
    for account in mod.ACCOUNTS:
        permissions[(account, "direct_reference_media")] = permission(f"src_{account}")
        permissions[(account, "approved_source_clip")] = permission(f"src_clip_{account}")
    args = {
        "direct_selections": direct,
        "clip_selections": clips,
        "permissions": permissions,
        "queue_rows": [],
        "posted_results": [],
        "batch_id": "review_batch_001",
        "direct_caption_builder": caption,
        "clip_caption_builder": caption,
        "direct_public_validator": public_validator,
        "clip_public_validator": public_validator,
        "media_validator": media_validator,
        "quality_evaluator": quality,
        "topic_validator": topic_validator,
        "candidate_validator": candidate_validator,
        "activation_planner": activation_planner,
    }
    args.update(overrides)
    return mod.build_review_evidence_plan(**args)


def test_four_rows_waiting_review_only() -> None:
    result = plan()
    assert result["status"] == "PASS"
    assert result["candidate_count"] == 4
    assert all(row["status"] == "WAITING_REVIEW" for row in result["candidates"])
    assert all(str(row["auto_publish"]).lower() == "false" for row in result["candidates"])


def test_no_ready_or_publish_side_effects() -> None:
    result = plan()
    serialized = json.dumps(result, ensure_ascii=False)
    assert '"status": "READY"' not in serialized
    safety = result["safety"]
    assert safety["production_write"] is False
    assert safety["sheets_write"] is False
    assert safety["queue_write"] is False
    assert safety["ready_transition"] is False
    assert safety["sns_post"] is False


def test_missing_permission_blocks_candidate() -> None:
    permissions = {
        ("night_scout", "direct_reference_media"): {},
        ("night_scout", "approved_source_clip"): permission("src_clip_night_scout"),
        ("liver_manager", "direct_reference_media"): permission("src_liver_manager"),
        ("liver_manager", "approved_source_clip"): permission("src_clip_liver_manager"),
    }
    result = plan(permissions=permissions)
    assert result["status"] == "BLOCKED"
    assert result["candidate_count"] == 3
    item = next(x for x in result["candidate_diagnostics"] if x["account_id"] == "night_scout" and x["content_route"] == "direct_reference_media")
    assert "permission_id_missing" in item["blockers"]


def test_missing_source_stays_missing() -> None:
    direct = {"night_scout": None, "liver_manager": direct_selection("liver_manager")}
    result = plan(direct_selections=direct)
    assert "night_scout:direct_reference_media" in result["missing_source_slots"]
    assert result["candidate_count"] == 3


def test_quiet_environment_contract() -> None:
    assert mod.safety_blockers({}) == []
    assert mod.safety_blockers({"PUBLISH_ENABLED": "true"}) == ["PUBLISH_ENABLED=true"]
    assert mod.safety_blockers({"GITHUB_MODELS_ENABLED": "1"}) == ["GITHUB_MODELS_ENABLED=true"]


def test_direct_media_understanding_required() -> None:
    selected = direct_selection("night_scout")
    selected[1]["media_understanding"] = {"status": "BLOCKED"}
    direct = {"night_scout": selected, "liver_manager": direct_selection("liver_manager")}
    result = plan(direct_selections=direct)
    item = next(x for x in result["candidate_diagnostics"] if x["account_id"] == "night_scout" and x["content_route"] == "direct_reference_media")
    assert any("media_understanding" in reason for reason in item["blockers"])


def test_clip_exact_transcript_required() -> None:
    selected = clip_selection("night_scout")
    selected[0]["transcript_excerpt"] = ""
    clips = {"night_scout": selected, "liver_manager": clip_selection("liver_manager")}
    result = plan(clip_selections=clips)
    item = next(x for x in result["candidate_diagnostics"] if x["account_id"] == "night_scout" and x["content_route"] == "approved_source_clip")
    assert "transcript_excerpt_missing" in item["blockers"]


def test_public_hash_mismatch_blocks() -> None:
    def mismatched(packet: dict[str, Any], recent: list[str]) -> dict[str, Any]:
        result = caption(packet, recent)
        result["public_post_hash"] = "wrong"
        return result

    result = plan(clip_caption_builder=mismatched)
    clip_items = [x for x in result["candidate_diagnostics"] if x["content_route"] == "approved_source_clip"]
    assert all("alignment_public_post_hash_mismatch" in item["blockers"] for item in clip_items)


def test_visual_evidence_is_hash_only() -> None:
    result = plan()
    for row in result["candidates"]:
        visual = json.loads(row["visual_plan_json"])
        assert visual["visual_plan_version"] == "visual_plan_v1"
        assert visual["overlay_mode"] == "none_existing_approved_media"
        assert visual["caption_cta_channel"] == "caption_only"
        assert "初見" not in row["visual_text_hash"]
        assert len(row["visual_text_hash"]) == 64


def test_batch_structure_compares_siblings() -> None:
    calls: list[tuple[str, int]] = []

    def observing_quality(account_id: str, text: str, compared: list[str], **kwargs: Any):
        calls.append((account_id, len(kwargs.get("batch_compared", []))))
        return quality(account_id, text, compared, **kwargs)

    result = plan(quality_evaluator=observing_quality)
    assert result["status"] == "PASS"
    assert calls == [
        ("night_scout", 1),
        ("night_scout", 1),
        ("liver_manager", 1),
        ("liver_manager", 1),
    ]


def test_candidate_contract_failure_removes_row() -> None:
    def reject_clip(row: dict[str, Any]) -> list[str]:
        return ["manual_test_block"] if row["content_route"] == "approved_source_clip" else candidate_validator(row)

    result = plan(candidate_validator=reject_clip)
    assert result["candidate_count"] == 2
    assert all(row["content_route"] == "direct_reference_media" for row in result["candidates"])


def test_external_model_flag_is_fail_closed() -> None:
    blockers = mod.safety_blockers({"GITHUB_MODELS_ENABLED": "true", "PUBLISH_ENABLED": "false"})
    assert blockers == ["GITHUB_MODELS_ENABLED=true"]



def test_direct_runtime_media_type_is_supported() -> None:
    observed: list[str] = []

    def validating(plan: dict[str, Any]) -> dict[str, Any]:
        if plan.get("media_origin") == "direct_reference":
            observed.append(str(plan.get("content_type")))
        return media_validator(plan)

    result = plan(media_validator=validating)
    assert result["status"] == "PASS"
    assert observed == ["direct_video", "direct_video"]


def test_direct_and_clip_public_validators_are_separate() -> None:
    calls: list[str] = []

    def direct_validator(text: Any, account_id: str) -> dict[str, Any]:
        calls.append(f"direct:{account_id}")
        return public_validator(text, account_id)

    def clip_validator(text: Any, account_id: str) -> dict[str, Any]:
        calls.append(f"clip:{account_id}")
        return public_validator(text, account_id)

    result = plan(
        direct_public_validator=direct_validator,
        clip_public_validator=clip_validator,
    )
    assert result["status"] == "PASS"
    assert calls == [
        "clip:night_scout",
        "direct:night_scout",
        "clip:liver_manager",
        "direct:liver_manager",
    ]



def test_sibling_text_is_in_full_similarity_comparison() -> None:
    observed: list[tuple[int, int]] = []

    def observing_quality(account_id: str, text: str, compared: list[Any], **kwargs: Any):
        del account_id, text
        sibling_count = sum(isinstance(item, dict) and str(item.get("candidate_id", "")).startswith("draft:") for item in compared)
        observed.append((sibling_count, len(kwargs.get("batch_compared", []))))
        return quality("liver_manager", "x", [], **kwargs)

    result = plan(quality_evaluator=observing_quality)
    assert result["status"] == "PASS"
    assert observed == [(1, 1), (1, 1), (1, 1), (1, 1)]




def test_direct_unusable_source_text_blocks_before_caption() -> None:
    selected = direct_selection("liver_manager")
    selected[0]["original_post_text"] = "絶対酔ってました！"
    direct = {
        "night_scout": direct_selection("night_scout"),
        "liver_manager": selected,
    }
    calls = 0

    def observing_caption(packet: dict[str, Any], recent: list[str]) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return caption(packet, recent)

    result = plan(
        direct_selections=direct,
        direct_caption_builder=observing_caption,
    )
    item = next(
        x
        for x in result["candidate_diagnostics"]
        if x["account_id"] == "liver_manager"
        and x["content_route"] == "direct_reference_media"
    )
    assert "direct_source_post_text_unusable" in item["blockers"]
    assert item["source_evidence_status"] == "SOURCE_EVIDENCE_UNSUITABLE"
    assert calls == 1


def test_direct_irrelevant_media_blocks_before_caption() -> None:
    selected = direct_selection("liver_manager")
    selected[1]["media_understanding"] = {
        "status": "PASS",
        "visual_summary": "若い人物が屋外でダンスをしている",
        "visible_text": "みんなで本番ダンス",
    }
    direct = {
        "night_scout": direct_selection("night_scout"),
        "liver_manager": selected,
    }
    result = plan(direct_selections=direct)
    item = next(
        x
        for x in result["candidate_diagnostics"]
        if x["account_id"] == "liver_manager"
        and x["content_route"] == "direct_reference_media"
    )
    assert "direct_media_account_evidence_insufficient" in item["blockers"]
    assert item["source_evidence_status"] == "SOURCE_EVIDENCE_UNSUITABLE"


def test_direct_source_media_topic_mismatch_blocks() -> None:
    selected = direct_selection("liver_manager")
    selected[1]["media_understanding"] = {
        "status": "PASS",
        "visual_summary": "ライバー事務所の所属条件とサポートを説明している",
        "visible_text": "事務所 所属 サポート",
    }
    direct = {
        "night_scout": direct_selection("night_scout"),
        "liver_manager": selected,
    }
    result = plan(direct_selections=direct)
    item = next(
        x
        for x in result["candidate_diagnostics"]
        if x["account_id"] == "liver_manager"
        and x["content_route"] == "direct_reference_media"
    )
    assert "direct_source_media_topic_mismatch" in item["blockers"]


def test_clip_single_generic_term_is_insufficient() -> None:
    selected = clip_selection("liver_manager")
    selected[0]["transcript_excerpt"] = (
        "でそういうところにさないやっぱり、よく紙巻きとかやってる人とか、"
        "たまたま投げに出てきてくれたとしても、すごいと思うかもしれない"
    )
    clips = {
        "night_scout": clip_selection("night_scout"),
        "liver_manager": selected,
    }
    result = plan(clip_selections=clips)
    item = next(
        x
        for x in result["candidate_diagnostics"]
        if x["account_id"] == "liver_manager"
        and x["content_route"] == "approved_source_clip"
    )
    assert "clip_account_evidence_insufficient" in item["blockers"]
    assert item["source_evidence_status"] == "SOURCE_EVIDENCE_UNSUITABLE"


def test_clip_requires_minimum_transcript_length() -> None:
    selected = clip_selection("liver_manager")
    selected[0]["transcript_excerpt"] = "配信で初見とコメント"
    clips = {
        "night_scout": clip_selection("night_scout"),
        "liver_manager": selected,
    }
    result = plan(clip_selections=clips)
    item = next(
        x
        for x in result["candidate_diagnostics"]
        if x["account_id"] == "liver_manager"
        and x["content_route"] == "approved_source_clip"
    )
    assert "clip_transcript_too_short_for_grounding" in item["blockers"]


def test_good_source_suitability_summary_is_persisted() -> None:
    result = plan()
    assert result["status"] == "PASS"
    for item in result["candidate_diagnostics"]:
        assert item["source_evidence_status"] == "PASS"
        summary = item["source_evidence_summary"]
        assert summary["minimum_account_term_count"] == 2

def _permission_checker(
    row: dict[str, Any],
    *,
    account_id: str,
    operation: str,
) -> bool:
    del account_id, operation
    return (
        row.get("permission_status") == "approved"
        and bool(row.get("evidence_reference"))
    )


def test_source_suitable_selection_skips_irrelevant_first() -> None:
    first = direct_selection("liver_manager")
    first[0]["source_post_id"] = "sp_irrelevant"
    first[1]["source_post_media_id"] = "spm_irrelevant"
    first[1]["media_asset_id"] = "ma_irrelevant"
    first[1]["media_understanding"] = {
        "status": "PASS",
        "visual_summary": "若い人物が屋外でダンスをしている",
        "visible_text": "みんなで本番ダンス",
    }

    second = direct_selection("liver_manager")
    second[0]["source_post_id"] = "sp_suitable"
    second[1]["source_post_media_id"] = "spm_suitable"
    second[1]["media_asset_id"] = "ma_suitable"

    selected, selected_permission, rejections = (
        mod.select_source_suitable_direct_candidate(
            [first, second],
            permissions=[
                permission("src_liver_manager")
            ],
            account_id="liver_manager",
            permission_checker=_permission_checker,
        )
    )

    assert selected is not None
    assert selected[0]["source_post_id"] == "sp_suitable"
    assert selected_permission["permission_id"] == (
        "perm_src_liver_manager"
    )
    assert rejections == [
        {
            "source_post_id": "sp_irrelevant",
            "source_id": "src_liver_manager",
            "status": "SOURCE_EVIDENCE_UNSUITABLE",
            "blockers": [
                "direct_media_account_evidence_insufficient"
            ],
        }
    ]


def test_source_suitable_selection_skips_missing_permission() -> None:
    first = direct_selection("liver_manager")
    first[0]["source_post_id"] = "sp_unpermissioned"
    first[0]["source_id"] = "src_unpermissioned"
    first[2]["source_id"] = "src_unpermissioned"

    second = direct_selection("liver_manager")
    second[0]["source_post_id"] = "sp_permissioned"

    selected, selected_permission, rejections = (
        mod.select_source_suitable_direct_candidate(
            [first, second],
            permissions=[
                permission("src_liver_manager")
            ],
            account_id="liver_manager",
            permission_checker=_permission_checker,
        )
    )

    assert selected is not None
    assert selected[0]["source_post_id"] == "sp_permissioned"
    assert selected_permission["source_id"] == (
        "src_liver_manager"
    )
    assert rejections[0]["source_post_id"] == (
        "sp_unpermissioned"
    )
    assert rejections[0]["blockers"] == [
        "active_direct_permission_missing"
    ]


def test_source_suitable_selection_all_rejected() -> None:
    selected = direct_selection("liver_manager")
    selected[0]["source_post_id"] = "sp_only_bad"
    selected[1]["media_understanding"] = {
        "status": "PASS",
        "visual_summary": "料理を作って皿に盛り付けている",
        "visible_text": "今日の晩ごはん",
    }

    result, selected_permission, rejections = (
        mod.select_source_suitable_direct_candidate(
            [selected],
            permissions=[
                permission("src_liver_manager")
            ],
            account_id="liver_manager",
            permission_checker=_permission_checker,
        )
    )

    assert result is None
    assert selected_permission == {}
    assert rejections[0]["source_post_id"] == "sp_only_bad"
    assert (
        "direct_media_account_evidence_insufficient"
        in rejections[0]["blockers"]
    )


def _clip_selector(
    selections: list[
        tuple[
            dict[str, Any],
            dict[str, Any],
            dict[str, Any],
        ]
    ],
):
    def select(
        clips,
        source_videos,
        media_assets,
        posted_results,
        account_id,
        excluded_clip_ids=None,
    ):
        del (
            clips,
            source_videos,
            media_assets,
            posted_results,
            account_id,
        )
        excluded = excluded_clip_ids or set()
        for selection in selections:
            clip_id = str(
                selection[0].get(
                    "clip_candidate_id",
                    "",
                )
            )
            if clip_id not in excluded:
                return (
                    selection[0],
                    selection[1],
                    selection[2],
                    [],
                )
        return None, None, None, [
            "no_more_saved_clip_candidates"
        ]

    return select


def _clip_permission_checker(
    row: dict[str, Any],
    *,
    account_id: str,
    operation: str,
) -> bool:
    del account_id
    return (
        operation == "clip"
        and row.get("permission_status")
        == "approved"
        and bool(row.get("evidence_reference"))
    )


def test_clip_fallback_skips_unsuitable_first() -> None:
    first = clip_selection("liver_manager")
    first[0]["clip_candidate_id"] = "clip_bad"
    first[0]["transcript_excerpt"] = (
        "紙巻きについて話しながら、"
        "楽しいかどうかを雑談している場面です。"
    )

    second = clip_selection("liver_manager")
    second[0]["clip_candidate_id"] = "clip_good"

    selected, selected_permission, rejected, reasons = (
        mod.select_source_suitable_clip_candidate(
            selector=_clip_selector(
                [first, second]
            ),
            clips=[],
            source_videos=[],
            media_assets=[{}, {}],
            posted_results=[],
            permissions=[
                permission(
                    "src_clip_liver_manager"
                )
            ],
            account_id="liver_manager",
            permission_checker=(
                _clip_permission_checker
            ),
        )
    )

    assert selected is not None
    assert (
        selected[0]["clip_candidate_id"]
        == "clip_good"
    )
    assert selected_permission["permission_id"] == (
        "perm_src_clip_liver_manager"
    )
    assert rejected == [
        {
            "clip_candidate_id": "clip_bad",
            "source_video_id": (
                "sv_liver_manager"
            ),
            "source_id": (
                "src_clip_liver_manager"
            ),
            "media_asset_id": (
                "ma_liver_manager_clip"
            ),
            "status": (
                "SOURCE_EVIDENCE_UNSUITABLE"
            ),
            "blockers": [
                "clip_account_evidence_insufficient"
            ],
        }
    ]
    assert reasons == []


def test_clip_fallback_skips_missing_permission() -> None:
    first = clip_selection("liver_manager")
    first[0]["clip_candidate_id"] = (
        "clip_unpermissioned"
    )
    first[0]["source_id"] = (
        "src_unpermissioned"
    )
    first[1]["source_id"] = (
        "src_unpermissioned"
    )

    second = clip_selection("liver_manager")
    second[0]["clip_candidate_id"] = (
        "clip_permissioned"
    )

    selected, selected_permission, rejected, _ = (
        mod.select_source_suitable_clip_candidate(
            selector=_clip_selector(
                [first, second]
            ),
            clips=[],
            source_videos=[],
            media_assets=[{}, {}],
            posted_results=[],
            permissions=[
                permission(
                    "src_clip_liver_manager"
                )
            ],
            account_id="liver_manager",
            permission_checker=(
                _clip_permission_checker
            ),
        )
    )

    assert selected is not None
    assert (
        selected[0]["clip_candidate_id"]
        == "clip_permissioned"
    )
    assert selected_permission["source_id"] == (
        "src_clip_liver_manager"
    )
    assert rejected[0][
        "clip_candidate_id"
    ] == "clip_unpermissioned"
    assert rejected[0]["blockers"] == [
        "active_clip_permission_missing"
    ]


def test_clip_fallback_all_unsuitable() -> None:
    first = clip_selection("night_scout")
    first[0]["clip_candidate_id"] = "clip_bad"
    first[0]["transcript_excerpt"] = (
        "今日の料理を作って、"
        "盛り付けについて説明しています。"
    )

    selected, selected_permission, rejected, reasons = (
        mod.select_source_suitable_clip_candidate(
            selector=_clip_selector([first]),
            clips=[],
            source_videos=[],
            media_assets=[{}],
            posted_results=[],
            permissions=[
                permission(
                    "src_clip_night_scout"
                )
            ],
            account_id="night_scout",
            permission_checker=(
                _clip_permission_checker
            ),
        )
    )

    assert selected is None
    assert selected_permission == {}
    assert rejected[0]["clip_candidate_id"] == (
        "clip_bad"
    )
    assert (
        "clip_account_evidence_insufficient"
        in rejected[0]["blockers"]
    )
    assert (
        "no_more_saved_clip_candidates"
        in reasons
    )


def main() -> None:
    tests = [value for name, value in globals().items() if name.startswith("test_") and callable(value)]
    for test in sorted(tests, key=lambda item: item.__name__):
        test()
    print(f"PASS {len(tests)} tests")


if __name__ == "__main__":
    main()
