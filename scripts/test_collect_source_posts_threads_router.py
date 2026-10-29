#!/usr/bin/env python3
"""Threads profile discovery reaches the real collector CLI without writes."""
from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import collect_source_posts as collector  # noqa: E402
from acquisition.models import NormalizedSourcePost  # noqa: E402
from acquisition.router import RouteResult  # noqa: E402


class _Router:
    def __init__(self, account_id="night_scout", author_handle="actual_author"):
        self.account_id = account_id
        self.author_handle = author_handle
        self.calls = []

    def route(self, capability, source, *, limit):
        assert capability == "threads.profile_posts"
        assert limit == 2
        assert source["target_account_ids"] == [self.account_id]
        self.calls.append(source["source_id"])
        return RouteResult(
            backend_name="threads_cli_public",
            posts=[NormalizedSourcePost(
                source_post_id="sp_src_abc",
                source_id="src",
                target_account_id=self.account_id,
                platform="threads",
                profile_url=source["source_url"],
                canonical_post_url="https://www.threads.com/@actual_author/post/abc",
                external_post_id="abc",
                original_post_text="公開投稿の本文",
                author_handle=self.author_handle,
                published_at="2026-08-17T00:00:00Z",
            )],
        )


def source(account_id="night_scout"):
    return {
        "source_id": "src_" + account_id,
        "source_url": "https://www.threads.com/@registered_profile",
        "source_platform": "threads", "target_account_ids": [account_id],
        "handle": "registered_profile", "fetch_enabled": True, "manual_only": False,
    }


class ThreadsProfileCollectorTests(unittest.TestCase):
    def run_cli(self, router, *, account_id="night_scout", fetch_real=True):
        argv = ["collect_source_posts.py", "--platform", "threads", "--account-id",
                account_id, "--limit", "2", "--dry-run"]
        if fetch_real:
            argv.append("--fetch-real")
        other = "liver_manager" if account_id == "night_scout" else "night_scout"
        out = io.StringIO()
        with patch("acquisition.factory.build_router", return_value=router) as build, \
                patch.object(collector, "load_sources_from_file", return_value=[source(account_id), source(other)]), \
                patch.object(collector, "adapter_status", return_value={}), \
                patch.object(collector, "fetch_threads_post", side_effect=AssertionError("profile must use router")), \
                patch.object(collector, "_append_many", side_effect=AssertionError("dry run cannot write")), \
                patch.object(collector, "_append_source_post_bundles", side_effect=AssertionError("dry run cannot write")), \
                patch.object(collector.urllib.request, "urlopen", side_effect=AssertionError("offline test")), \
                patch.object(sys, "argv", argv), redirect_stdout(out):
            self.assertEqual(collector.main(), 0)
        return json.loads(out.getvalue()), build.call_count

    def test_shared_router_preserves_existing_contract_and_actual_author(self):
        router = _Router()
        with patch("acquisition.factory.build_router", return_value=router):
            result = collector.fetch_threads_account_posts(source(), limit=2)
        self.assertEqual(result["status"], "FETCHED")
        self.assertTrue(result["rows"][0]["post_url"].endswith("/post/abc"))
        self.assertEqual(result["backend"], "threads_cli_public")
        self.assertFalse(result["fallback_used"])
        self.assertEqual(result["rows"][0]["author_handle"], "actual_author")

    def test_actual_cli_profile_branch_preserves_both_accounts_and_author(self):
        for account in ("night_scout", "liver_manager"):
            with self.subTest(account=account):
                router = _Router(account)
                plan, build_calls = self.run_cli(router, account_id=account)
                self.assertEqual(build_calls, 1)
                self.assertEqual(router.calls, ["src_" + account])
                self.assertEqual(plan["status"], "PLAN_ONLY")
                self.assertEqual(plan["selected_count"], 1)
                self.assertFalse(plan["media_download"])
                self.assertTrue(plan["real_fetch"])
                self.assertEqual(len(plan["rows"]), 1)
                row = plan["rows"][0]
                self.assertEqual(row["account_id"], account)
                self.assertEqual(row["source_id"], "src_" + account)
                self.assertEqual(row["source_handle"], "actual_author")
                self.assertEqual(row["post_url"], "https://www.threads.com/@actual_author/post/abc")
                self.assertEqual(row["external_post_id"], "abc")
                self.assertEqual(row["post_text"], "公開投稿の本文")
                self.assertEqual(row["published_at"], "2026-08-17T00:00:00Z")
                self.assertEqual(row["use_status"], "REFERENCE_ONLY")
                self.assertEqual(row["can_reuse_media"], "false")
                self.assertEqual(row["media_body_saved"], "false")
                parent, children = collector.source_post_bundle(row)
                self.assertEqual(parent["author_handle"], "actual_author")
                self.assertEqual(parent["source_id"], "src_" + account)
                self.assertEqual(parent["target_account_id"], account)
                self.assertEqual(parent["canonical_post_url"], row["post_url"])
                self.assertEqual(children, [])

    def test_missing_provider_author_is_not_registered_owner_evidence(self):
        plan, _ = self.run_cli(_Router(author_handle=""))
        self.assertEqual(plan["rows"][0]["source_handle"], "")
        self.assertNotEqual(plan["rows"][0]["source_handle"], source()["handle"])
        parent, _ = collector.source_post_bundle(plan["rows"][0])
        self.assertEqual(parent["author_handle"], "")

    def test_legacy_normalization_fallback_only_when_author_field_is_absent(self):
        self.assertEqual(collector.normalize_source(source(), {})["source_handle"], "registered_profile")
        self.assertEqual(collector.normalize_source(source(), {"author_handle": ""})["source_handle"], "")

    def test_plan_without_fetch_real_does_not_invoke_router(self):
        router = _Router()
        plan, build_calls = self.run_cli(router, fetch_real=False)
        self.assertEqual(build_calls, 0)
        self.assertEqual(router.calls, [])
        self.assertEqual(plan["rows"], [])
        self.assertTrue(any(row["reason"] == "fetch_real_required" for row in plan["skipped"]))

    def test_provider_failure_remains_deferred_without_rows_or_writes(self):
        class FailingRouter:
            def route(self, *_args, **_kwargs):
                raise RuntimeError("offline_provider_unavailable")

        plan, _ = self.run_cli(FailingRouter())
        self.assertEqual(plan["rows"], [])
        self.assertTrue(any("offline_provider_unavailable" in row["reason"] for row in plan["skipped"]))
        self.assertFalse(plan["media_download"])


if __name__ == "__main__":
    unittest.main()
