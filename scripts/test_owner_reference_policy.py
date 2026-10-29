#!/usr/bin/env python3
"""Current owner policy applies before source bounds and physical side effects."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import acquire_approved_source_posts as acquisition
import collect_source_posts as collector
import evaluate_reference_first_completion as completion
import ingest_direct_reference_media as ingest
import ingest_direct_reference_media_reliable as reliable
import run_direct_reference_media_pipeline as direct
import verify_physical_media_goldens as golden
import run_media_production_pipeline as clips_pipeline
import test_reference_first_content_router as router_fixture
from generation import media_platform_policy as policy
from generation import video_source_acquirer as video

ACCOUNTS = ("night_scout", "liver_manager")
ORDER = ("tiktok", "threads", "x", "youtube")
URLS = {
    "tiktok": "https://www.tiktok.com/@owner/video/123",
    "threads": "https://www.threads.com/@owner/post/ABC123",
    "x": "https://x.com/owner/status/123",
    "youtube": "https://www.youtube.com/watch?v=abcdefghijk",
}


def sources(account):
    return [{"source_id": f"{account}_{p}", "source_platform": p,
             "target_account_id": account, "target_account_ids": [account],
             "source_url": URLS[p], "active": True, "fetch_enabled": True,
             "x_read_only": True, "media_usage_mode": "direct_and_clip"}
            for p in reversed(ORDER)]


def authorized(platform, account):
    candidate = {"source_id": "s", "source_handle": "owner", "source_platform": platform,
                 "source_url": URLS[platform], "rights_status": "approved_creator_clip",
                 "permission_status": "approved"}
    ledger = {"source_id": "s", "source_handle": "owner", "account_id": account,
              "allowed_accounts": [account], "rights_status": "approved_creator_clip",
              "permission_status": "approved", "usage_mode": "direct_and_clip",
              "allow_download": True, "allow_cut": True,
              "evidence_type": "owner_attestation", "evidence_reference": "offline-fixture",
              "approved_by": "fixture", "approved_at": "2026-10-29T00:00:00+09:00",
              "revoked": False}
    return candidate, [ledger]


def bundle(platform, account):
    post = {"source_post_id": "p", "source_id": "s", "target_account_id": account,
            "platform": platform, "canonical_post_url": URLS[platform],
            "original_post_text": "配信で初見の人に挨拶するときは、今話していることを一言添えて、コメントしやすい入口を作る。"}
    media = {"source_post_media_id": "m", "source_post_id": "p", "media_index": "0",
             "media_type": "video", "canonical_post_url": URLS[platform],
             "original_media_url": URLS[platform], "download_status": "PENDING",
             "cloudinary_status": "PENDING"}
    return post, media


class Client:
    def __init__(self, post, media):
        self.rows = {"source_posts": [post], "source_post_media": [media]}

    def _ws(self, logical):
        return SimpleNamespace(get_all_records=lambda: self.rows.get(logical, []))

    def _ensure_tab(self, logical, _headers):
        return self._ws(logical)

    def _call_with_rate_limit_retry(self, _label, callback):
        return callback()


class OwnerPolicyTests(unittest.TestCase):
    def test_reference_order_and_scoped_config_are_consistent(self):
        self.assertEqual(policy.REFERENCE_PLATFORMS, ORDER)
        self.assertEqual(sorted(ORDER, key=lambda p: -policy.reference_priority_score(p)), list(ORDER))
        cfg = json.loads((ROOT / "config/media_growth_engine.json").read_text())
        for account in ACCOUNTS:
            self.assertEqual(cfg["physical_media_source_platforms_by_account"][account], ["x", "youtube"])
            self.assertEqual(cfg["deferred_physical_media_source_platforms_by_account"][account], ["tiktok", "threads"])

    def test_real_source_selectors_sort_before_caller_bounds(self):
        for account in ACCOUNTS:
            rows = sources(account)
            before = deepcopy(rows)
            with self.subTest(account=account), patch.object(acquisition, "load_registry", return_value=rows):
                picked, _ = acquisition.selected_sources(account, "all", reference_only=True)
            self.assertEqual([s["source_platform"] for s in picked], list(ORDER))
            self.assertEqual(picked[:1][0]["source_platform"], "tiktok")
            picked, _ = collector.select_sources(rows, account_id=account, platform="all", include_x=True)
            self.assertEqual([s["source_platform"] for s in picked], list(ORDER))
            self.assertEqual(rows, before)

    def test_all_account_order_preserves_other_account_slots_and_same_platform_order(self):
        rows = sources("night_scout")[:2] + sources("beauty_account")[:1] + sources("night_scout")[2:]
        ordered = policy.order_reference_sources(rows, account_id="all")
        self.assertIs(ordered[2], rows[2])
        self.assertEqual([r["source_platform"] for r in ordered if r["target_account_id"] == "night_scout"], list(ORDER))
        duplicates = [sources("night_scout")[0], {**sources("night_scout")[0], "source_id": "second"}]
        self.assertEqual(policy.order_reference_sources(duplicates, account_id="night_scout"), duplicates)
        self.assertEqual(policy.order_reference_sources(rows, account_id="beauty_account"), rows)

    def test_owner_physical_policy_blocks_deferred_platforms_without_revoking_legacy_capability(self):
        for account in ACCOUNTS:
            for platform in ORDER:
                with self.subTest(account=account, platform=platform):
                    allowed = platform in {"x", "youtube"}
                    self.assertEqual(policy.can_attempt_physical_media(platform, account_id=account), allowed)
                    self.assertEqual(policy.can_attempt_physical_media("", URLS[platform], account_id=account), allowed)
                    self.assertEqual(policy.physical_media_provider(platform, account_id=account), "yt_dlp" if allowed else "")
        self.assertTrue(policy.can_attempt_physical_media("threads"))
        self.assertTrue(policy.can_attempt_physical_media("tiktok", account_id="beauty_account"))

    def test_real_permission_does_not_override_deferred_platform_or_cache(self):
        for account in ACCOUNTS:
            for platform in ("threads", "tiktok"):
                candidate, ledger = authorized(platform, account)
                self.assertTrue(video.is_download_authorized(candidate, ledger, account_id=account))
                with self.subTest(account=account, platform=platform), \
                        patch.object(video, "find_cached_source", return_value=Path("existing.mp4")) as cached, \
                        patch("subprocess.run", side_effect=AssertionError("no subprocess")):
                    with self.assertRaisesRegex(RuntimeError, "physical_media_platform_deferred"):
                        video.acquire_authorized_public_source(candidate, {}, cache_root="/unused", account_id=account,
                            source_video_id="v", permission_rows=ledger)
                    cached.assert_not_called()

    def test_x_and_youtube_cache_stays_supported_with_source_specific_x_author(self):
        for account in ACCOUNTS:
            for platform in ("x", "youtube"):
                candidate, ledger = authorized(platform, account)
                path = Path("approved-cache.mp4")
                with self.subTest(account=account, platform=platform), \
                        patch.object(video, "find_cached_source", return_value=path):
                    self.assertEqual(video.acquire_authorized_public_source(candidate, {},
                        cache_root="/unused", account_id=account, source_video_id="v", permission_rows=ledger,
                        registered_source={"source_handle": "owner"}), path)

    def test_cached_x_cannot_bypass_registered_author_binding(self):
        candidate, ledger = authorized("x", "liver_manager")
        with patch.object(video, "find_cached_source", return_value=Path("cache.mp4")) as cache:
            with self.assertRaisesRegex(PermissionError, "x_status_author_does_not_match"):
                video.acquire_authorized_public_source(candidate, {}, cache_root="/unused",
                    account_id="liver_manager", source_video_id="v", permission_rows=ledger,
                    registered_source={"source_handle": "other_author"})
            cache.assert_not_called()

    def test_actual_download_dispatch_refuses_before_any_network(self):
        for account in ACCOUNTS:
            for platform in ("threads", "tiktok"):
                with self.subTest(account=account, platform=platform), \
                        patch.object(ingest, "download_direct_https_media", side_effect=AssertionError("no direct HTTP")), \
                        patch.object(ingest, "download_with_ytdlp", side_effect=AssertionError("no downloader")):
                    with self.assertRaisesRegex(RuntimeError, "physical_media_platform_deferred"):
                        ingest.download_source_media(media_url=URLS[platform], canonical_post_url=URLS[platform],
                            path=Path("unused.mp4"), media_type="video", platform=platform, account_id=account)

    def test_explicit_legacy_account_cannot_override_owner_from_parent(self):
        with self.assertRaisesRegex(PermissionError, "physical_media_account_mismatch"):
            ingest.download_source_media(media_url=URLS["tiktok"], canonical_post_url=URLS["tiktok"],
                path=Path("unused.mp4"), media_type="video", platform="tiktok",
                post={"target_account_id": "night_scout"}, account_id="beauty_account")

    def test_ingest_entrypoint_refuses_before_reads_asset_reuse_or_storage(self):
        for account in ACCOUNTS:
            for platform in ("threads", "tiktok"):
                post, media = bundle(platform, account)
                media.update(cloudinary_status="UPLOADED", storage_url="https://cloudinary.example/owned.mp4")
                with self.subTest(account=account, platform=platform), \
                        patch.object(ingest, "record", side_effect=AssertionError("no reads")), \
                        patch.object(ingest, "download_direct_https_media", side_effect=AssertionError("no cache refresh")):
                    result = ingest.ingest_one(None, post, media)
                self.assertEqual(result["status"], "BLOCKED")
                self.assertIn("physical_media_platform_deferred", result["reason"])

    def test_both_pending_selectors_skip_deferred_media_even_with_permission(self):
        for account in ACCOUNTS:
            for platform in ("threads", "tiktok"):
                post, media = bundle(platform, account)
                client = Client(post, media)
                with self.subTest(account=account, platform=platform), \
                        patch.object(ingest, "permission_ok_from_rows", return_value=True):
                    self.assertEqual(ingest.select_pending_media_id(client, account, permissions=[]), "")
                    self.assertEqual(reliable.select_pending_media_id(client, account, permissions=[]), "")

    def test_full_parent_candidate_selector_reports_deferral(self):
        for account in ACCOUNTS:
            for platform in ("threads", "tiktok"):
                post, media = bundle(platform, account)
                client = Client(post, media)
                with self.subTest(account=account, platform=platform), \
                        patch.object(direct, "_source_map", return_value={"s": {}}), \
                        patch.object(direct, "_permission_map", return_value=({}, {})):
                    candidates, reasons = direct.select_direct_candidates(client, account)
                self.assertEqual(candidates, [])
                self.assertTrue(any("physical_media_platform_deferred" in r for r in reasons), reasons)

    def test_physical_golden_cannot_probe_or_generate_for_deferred_platform(self):
        for account in ACCOUNTS:
            for platform in ("threads", "tiktok"):
                with self.subTest(account=account, platform=platform), \
                        patch.object(golden, "evaluate_permission", side_effect=AssertionError("no permission reinterpretation")), \
                        patch.object(golden, "probe_media_streams", side_effect=AssertionError("no media probe")), \
                        patch.object(golden, "generate_production_post", side_effect=AssertionError("no generation")):
                    row = golden.verify_item({"account_id": account, "source_id": "s", "url": URLS[platform]},
                                              Path("unused.mp4"), {}, [])
                self.assertEqual(row["queue_status"], "BLOCKED")
                self.assertFalse(row["publisher_eligible"])
                self.assertEqual(row["actual_video_bytes"], 0)

    def test_declared_platform_cannot_disguise_deferred_canonical_url(self):
        for account in ACCOUNTS:
            for platform in ("threads", "tiktok"):
                self.assertFalse(policy.can_attempt_physical_media("youtube", URLS[platform], account_id=account))
                with TemporaryDirectory() as directory:
                    sentinel = Path(directory) / "existing.mp4"
                    sentinel.write_bytes(b"preserve-existing-file")
                    with patch.object(ingest, "download_with_ytdlp") as downloader:
                        with self.assertRaisesRegex(RuntimeError, "physical_media_platform_deferred"):
                            ingest.download_source_media(media_url=URLS[platform], canonical_post_url=URLS[platform],
                                path=sentinel, media_type="video", platform="youtube", account_id=account)
                        downloader.assert_not_called()
                    self.assertEqual(sentinel.read_bytes(), b"preserve-existing-file")

    def test_mislabeled_parent_cannot_reach_read_or_pending_selection(self):
        for account in ACCOUNTS:
            for platform in ("threads", "tiktok"):
                post, media = bundle(platform, account)
                post["platform"] = "youtube"
                with patch.object(ingest, "record", side_effect=AssertionError("no asset read")):
                    result = ingest.ingest_one(None, post, media)
                self.assertEqual(result["status"], "BLOCKED")
                with patch.object(ingest, "permission_ok_from_rows", return_value=True):
                    self.assertEqual(ingest.select_pending_media_id(Client(post, media), account, permissions=[]), "")
                    self.assertEqual(reliable.select_pending_media_id(Client(post, media), account, permissions=[]), "")

    def test_registered_deferred_source_cannot_be_relabelled_for_cached_clip(self):
        for account in ACCOUNTS:
            candidate, ledger = authorized("youtube", account)
            with patch.object(video, "find_cached_source", return_value=Path("cache.mp4")) as cached:
                with self.assertRaisesRegex(RuntimeError, "physical_media_platform_deferred"):
                    video.acquire_authorized_public_source(candidate, {}, cache_root="/unused",
                        account_id=account, source_video_id="v", permission_rows=ledger,
                        registered_source={"platform": "tiktok", "source_url": URLS["tiktok"]})
                cached.assert_not_called()

    def test_registered_deferred_source_cannot_enter_full_parent_candidates(self):
        for account in ACCOUNTS:
            post, media = bundle("youtube", account)
            with patch.object(direct, "_source_map", return_value={"s": {"platform": "tiktok"}}), \
                    patch.object(direct, "_permission_map", return_value=({}, {})):
                candidates, reasons = direct.select_direct_candidates(Client(post, media), account)
            self.assertEqual(candidates, [])
            self.assertTrue(any("physical_media_platform_deferred" in reason for reason in reasons), reasons)

    def test_physical_source_planning_excludes_deferred_sources_before_scan_budget(self):
        for account in ACCOUNTS:
            rows = [{**row, "x_video_candidate_enabled": True} for row in sources(account)]
            with patch.object(acquisition, "load_registry", return_value=rows), \
                    patch.object(acquisition, "media_usage_mode", return_value="direct_and_clip"):
                picked, blocked = acquisition.selected_sources(account, "all", reference_only=False)
                metadata, _ = acquisition.selected_sources(account, "all", reference_only=True)
            self.assertEqual([row["source_platform"] for row in picked], ["x", "youtube"])
            self.assertEqual([row["source_platform"] for row in metadata], list(ORDER))
            self.assertEqual({row["reason"] for row in blocked},
                             {"physical_media_platform_deferred:tiktok", "physical_media_platform_deferred:threads"})

    def test_ready_clip_candidate_cannot_reopen_deferred_physical_route(self):
        for account in ACCOUNTS:
            for platform in ("threads", "tiktok"):
                clip, source = router_fixture.ClipEvidenceTests.candidate_fixture()
                clip["account_id"] = source["account_id"] = account
                source.update(platform=platform, canonical_video_url=URLS[platform])
                chosen, _, reasons = clips_pipeline.select_candidate([clip], [source], [], account_id=account)
                self.assertIsNone(chosen)
                self.assertTrue(any("physical_media_platform_deferred" in reason for reason in reasons), reasons)

    def test_uploaded_saved_clip_candidate_stays_deferred(self):
        for account in ACCOUNTS:
            for platform in ("threads", "tiktok"):
                clip, source = router_fixture.ClipEvidenceTests.candidate_fixture()
                clip["account_id"] = source["account_id"] = account
                source.update(platform=platform, canonical_video_url=URLS[platform])
                asset = {"media_asset_id": "asset", "clip_candidate_id": clip["clip_candidate_id"],
                         "source_video_id": source["source_video_id"], "account_id": account,
                         "rights_status": "approved_creator_clip", "permission_status": "approved",
                         "upload_status": "UPLOADED", "storage_url": "https://cdn.example.invalid/clip.mp4"}
                chosen, _, _, reasons = clips_pipeline.select_saved_media_candidate([clip], [source], [asset], [], account)
                self.assertIsNone(chosen)
                self.assertTrue(any("physical_media_platform_deferred" in reason for reason in reasons), reasons)

    def test_completion_checks_require_exact_current_owner_scope(self):
        contract = completion._load(completion.CONTRACT_PATH)
        self.assertEqual(completion._architecture(contract)["status"], "PASS")
        bad = deepcopy(contract)
        bad["active_owner_scope"]["managed_accounts"].append("beauty_account")
        result = completion._architecture(bad)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("active_owner_scope_mismatch", result["reasons"])
        original_load = completion._load
        def drift(path):
            data = original_load(path)
            if path == completion.MEDIA_PATH:
                data["physical_media_source_platforms_by_account"]["night_scout"].append("tiktok")
            return data
        with patch.object(completion, "_load", side_effect=drift):
            result = completion._architecture(contract)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("active_owner_physical_platform_mismatch", result["reasons"])


if __name__ == "__main__":
    unittest.main()
