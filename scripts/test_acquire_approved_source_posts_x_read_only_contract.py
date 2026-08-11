#!/usr/bin/env python3
from types import SimpleNamespace

import acquire_approved_source_posts as acquisition
from acquisition.models import NormalizedSourcePost
from acquisition.router import BackendRoute

source = {
    "source_id": "src_lm_x_contract",
    "source_platform": "x",
    "source_url": "https://x.com/meg_lsm",
    "source_handle": "@meg_lsm",
    "target_account_ids": ["liver_manager"],
    "active": True,
    "fetch_enabled": True,
    "x_read_only": True,
}
post = NormalizedSourcePost(
    source_post_id="sp_src_lm_x_contract_123",
    source_id=source["source_id"],
    target_account_id="liver_manager",
    platform="x",
    profile_url="https://x.com/meg_lsm",
    canonical_post_url="https://x.com/meg_lsm/status/123",
    external_post_id="123",
    original_post_text="配信で続けやすい型を作る",
    published_at="2026-08-11T00:00:00+00:00",
    author_handle="meg_lsm",
    collection_backend="x_gallery_dl",
)


class FakeRouter:
    routes = {"x.profile_posts": BackendRoute("x.profile_posts", "x_gallery_dl")}

    def route(self, capability, routed_source, *, limit, shadow=False):
        assert capability == "x.profile_posts"
        assert routed_source["x_read_only"] is True
        assert limit <= 30
        return SimpleNamespace(
            backend_name="x_gallery_dl",
            posts=[post],
            fallback_used=False,
        )


original_selected = acquisition.selected_sources
original_router = acquisition.build_router
original_config = acquisition.get_config
try:
    acquisition.selected_sources = lambda *args, **kwargs: ([source], [])
    acquisition.build_router = lambda: FakeRouter()
    acquisition.get_config = lambda: (_ for _ in ()).throw(AssertionError("Sheets config must not load"))
    result = acquisition.run(
        "liver_manager",
        "x",
        5,
        apply=False,
        shadow=False,
        reference_only=True,
        verify_network=True,
    )
finally:
    acquisition.selected_sources = original_selected
    acquisition.build_router = original_router
    acquisition.get_config = original_config

assert result["status"] == "PASS", result
assert result["network_fetch"] is True
assert result["discovered_post_count"] == 1
assert result["would_save_source_posts"] is False
assert result["source_results"][0]["selected_backend"] == "x_gallery_dl"
print("PASS test_acquire_approved_source_posts_x_read_only_contract.py")
