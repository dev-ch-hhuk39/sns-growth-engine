#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]

sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "src"),
]

import acquire_approved_source_posts as a  # noqa: E402
from acquisition.models import (  # noqa: E402
    NormalizedMediaItem,
    NormalizedSourcePost,
)


SOURCE = {
    "source_id": "src_post_policy",
    "source_platform": "threads",
    "source_url": ("https://www.threads.com/" "@sample"),
    "target_account_ids": ["night_scout"],
    "active": True,
}


CONFIG = {
    "source_post_discovery_state_enabled": True,
    "initial_source_scan_limit": 30,
    "incremental_source_scan_limit": 12,
    "backfill_source_scan_limit": 30,
    "consecutive_existing_stop": 5,
    "backfill_overlap_items": 3,
    "min_unprocessed_source_inventory_per_account": 3,
    "max_new_videos_per_source_per_run": 3,
    "max_total_new_videos_per_run": 12,
}


def post(number: int) -> NormalizedSourcePost:
    external = f"post{number}"

    canonical = "https://www.threads.com/" f"@sample/post/{external}"

    source_post_id = f"sp_src_post_policy_{external}"

    media = NormalizedMediaItem(
        source_post_media_id=(f"spm_{source_post_id}_0"),
        source_post_id=source_post_id,
        media_index=0,
        media_type="image",
        canonical_post_url=canonical,
        original_media_url=("https://cdn.example/" f"{external}.jpg"),
        resolver_backend="test",
    )

    return NormalizedSourcePost(
        source_post_id=source_post_id,
        source_id="src_post_policy",
        target_account_id="night_scout",
        platform="threads",
        profile_url=SOURCE["source_url"],
        canonical_post_url=canonical,
        external_post_id=external,
        original_post_text=external,
        published_at=(f"202608{number:02d}"),
        media_items=(media,),
        collection_backend="test",
        backend_version="test",
        content_hash=external,
        discovered_at=("2026-08-01T00:00:00+00:00"),
    )


class FakeRouter:
    def __init__(
        self,
        returned_posts,
    ):
        self.returned_posts = returned_posts

        self.calls = []

        self.adapters = {"fake": SimpleNamespace(backend_version="test")}

        self.routes = {
            a.capability_for("threads"): SimpleNamespace(
                primary="fake",
                fallbacks=(),
            )
        }

    def route(
        self,
        capability,
        source,
        *,
        limit,
        shadow=False,
    ):
        self.calls.append(
            {
                "capability": capability,
                "start_position": (source.get("_discovery_start_position")),
                "mode": source.get("_discovery_mode"),
                "limit": limit,
                "shadow": shadow,
            }
        )

        return SimpleNamespace(
            backend_name="fake",
            posts=list(self.returned_posts),
            attempted_backends=["fake"],
            fallback_used=False,
            shadow_results={},
        )


class FakeClient:
    pass


originals = {
    "selected_sources": a.selected_sources,
    "get_config": a.get_config,
    "SheetsClient": a.SheetsClient,
    "build_router": a.build_router,
    "build_provider_registry": (a.build_provider_registry),
    "ledger_permission": (a.ledger_permission),
    "enrich_posts": a.enrich_posts,
    "load_discovery_config": (a.load_discovery_config),
    "load_post_discovery_data": (a.load_post_discovery_data),
    "persist": a.persist,
    "persist_auxiliary": (a.persist_auxiliary),
    "persist_observability": (a.persist_observability),
    "append_discovery_state_to_sheets": (a.append_discovery_state_to_sheets),
}


captured_posts = []
captured_states = []


def fake_persist(
    client,
    posts,
    policy_by_source=None,
):
    captured_posts[:] = posts

    return {
        "saved_source_posts": len(posts),
        "saved_source_post_media": sum(item.media_count for item in posts),
        "duplicate_source_posts": 0,
        "invalid_source_posts": 0,
    }


def fake_state_append(
    client,
    rows,
):
    captured_states[:] = rows
    return len(rows)


def apply_common(
    router,
    discovery_data,
):
    a.selected_sources = lambda account_id, platform, **_kwargs: (
        [SOURCE],
        [],
    )

    a.get_config = lambda: {
        "sheet_id": "test",
        "sa_dict": {},
    }

    a.SheetsClient = lambda *args, **kwargs: FakeClient()

    a.build_router = lambda: router
    a.build_provider_registry = lambda: {}

    a.ledger_permission = lambda client, source_id, *, account_id="", source_handle="": {
        "rights_status": ("approved_creator_clip"),
        "permission_status": ("approved"),
    }

    a.enrich_posts = lambda source, posts, permission, providers: (
        list(posts),
        [],
        [],
        [],
    )

    a.load_discovery_config = lambda: dict(CONFIG)

    a.load_post_discovery_data = lambda client: discovery_data

    a.persist = fake_persist

    a.persist_auxiliary = lambda *args, **kwargs: 0

    a.persist_observability = lambda *args, **kwargs: None

    a.append_discovery_state_to_sheets = fake_state_append


try:
    incremental_existing = a.normalize_existing_source_posts(
        [
            {
                "source_post_id": (post(number).source_post_id),
                "source_id": ("src_post_policy"),
                "target_account_id": ("night_scout"),
                "external_post_id": (post(number).external_post_id),
                "canonical_post_url": (post(number).canonical_post_url),
                "processing_status": ("PENDING"),
            }
            for number in range(
                1,
                6,
            )
        ]
    )

    incremental_router = FakeRouter(
        [
            post(number)
            for number in range(
                1,
                7,
            )
        ]
    )

    apply_common(
        incremental_router,
        (
            incremental_existing,
            [],
        ),
    )

    incremental_result = a.run(
        "night_scout",
        "threads",
        30,
        apply=True,
        shadow=False,
    )

    incremental_source = incremental_result["source_results"][0]

    assert incremental_router.calls[0]["start_position"] == 1

    assert incremental_router.calls[0]["limit"] == 12

    assert incremental_source["scan_mode"] == "incremental"

    assert incremental_source["duplicate_post_count"] == 5

    assert incremental_source["stop_reason"] == "consecutive_existing_stop"

    assert incremental_source["post_count"] == 0

    assert captured_posts == []

    assert captured_states[0]["item_type"] == "post"

    assert captured_states[0]["last_new_count"] == 0

    backfill_existing = a.normalize_existing_source_posts(
        [
            {
                "source_post_id": (post(number).source_post_id),
                "source_id": ("src_post_policy"),
                "target_account_id": ("night_scout"),
                "external_post_id": (post(number).external_post_id),
                "canonical_post_url": (post(number).canonical_post_url),
                "processing_status": ("COMPLETE"),
            }
            for number in range(
                1,
                11,
            )
        ]
    )

    backfill_state = [
        {
            "state_id": ("src_post_policy:" "night_scout:post"),
            "source_id": ("src_post_policy"),
            "account_id": ("night_scout"),
            "item_type": "post",
            "backfill_cursor": 8,
            "updated_at": ("2026-08-01T00:00:00+00:00"),
        }
    ]

    backfill_router = FakeRouter(
        [
            post(number)
            for number in range(
                8,
                14,
            )
        ]
    )

    apply_common(
        backfill_router,
        (
            backfill_existing,
            backfill_state,
        ),
    )

    backfill_result = a.run(
        "night_scout",
        "threads",
        30,
        apply=True,
        shadow=False,
    )

    backfill_source = backfill_result["source_results"][0]

    assert backfill_router.calls[0]["start_position"] == 8

    assert backfill_router.calls[0]["limit"] == 30

    assert backfill_source["scan_mode"] == "backfill"

    assert backfill_source["duplicate_post_count"] == 3

    assert backfill_source["post_count"] == 3

    assert [item.external_post_id for item in captured_posts] == [
        "post11",
        "post12",
        "post13",
    ]

    assert captured_states[0]["backfill_cursor"] == 11

    assert captured_states[0]["last_new_count"] == 3

finally:
    for name, value in originals.items():
        setattr(
            a,
            name,
            value,
        )


print("PASS " "test_post_acquisition_uses_" "incremental_policy.py")
