#!/usr/bin/env python3
"""An unsupported historical window must not silently return newest posts."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from acquisition.threads_cli import ThreadsCliPublicAdapter, ThreadsLoggedOutGraphQLAdapter  # noqa: E402
from acquisition.router import AdapterRouter, BackendFailure, BackendRoute  # noqa: E402


SOURCE = {"source_id": "test", "source_url": "https://www.threads.com/@target",
          "platform": "threads", "target_account_ids": ["night_scout"]}


class PublicBackfillTests(unittest.TestCase):
    def test_cli_respects_position_without_increasing_five_post_bound(self):
        rows = [{"id": str(i), "username": "target", "text": "public",
                 "permalink": f"https://www.threads.com/@target/post/ABC{i}"} for i in range(1, 6)]
        runner = Mock(return_value=(0, json.dumps(rows), ""))
        adapter = ThreadsCliPublicAdapter(runner=runner, binary_path="/test/th")
        posts = adapter.acquire({**SOURCE, "_discovery_start_position": 3}, limit=30)
        self.assertEqual([p.external_post_id for p in posts], ["3", "4", "5"])
        self.assertEqual(runner.call_args.args[0][-4:], ["-n", "5", "-o", "json"])

    def test_unsupported_history_does_not_fetch_first_page(self):
        runner, loader, poster = Mock(), Mock(), Mock()
        adapters = [ThreadsCliPublicAdapter(runner=runner),
                    ThreadsLoggedOutGraphQLAdapter(profile_loader=loader, json_poster=poster)]
        for adapter in adapters:
            with self.assertRaisesRegex(BackendFailure, "history_window_unsupported"):
                adapter.acquire({**SOURCE, "_discovery_start_position": 94}, limit=30)
        runner.assert_not_called()
        loader.assert_not_called()
        poster.assert_not_called()

    def test_graphql_respects_window_instead_of_returning_first_posts(self):
        nodes = [{"thread_items": [{"post": {"pk": str(i), "code": f"ABC{i}",
                  "user": {"username": "target"}, "caption": {"text": "public"}}}]} for i in range(1, 7)]
        adapter = ThreadsLoggedOutGraphQLAdapter(
            profile_loader=lambda _: {"id": "123", "username": "target"},
            json_poster=lambda *_: {"data": nodes})
        posts = adapter.acquire({**SOURCE, "_discovery_start_position": 4}, limit=30)
        self.assertEqual([p.external_post_id for p in posts], ["4", "5"])

    def test_history_reaches_existing_public_browser_fallback(self):
        source = {**SOURCE, "_discovery_start_position": 94}
        browser = Mock()
        browser.acquire.return_value = ["historical-result"]
        del browser.discover_profile
        router = AdapterRouter({
            "cli": ThreadsCliPublicAdapter(runner=Mock()),
            "graphql": ThreadsLoggedOutGraphQLAdapter(profile_loader=Mock()), "browser": browser,
        }, {"threads.profile_posts": BackendRoute("threads.profile_posts", "cli", ("graphql", "browser"))})
        result = router.route("threads.profile_posts", source, limit=30)
        self.assertTrue(result.fallback_used)
        self.assertEqual(result.backend_name, "browser")
        self.assertEqual(result.posts, ["historical-result"])
        browser.acquire.assert_called_once_with(source, limit=30)


if __name__ == "__main__":
    unittest.main()
