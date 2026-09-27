#!/usr/bin/env python3
"""Fail-closed tests for reconstructing missing source-video ledger rows."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

from media_growth_schemas import build_source_video  # noqa: E402
from reference.source_registry import load_registry  # noqa: E402
from run_media_production_pipeline import (  # noqa: E402
    repair_missing_source_video_lineage,
    source_video_lineage_repairs,
)
from sheets_client import TAB_DEFINITIONS  # noqa: E402


def fixture():
    source = next(row for row in load_registry() if row["source_id"] == "src_lm_yt_cand_001")
    account = "liver_manager"
    url = "https://www.youtube.com/watch?v=AbCdEfGhIjK"
    video_id = "AbCdEfGhIjK"
    source_video = build_source_video(source, video_url=url, title="Stored source", duration_seconds=120)
    digest = hashlib.sha256(b"verified original full source").hexdigest()
    parent_id = "sp_lm_lineage_001"
    media_id = "ma_lm_lineage_001"
    storage = "https://res.cloudinary.com/example/video/upload/v1/lineage.mp4"
    clip = {
        "clip_candidate_id": "clip_lineage_001",
        "source_video_id": source_video["source_video_id"],
        "source_id": source["source_id"],
        "account_id": account,
        "platform": "youtube",
        "video_id": video_id,
        "canonical_video_url": url,
    }
    parent = {
        "source_post_id": parent_id,
        "source_id": source["source_id"],
        "target_account_id": account,
        "platform": "youtube",
        "canonical_post_url": url,
        "external_post_id": video_id,
        "author_handle": str(source["source_handle"]).lstrip("@"),
        "media_count": "1",
        "rights_status": "approved_creator_clip",
        "permission_status": "approved",
    }
    media = {
        "source_post_media_id": "spm_lm_lineage_001",
        "source_post_id": parent_id,
        "media_index": "0",
        "canonical_post_url": url,
        "original_media_url": url,
        "resolver_backend": "yt_dlp",
        "media_type": "video",
        "duration_seconds": "120",
        "content_hash": digest,
        "cloudinary_status": "UPLOADED",
        "storage_url": storage,
        "rights_status": "approved_creator_clip",
        "permission_status": "approved",
        "media_asset_id": media_id,
    }
    asset = {
        "media_id": media_id,
        "account_id": account,
        "reference_post_id": parent_id,
        "source_post_url": url,
        "media_type": "video",
        "duration_seconds": "120",
        "content_hash": digest,
        "storage_url": storage,
        "upload_status": "UPLOADED",
        "rights_status": "approved_creator_clip",
        "permission_status": "approved",
        "media_role": "full_source",
    }
    permission = {
        "source_id": source["source_id"],
        "account_id": account,
        "allowed_accounts": account,
        "source_handle": str(source["source_handle"]).lstrip("@"),
        "permission_status": "approved",
        "rights_status": "approved_creator_clip",
        "usage_mode": "approved_creator_clip",
        "evidence_type": "owner_attestation",
        "evidence_reference": "existing-evidence",
        "approved_by": "owner",
        "approved_at": "2026-01-01T00:00:00Z",
        "revoked": "false",
        **{name: "true" for name in (
            "allow_download", "allow_cloudinary_storage", "allow_analysis",
            "allow_cut", "allow_clip_repost", "allow_new_caption", "allow_edit",
        )},
    }
    return source, clip, source_video, parent, media, asset, permission


def plan(parts, *, parents_override=None, media_override=None, asset_override=None,
         permissions_override=None, registered_override=None, clips_override=None,
         source_videos_override=None):
    source, clip, source_video, parent, media, asset, permission = parts
    return source_video_lineage_repairs(
        clips=clips_override or [clip], source_videos=source_videos_override or [],
        source_posts=parents_override or [parent],
        source_post_media=media_override or [media], media_assets=asset_override or [asset],
        media_permissions=permissions_override or [permission],
        registered_sources=registered_override or [source], account_id="liver_manager",
    )


class Worksheet:
    def __init__(self, headers, rows=None):
        self.headers = list(headers)
        self.rows = [dict(row) for row in rows or []]

    def row_values(self, _index):
        return list(self.headers)

    def get_all_records(self):
        return [dict(row) for row in self.rows]

    def append_row(self, values, value_input_option=None):
        assert value_input_option == "USER_ENTERED"
        self.rows.append(dict(zip(self.headers, values)))


class SheetClient:
    def __init__(self, datasets):
        self.tabs = {
            logical: Worksheet(TAB_DEFINITIONS[logical], rows)
            for logical, rows in datasets.items()
        }

    def _ensure_tab(self, logical, headers):
        self.tabs.setdefault(logical, Worksheet(headers))

    def _ws(self, logical):
        return self.tabs[logical]


def run() -> int:
    passed = 0
    failures = []
    parts = fixture()

    rows, counters = plan(parts)
    passed += int(len(rows) == 1 and counters["repairable"] == 1
                  and rows[0]["discovery_status"] == "REPAIRED_FROM_VERIFIED_LINEAGE")
    if not rows:
        failures.append("exact_provenance_must_repair")

    source, clip, source_video, *_rest = parts
    missing_link = {**clip, "source_video_id": ""}
    rows, counters = plan(parts, clips_override=[missing_link])
    passed += int(len(rows) == 1 and counters["repairable"] == 1
                  and rows[0]["source_video_id"] == source_video["source_video_id"]
                  and rows[0]["_repair_clip_link"] is True)
    if not rows:
        failures.append("missing_candidate_link_must_require_and_derive_from_exact_source_evidence")

    second_clip = {**missing_link, "clip_candidate_id": "clip-second-range", "start_seconds": 12,
                   "end_seconds": 24}
    rows, counters = plan(parts, clips_override=[missing_link, second_clip])
    passed += int(len(rows) == 2 and counters["repairable"] == 2
                  and len({row["source_video_id"] for row in rows}) == 1
                  and all(row["_repair_clip_link"] for row in rows))
    if len(rows) != 2:
        failures.append("multiple_clips_from_same_verified_video_must_share_one_ledger_identity")

    mismatched_video = {**missing_link, "video_id": "different-video"}
    rows, counters = plan(parts, clips_override=[mismatched_video])
    passed += int(not rows and counters["provenance_insufficient"] == 1)
    if rows:
        failures.append("missing_candidate_link_with_wrong_video_id_must_fail_closed")

    _, counters = plan(parts, source_videos_override=[{
        **source_video, "content_hash": "f" * 64,
    }])
    passed += int(counters["repairable"] == 0 and counters["ambiguous"] == 1)
    if counters["repairable"]:
        failures.append("existing_source_video_hash_mismatch_must_fail_closed")

    _, counters = plan(parts, parents_override=[parts[3], dict(parts[3])])
    passed += int(counters["ambiguous"] == 1)
    if counters["ambiguous"] != 1:
        failures.append("ambiguous_parent_must_fail_closed")

    bad_permission = {**parts[6], "revoked": "true"}
    rows, counters = plan(parts, permissions_override=[bad_permission])
    passed += int(not rows and counters["provenance_insufficient"] == 1)
    if rows:
        failures.append("revoked_permission_must_not_repair")

    bad_hash_asset = {**parts[5], "content_hash": "0" * 64}
    rows, _ = plan(parts, asset_override=[bad_hash_asset])
    passed += int(not rows)
    if rows:
        failures.append("asset_hash_mismatch_must_not_repair")

    bad_author = {**parts[3], "author_handle": "another_channel"}
    rows, _ = plan(parts, parents_override=[bad_author])
    passed += int(not rows)
    if rows:
        failures.append("author_mismatch_must_not_repair")

    cross_account = {**parts[1], "account_id": "night_scout"}
    source, _, _, parent, media, asset, permission = parts
    rows, _ = source_video_lineage_repairs(
        clips=[cross_account], source_videos=[], source_posts=[parent],
        source_post_media=[media], media_assets=[asset], media_permissions=[permission],
        registered_sources=[source], account_id="liver_manager",
    )
    passed += int(not rows)
    if rows:
        failures.append("cross_account_clip_must_not_repair")

    source, clip, _source_video, parent, media, asset, permission = parts
    client = SheetClient({
        "source_videos": [], "video_clip_candidates": [clip],
        "source_posts": [parent], "source_post_media": [media],
        "media_assets": [asset], "media_permissions": [permission],
    })
    applied = repair_missing_source_video_lineage(client, account_id="liver_manager")
    saved = client._ws("source_videos").get_all_records()
    passed += int(applied["repaired_count"] == 1 and len(saved) == 1
                  and saved[0]["source_video_id"] == clip["source_video_id"])
    if applied["repaired_count"] != 1 or len(saved) != 1:
        failures.append("repair_apply_must_read_back_exactly_once")
    repeated = repair_missing_source_video_lineage(client, account_id="liver_manager")
    passed += int(repeated["repaired_count"] == 0 and len(client._ws("source_videos").rows) == 1)
    if repeated["repaired_count"] or len(client._ws("source_videos").rows) != 1:
        failures.append("repair_rerun_must_be_idempotent")

    missing_link_clip = {**clip, "source_video_id": ""}
    client = SheetClient({
        "source_videos": [], "video_clip_candidates": [missing_link_clip],
        "source_posts": [parent], "source_post_media": [media],
        "media_assets": [asset], "media_permissions": [permission],
    })
    from unittest.mock import patch

    def update_candidate(client_arg, logical, key, key_value, fields):
        rows = client_arg._ws(logical).rows
        matches = [row for row in rows if row.get(key) == key_value]
        if len(matches) != 1:
            return False
        matches[0].update(fields)
        return True

    with patch("process_threads_queue.update_row", side_effect=update_candidate):
        applied = repair_missing_source_video_lineage(client, account_id="liver_manager")
    saved_clips = client._ws("video_clip_candidates").get_all_records()
    passed += int(
        applied["repaired_count"] == 1
        and applied["linked_clip_candidate_ids"] == [clip["clip_candidate_id"]]
        and len(client._ws("source_videos").rows) == 1
        and saved_clips[0]["source_video_id"] == source_video["source_video_id"]
    )
    if not applied.get("linked_clip_candidate_ids"):
        failures.append("exact_missing_clip_link_must_read_after_write")

    second_missing_link_clip = {
        **missing_link_clip, "clip_candidate_id": "clip-second-range", "start_seconds": 12,
        "end_seconds": 24,
    }
    client = SheetClient({
        "source_videos": [], "video_clip_candidates": [missing_link_clip, second_missing_link_clip],
        "source_posts": [parent], "source_post_media": [media],
        "media_assets": [asset], "media_permissions": [permission],
    })
    with patch("process_threads_queue.update_row", side_effect=update_candidate):
        applied = repair_missing_source_video_lineage(client, account_id="liver_manager")
    saved_clips = client._ws("video_clip_candidates").get_all_records()
    passed += int(
        applied["repaired_count"] == 1
        and len(applied["linked_clip_candidate_ids"]) == 2
        and len(client._ws("source_videos").rows) == 1
        and all(row["source_video_id"] == source_video["source_video_id"] for row in saved_clips)
    )
    if len(applied.get("linked_clip_candidate_ids", [])) != 2:
        failures.append("multiple_verified_clips_must_link_to_single_read_back_ledger_row")

    print(f"PASS: {passed} / FAIL: {len(failures)}")
    for failure in failures:
        print(f"FAIL {failure}")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(run())
