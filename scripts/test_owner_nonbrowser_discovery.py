#!/usr/bin/env python3
"""Current owner routes and direct adapter calls never enter a browser."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from acquisition.capability_registry import CapabilityRegistry
from acquisition.factory import build_router, load_routing_config
from acquisition.router import BackendFailure
from acquisition.threads_public import (
    ThreadsBrowserSessionAdapter, ThreadsPublicHttpAdapter,
    ThreadsPublicProfileAdapter, ThreadsPublicScreenAdapter,
)
from acquisition.tiktok_public import TikTokPublicProfileAdapter


def source(**scope):
    return {"source_id": "fixture", "source_platform": "threads",
            "source_url": "https://www.threads.com/@sample", **scope}


class OwnerNonbrowserTests(unittest.TestCase):
    def test_current_routes_have_no_browser_or_authenticated_backend(self):
        registry = CapabilityRegistry.load()
        config = load_routing_config()
        for capability in ("threads.profile_posts", "tiktok.profile_posts"):
            route = config["routes"][capability]
            for name in [route["primary"], *route["fallbacks"], *route["shadow"]]:
                with self.subTest(backend=name):
                    self.assertFalse(registry.get(name).requires_browser)
                    self.assertFalse(registry.get(name).requires_auth)
        self.assertEqual(config["routes"]["threads.profile_posts"]["fallbacks"],
                         ["threads_logged_out_graphql", "threads_public_http"])
        self.assertFalse(registry.get("threads_public_screen").production_selectable)
        self.assertTrue(registry.get("threads_public_http").production_selectable)

    def test_registered_owner_sources_have_no_browser_fallback(self):
        rows = json.loads((ROOT / "config/source_accounts/default_sources.json").read_text())["sources"]
        checked = 0
        for row in rows:
            targets = row.get("target_account_ids") or [row.get("target_account_id")]
            if row.get("source_platform") == "threads" and set(targets) & {"night_scout", "liver_manager"}:
                self.assertNotIn("threads_public_screen", row.get("fallback", []))
                if row.get("collection_method") == "threads_cli_public":
                    self.assertIn("threads_public_http", row.get("fallback", []))
                    checked += 1
        self.assertGreaterEqual(checked, 9)

    def test_direct_browser_entrypoints_stop_before_any_loader(self):
        calls = []
        def forbidden(*args, **kwargs):
            calls.append(True)
            raise AssertionError("browser/session loader must not run")
        adapters = [ThreadsPublicProfileAdapter(html_loader=forbidden),
                    ThreadsPublicScreenAdapter(html_loader=forbidden, href_loader=forbidden),
                    ThreadsBrowserSessionAdapter(render_loader=forbidden),
                    TikTokPublicProfileAdapter(html_loader=forbidden)]
        scopes = [{"target_account_ids": [account]} for account in ("night_scout", "liver_manager")]
        scopes += [{"target_account_ids": ["legacy_fixture", "liver_manager"]},
                   {"target_account_ids": ["legacy_fixture"], "target_account_id": "night_scout"},
                   {"target_account_ids": ["legacy_fixture"], "account_id": "liver_manager"},
                   {"target_account_id": " NIGHT_SCOUT "}, {"account_id": "liver_manager"},
                   {}, {"target_account_ids": "night_scout"}, {"target_account_ids": [None]},
                   {"target_account_ids": ["all"]}]
        for scope in scopes:
            for adapter in adapters:
                with self.subTest(scope=scope, adapter=adapter.backend_name):
                    with self.assertRaisesRegex(BackendFailure, "owner_nonbrowser|browser_scope"):
                        adapter.acquire(source(**scope), limit=1)
                    result = adapter.discover_profile(source(**scope), limit=1)
                    self.assertFalse(result.ok)
                    if isinstance(adapter, ThreadsPublicProfileAdapter):
                        with self.assertRaisesRegex(BackendFailure, "owner_nonbrowser|browser_scope"):
                            adapter.acquire_post(source(**scope), "https://www.threads.com/@sample/post/one")
        self.assertEqual(calls, [])

    def test_http_discovery_and_exact_post_remain_available_for_both_owners(self):
        calls = []
        def load(url):
            calls.append(url)
            if "/post/" not in url:
                return '<a href="/@other/post/ignored"></a><a href="/@sample/post/one"></a>'
            return '<meta property="og:description" content="配信の準備についての公開投稿">'
        adapter = ThreadsPublicHttpAdapter(html_loader=load)
        for account in ("night_scout", "liver_manager"):
            row = source(target_account_ids=[account])
            posts = adapter.acquire(row, limit=1)
            self.assertEqual(len(posts), 1)
            self.assertEqual(posts[0].target_account_id, account)
            self.assertEqual(posts[0].external_post_id, "one")
            self.assertEqual(posts[0].media_count, 0)
            with self.assertRaisesRegex(BackendFailure, "author_mismatch"):
                adapter.acquire_post(row, "https://www.threads.com/@other/post/two")
        self.assertEqual(len(calls), 4)

    def test_cli_and_graphql_failure_reaches_http_without_browser(self):
        calls = []
        class Unavailable:
            def acquire(self, row, *, limit):
                calls.append("unavailable")
                raise BackendFailure("no_public_posts")
        router = build_router()
        router.adapters["threads_cli_public"] = Unavailable()
        router.adapters["threads_logged_out_graphql"] = Unavailable()
        router.adapters["threads_public_http"] = ThreadsPublicHttpAdapter(
            html_loader=lambda url: ('<a href="/@sample/post/one"></a>' if "/post/" not in url
                                    else '<meta property="og:description" content="公開本文">'))
        result = router.route("threads.profile_posts", source(target_account_ids=["liver_manager"]), limit=1)
        self.assertEqual(result.backend_name, "threads_public_http")
        self.assertTrue(result.fallback_used)
        self.assertEqual(len(result.posts), 1)
        self.assertEqual(calls, ["unavailable", "unavailable"])

    def test_browser_route_override_cannot_bypass_owner_scope(self):
        from acquisition.router import AdapterRouter, BackendRoute
        calls = []
        adapter = ThreadsPublicScreenAdapter(href_loader=lambda *args, **kwargs: calls.append(True))
        router = AdapterRouter({adapter.backend_name: adapter}, {
            "threads.profile_posts": BackendRoute("threads.profile_posts", adapter.backend_name)})
        with self.assertRaisesRegex(BackendFailure, "owner_nonbrowser_discovery_required"):
            router.route("threads.profile_posts", source(target_account_ids=["night_scout"]), limit=1)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
