#!/usr/bin/env python3
"""Focused pure contracts for media activation source suitability inventory."""

from __future__ import annotations

import importlib.util
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

MODULE_PATH = Path(__file__).with_name("inventory_media_activation_sources.py")
spec = importlib.util.spec_from_file_location("source_inventory", MODULE_PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def active_permission(
    source_id: str,
    account_id: str,
    *,
    direct: bool = True,
    clip: bool = True,
) -> dict[str, Any]:
    return {
        "permission_id": f"perm_{source_id}_{account_id}",
        "source_id": source_id,
        "account_id": account_id,
        "rights_status": "approved_creator_clip",
        "permission_status": "approved",
        "evidence_reference": f"owner_attestation_{source_id}",
        "allow_cloudinary_storage": "true",
        "allow_original_repost": "true" if direct else "false",
        "allow_cut": "true" if clip else "false",
        "allow_clip_repost": "true" if clip else "false",
        "allow_new_caption": "true",
    }


def permission_checker(row: dict[str, Any], *, account_id: str, operation: str) -> bool:
    if row.get("account_id") != account_id:
        return False
    if row.get("permission_status") != "approved":
        return False
    if operation == "direct":
        return row.get("allow_original_repost") == "true"
    if operation == "clip":
        return row.get("allow_clip_repost") == "true"
    return False


def direct_fixture(
    account_id: str = "liver_manager",
    *,
    source_id: str = "src_direct",
    post_id: str = "sp_direct",
    permission: bool = True,
    understanding: bool = True,
    uploaded: bool = True,
    off_topic: bool = False,
    duration_seconds: str = "20",
    media_type: str = "video",
    source_url: str = "https://www.threads.com/@creator/post/example",
) -> dict[str, list[dict[str, Any]]]:
    if account_id == "night_scout":
        text = "夜職の店を選ぶ時は、時給と控除、客層を確認して体験入店することが大事です。"
        visual = "夜職の店舗で時給と控除、客層について説明している"
    else:
        text = "配信で初見が入りやすくなるには、挨拶とコメントの入口を作ることが大事です。"
        visual = "配信者が初見への挨拶とコメントについて説明している"
    if off_topic:
        text = "絶対酔っていました。みんなで屋外に集まって楽しく踊りました。"
        visual = "若い人物が屋外でダンスをしている"
    media_id = f"spm_{post_id}"
    asset_id = f"ma_{post_id}"
    data = {
        "source_posts": [{
            "source_post_id": post_id,
            "source_id": source_id,
            "target_account_id": account_id,
            "platform": "threads",
            "canonical_post_url": source_url,
            "original_post_text": text,
            "published_at": "2026-08-01T00:00:00+00:00",
        }],
        "source_post_media": [{
            "source_post_media_id": media_id,
            "source_post_id": post_id,
            "media_index": "0",
            "media_type": media_type,
            "original_media_url": "https://origin.example/video.mp4",
        }],
        "media_assets": [{
            "media_asset_id": asset_id,
            "reference_post_id": post_id,
            "source_post_media_id": media_id,
            "original_media_url": "https://origin.example/video.mp4",
            "storage_url": "https://cdn.example/video.mp4" if uploaded else "",
            "cloudinary_status": "UPLOADED" if uploaded else "PENDING",
            "media_type": media_type,
            "duration_seconds": duration_seconds,
        }],
        "source_media_understanding": [{
            "source_post_media_id": media_id,
            "status": "PASS" if understanding else "BLOCKED",
            "visual_summary": visual if understanding else "",
            "visible_text": (
                "配信 初見 コメント" if account_id == "liver_manager" else "夜職 店 時給 控除"
            ) if understanding and not off_topic else ("ダンス 練習" if understanding else ""),
        }],
        "source_accounts": [{"source_id": source_id, "priority": "5"}],
        "reference_sources": [],
        "media_permissions": [active_permission(source_id, account_id)] if permission else [],
        "queue": [],
        "posted_results": [],
        "video_clip_candidates": [],
        "source_videos": [],
    }
    return data


def clip_fixture(
    account_id: str = "liver_manager",
    *,
    source_id: str = "src_clip",
    clip_id: str = "clip_1",
    permission: bool = True,
    transcript_good: bool = True,
    uploaded: bool = True,
    video_evidence: bool = True,
    quarantined: bool = False,
    synthetic: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    if account_id == "night_scout":
        transcript = "夜職の店を選ぶなら、時給と控除、客層を確認して体験入店すると判断しやすいです。"
    else:
        transcript = "配信で初見に挨拶してコメントの入口を作ると、リスナーが参加しやすくなります。"
    if not transcript_good:
        transcript = "たまたま投げに出てきたらすごい。"
    video_id = f"sv_{clip_id}"
    asset_id = f"ma_{clip_id}"
    return {
        "video_clip_candidates": [{
            "clip_candidate_id": clip_id,
            "source_video_id": video_id,
            "source_id": source_id,
            "account_id": account_id,
            "clip_status": "READY",
            "transcript_grounded": "true",
            "transcript_excerpt": transcript,
            "start_seconds": "10",
            "end_seconds": "30",
            "confidence_score": "0.9",
            "quarantined_at": "2026-08-01T00:00:00+00:00" if quarantined else "",
        }],
        "source_videos": [{
            "source_video_id": video_id,
            "source_id": source_id,
            "account_id": account_id,
            "platform": "tiktok",
            "canonical_video_url": "https://www.tiktok.com/@creator/video/1234567890",
        }],
        "media_assets": [{
            "media_asset_id": asset_id,
            "clip_candidate_id": clip_id,
            "account_id": account_id,
            "storage_url": "https://cdn.example/clip.mp4" if uploaded else "",
            "upload_status": "UPLOADED" if uploaded else "PENDING",
            "media_origin": "system_generated" if synthetic else "approved_source_clip",
            "video_stream_count": "1" if video_evidence else "0",
            "audio_stream_count": "1",
            "media_probe_status": "PASS" if video_evidence else "BLOCKED",
        }],
        "media_permissions": [active_permission(source_id, account_id)] if permission else [],
        "queue": [],
        "posted_results": [],
        "source_posts": [],
        "source_post_media": [],
        "source_media_understanding": [],
        "source_accounts": [],
        "reference_sources": [],
    }


def merge_data(*parts: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    keys = {
        "source_posts", "source_post_media", "media_assets",
        "source_media_understanding", "source_accounts", "reference_sources",
        "media_permissions", "queue", "posted_results",
        "video_clip_candidates", "source_videos",
    }
    result = {key: [] for key in keys}
    for part in parts:
        for key in keys:
            result[key].extend(deepcopy(part.get(key, [])))
    return result


def direct_rows(data: dict[str, list[dict[str, Any]]], account_id: str = "liver_manager"):
    return mod.build_direct_inventory(
        account_id=account_id,
        source_posts=data["source_posts"],
        source_post_media=data["source_post_media"],
        media_assets=data["media_assets"],
        source_media_understanding=data["source_media_understanding"],
        source_accounts=data["source_accounts"],
        reference_sources=data["reference_sources"],
        permissions=data["media_permissions"],
        queue_rows=data["queue"],
        posted_results=data["posted_results"],
        permission_checker=permission_checker,
    )


def clip_rows(data: dict[str, list[dict[str, Any]]], account_id: str = "liver_manager"):
    return mod.build_clip_inventory(
        account_id=account_id,
        clips=data["video_clip_candidates"],
        source_videos=data["source_videos"],
        media_assets=data["media_assets"],
        permissions=data["media_permissions"],
        queue_rows=data["queue"],
        posted_results=data["posted_results"],
        permission_checker=permission_checker,
    )


def test_safety_blockers():
    assert mod.safety_blockers({"PUBLISH_ENABLED": "true"}) == ["PUBLISH_ENABLED=true"]
    assert mod.safety_blockers({}) == []


def test_direct_ready():
    row = direct_rows(direct_fixture())[0]
    assert row["candidate_status"] == mod.READY
    assert row["permission_active"] is True
    assert row["blockers"] == []


def test_direct_permission_review():
    row = direct_rows(direct_fixture(permission=False))[0]
    assert row["candidate_status"] == mod.PERMISSION_REVIEW
    assert "active_direct_permission_missing" in row["blockers"]
    assert row["human_approval_required"] is True


def test_direct_off_topic_rejected():
    row = direct_rows(direct_fixture(off_topic=True))[0]
    assert row["candidate_status"] == mod.UNSUITABLE
    assert "direct_source_account_evidence_insufficient" in row["blockers"]


def test_direct_understanding_repair():
    row = direct_rows(direct_fixture(understanding=False))[0]
    assert row["candidate_status"] == mod.SOURCE_REPAIR
    assert any("media_understanding_not_pass" in reason for reason in row["blockers"])


def test_direct_upload_repair():
    row = direct_rows(direct_fixture(uploaded=False))[0]
    assert row["candidate_status"] == mod.SOURCE_REPAIR
    assert any("media_not_uploaded" in reason for reason in row["blockers"])


def test_direct_over_limit_video_excluded():
    row = direct_rows(direct_fixture(duration_seconds="301"))[0]
    assert row["candidate_status"] == mod.EXCLUDED
    assert any(
        "video_duration_above_direct_limit" in reason
        for reason in row["hard_blockers"]
    )
    assert not any(
        "video_duration_above_direct_limit" in reason
        for reason in row["repair_blockers"]
    )


def test_direct_unsupported_media_type_excluded():
    row = direct_rows(direct_fixture(media_type="audio"))[0]
    assert row["candidate_status"] == mod.EXCLUDED
    assert any(
        "unsupported_media_type" in reason
        for reason in row["hard_blockers"]
    )


def test_direct_invalid_parent_url_excluded():
    row = direct_rows(
        direct_fixture(
            source_url="https://www.threads.com/@creator",
        )
    )[0]
    assert row["candidate_status"] == mod.EXCLUDED
    assert "individual_source_post_url_required" in row["hard_blockers"]


def test_direct_quarantined_excluded():
    data = direct_fixture()
    data["source_posts"][0]["quarantined_at"] = "2026-08-01T00:00:00+00:00"
    row = direct_rows(data)[0]
    assert row["candidate_status"] == mod.EXCLUDED


def test_direct_remaining_eight_parent_excluded():
    source_id = "fresh_remaining_eight_20260730225046_night_scout_direct_carousel"
    post_id = f"sp_{source_id}"
    data = direct_fixture(
        "night_scout",
        source_id=source_id,
        post_id=post_id,
    )
    data["source_posts"][0].update({
        "platform": "system_generated_owned",
        "collection_backend": "system_owned_media",
    })
    row = direct_rows(data, "night_scout")[0]
    assert row["candidate_status"] == mod.EXCLUDED
    assert "synthetic_source_forbidden" in row["blockers"]


def test_synthetic_identity_detects_parent_provenance():
    assert mod._synthetic_identity({
        "source_post_id": "sp_fresh_remaining_eight_20260730225046_direct",
        "source_id": "fresh_remaining_eight_20260730225046_direct",
        "platform": "system_generated_owned",
        "collection_backend": "system_owned_media",
    })


def test_direct_used_excluded():
    data = direct_fixture()
    data["posted_results"].append({
        "status": "POSTED",
        "source_post_id": "sp_direct",
        "media_asset_id": "ma_sp_direct",
    })
    row = direct_rows(data)[0]
    assert row["candidate_status"] == mod.EXCLUDED


def test_direct_scope_gap_requires_review():
    data = direct_fixture()
    data["media_permissions"][0]["allow_new_caption"] = "false"
    row = direct_rows(data)[0]
    assert row["candidate_status"] == mod.PERMISSION_REVIEW
    assert "permission_scope_missing:allow_new_caption" in row["blockers"]


def test_direct_sort_prefers_ready():
    ready = direct_fixture(source_id="src_ready", post_id="sp_ready")
    review = direct_fixture(source_id="src_review", post_id="sp_review", permission=False)
    rows = direct_rows(merge_data(review, ready))
    assert rows[0]["source_post_id"] == "sp_ready"
    assert rows[0]["candidate_status"] == mod.READY


def test_slot_never_recommends_hard_blocked_direct_candidate():
    hard_blocked = direct_fixture(
        source_id="src_hard",
        post_id="sp_hard",
        duration_seconds="301",
    )
    repairable = direct_fixture(
        source_id="src_repair",
        post_id="sp_repair",
        uploaded=False,
    )
    rows = direct_rows(merge_data(hard_blocked, repairable))
    slot = mod.summarize_slot(
        "liver_manager",
        "direct_reference_media",
        rows,
    )
    assert slot["route_status"] == "EXISTING_SOURCE_REPAIR_REQUIRED"
    assert slot["recommended_candidate_id"] == "sp_repair"
    assert slot["top_audit_candidate_id"] == "sp_repair"


def test_clip_ready():
    row = clip_rows(clip_fixture())[0]
    assert row["candidate_status"] == mod.READY
    assert row["asset_video_evidence"] is True


def test_clip_permission_review():
    row = clip_rows(clip_fixture(permission=False))[0]
    assert row["candidate_status"] == mod.PERMISSION_REVIEW
    assert "active_clip_permission_missing" in row["blockers"]


def test_clip_weak_transcript_unsuitable():
    row = clip_rows(clip_fixture(transcript_good=False))[0]
    assert row["candidate_status"] == mod.UNSUITABLE
    assert "clip_account_evidence_insufficient" in row["blockers"]


def test_clip_missing_upload_repair():
    row = clip_rows(clip_fixture(uploaded=False))[0]
    assert row["candidate_status"] == mod.SOURCE_REPAIR
    assert "media_asset_not_uploaded" in row["blockers"]


def test_clip_missing_video_evidence_repair():
    row = clip_rows(clip_fixture(video_evidence=False))[0]
    assert row["candidate_status"] == mod.SOURCE_REPAIR
    assert "media_stream_evidence_missing" in row["blockers"]


def test_clip_quarantined_excluded():
    row = clip_rows(clip_fixture(quarantined=True))[0]
    assert row["candidate_status"] == mod.EXCLUDED


def test_clip_synthetic_excluded():
    row = clip_rows(clip_fixture(synthetic=True))[0]
    assert row["candidate_status"] == mod.EXCLUDED
    assert "synthetic_media_forbidden" in row["blockers"]


def test_clip_used_excluded():
    data = clip_fixture()
    data["queue"].append({
        "status": "WAITING_REVIEW",
        "clip_candidate_id": "clip_1",
        "media_asset_id": "ma_clip_1",
    })
    row = clip_rows(data)[0]
    assert row["candidate_status"] == mod.EXCLUDED


def test_clip_scope_gap_requires_review():
    data = clip_fixture()
    data["media_permissions"][0]["allow_cut"] = "false"
    row = clip_rows(data)[0]
    assert row["candidate_status"] == mod.PERMISSION_REVIEW
    assert "permission_scope_missing:allow_cut" in row["blockers"]


def test_slot_ready_summary():
    rows = direct_rows(direct_fixture())
    slot = mod.summarize_slot("liver_manager", "direct_reference_media", rows)
    assert slot["route_status"] == "EXISTING_SOURCE_READY"
    assert slot["recommended_candidate_id"] == "sp_direct"


def test_slot_permission_summary():
    rows = direct_rows(direct_fixture(permission=False))
    slot = mod.summarize_slot("liver_manager", "direct_reference_media", rows)
    assert slot["route_status"] == "HUMAN_PERMISSION_REVIEW_REQUIRED"
    assert slot["human_approval_required"] is True


def test_slot_repair_summary():
    rows = clip_rows(clip_fixture(uploaded=False))
    slot = mod.summarize_slot("liver_manager", "approved_source_clip", rows)
    assert slot["route_status"] == "EXISTING_SOURCE_REPAIR_REQUIRED"


def test_slot_new_source_summary():
    rows = clip_rows(clip_fixture(transcript_good=False))
    slot = mod.summarize_slot("liver_manager", "approved_source_clip", rows)
    assert slot["route_status"] == "NEW_SOURCE_REQUIRED"
    assert slot["recommended_candidate_id"] == ""


def test_full_inventory_four_ready():
    data = merge_data(
        direct_fixture("night_scout", source_id="src_ns_d", post_id="sp_ns_d"),
        direct_fixture("liver_manager", source_id="src_lm_d", post_id="sp_lm_d"),
        clip_fixture("night_scout", source_id="src_ns_c", clip_id="clip_ns"),
        clip_fixture("liver_manager", source_id="src_lm_c", clip_id="clip_lm"),
    )
    report = mod.build_source_inventory(
        datasets=data,
        permission_checker=permission_checker,
    )
    assert report["status"] == "PASS_EXISTING_SOURCES_READY"
    assert report["ready_slot_count"] == 4
    assert report["new_source_slot_count"] == 0
    assert report["planned_external_operations"] == []


def test_full_inventory_blocked_and_safe():
    data = merge_data(
        direct_fixture("night_scout", source_id="src_ns_d", post_id="sp_ns_d", permission=False),
        direct_fixture("liver_manager", source_id="src_lm_d", post_id="sp_lm_d", off_topic=True),
        clip_fixture("night_scout", source_id="src_ns_c", clip_id="clip_ns", quarantined=True),
        clip_fixture("liver_manager", source_id="src_lm_c", clip_id="clip_lm", transcript_good=False),
    )
    report = mod.build_source_inventory(
        datasets=data,
        permission_checker=permission_checker,
    )
    assert report["status"] == "BLOCKED_SOURCE_OR_PERMISSION_REPAIR_REQUIRED"
    assert report["permission_review_slot_count"] == 1
    assert report["new_source_slot_count"] == 3
    assert all(value is False for value in report["safety"].values())


def test_no_executable_operations_in_candidates():
    data = merge_data(direct_fixture(), clip_fixture())
    report = mod.build_source_inventory(
        datasets=data,
        permission_checker=permission_checker,
    )
    assert report["planned_external_operations"] == []
    for account in mod.ACCOUNTS:
        for route in mod.ROUTES:
            for row in report["candidates"][account][route]:
                assert row["external_operations"] == []


def test_deterministic_inventory():
    data = merge_data(
        direct_fixture(source_id="src_a", post_id="sp_a", permission=False),
        direct_fixture(source_id="src_b", post_id="sp_b", permission=True),
        clip_fixture(source_id="src_c", clip_id="clip_c"),
    )
    first = mod.build_source_inventory(datasets=data, permission_checker=permission_checker)
    second = mod.build_source_inventory(datasets=deepcopy(data), permission_checker=permission_checker)
    assert first == second


def main() -> None:
    tests = [
        value
        for name, value in sorted(globals().items())
        if name.startswith("test_") and callable(value)
    ]
    for test in tests:
        test()
    print(f"PASS {len(tests)} tests")


if __name__ == "__main__":
    main()
