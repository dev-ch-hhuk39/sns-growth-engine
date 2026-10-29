#!/usr/bin/env python3
"""Normalized bundle ownership and ordering contracts, with no provider I/O."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acquisition.models import (  # noqa: E402
    NormalizedMediaItem,
    NormalizedSourcePost,
    validate_source_post,
)

POST_URL = "https://x.com/registered_owner/status/111"


def media(index=0, *, media_id="m1", **changes):
    return replace(NormalizedMediaItem(
        source_post_media_id=media_id,
        source_post_id="p1",
        media_index=index,
        media_type="image",
        canonical_post_url=POST_URL,
        original_media_url="https://cdn.example.invalid/image.jpg",
        resolver_backend="offline_fixture",
    ), **changes)


def post(*items):
    return NormalizedSourcePost(
        source_post_id="p1", source_id="s1", target_account_id="night_scout",
        platform="x", profile_url="https://x.com/registered_owner",
        canonical_post_url=POST_URL, external_post_id="111",
        original_post_text="fixture", published_at="", media_items=tuple(items),
    )


class SourcePostInvariantTests(unittest.TestCase):
    def test_valid_single_parent_is_accepted(self):
        for account in ("night_scout", "liver_manager"):
            with self.subTest(account=account):
                self.assertEqual(validate_source_post(replace(post(media()), target_account_id=account)), [])

    def test_metadata_only_source_remains_valid(self):
        self.assertEqual(validate_source_post(post()), [])

    def test_mixed_media_keeps_strict_source_order_and_original_gaps(self):
        items = (media(1), media(4, media_id="m2", media_type="video",
                                 original_media_url="https://cdn.example.invalid/video.mp4"))
        bundle = post(*items)
        self.assertEqual(validate_source_post(bundle), [])
        self.assertIs(bundle.media_items[0], items[0])
        self.assertIs(bundle.media_items[1], items[1])
        self.assertEqual([item.media_index for item in bundle.media_items], [1, 4])
        self.assertEqual([item.media_type for item in bundle.media_items], ["image", "video"])

    def test_youtube_video_canonical_url_is_preserved(self):
        url = "https://www.youtube.com/watch?v=abcdefghijk"
        bundle = replace(post(media(canonical_post_url=url, media_type="video")),
                         platform="youtube", canonical_post_url=url,
                         profile_url="https://www.youtube.com/@registered_owner",
                         external_post_id="abcdefghijk")
        self.assertEqual(validate_source_post(bundle), [])

    def test_cross_post_parent_link_is_rejected(self):
        errors = validate_source_post(post(media(source_post_id="other_parent")))
        self.assertIn("cross_post_media_link", errors)

    def test_child_canonical_field_must_match_exact_parent_field(self):
        for url in ("https://x.com/third_party/status/999", "", POST_URL + "?tracking=1"):
            with self.subTest(url=url):
                errors = validate_source_post(post(media(canonical_post_url=url)))
                self.assertIn("cross_post_media_url", errors)

    def test_empty_or_nonstring_media_identity_is_rejected(self):
        for media_id in ("", "   ", None, 0, False):
            with self.subTest(media_id=media_id):
                errors = validate_source_post(post(media(media_id=media_id)))
                self.assertIn("source_post_media_id_required", errors)

    def test_repeated_media_identity_is_rejected_even_with_unique_indices(self):
        errors = validate_source_post(post(media(0), media(1)))
        self.assertIn("duplicate_source_post_media_id", errors)

    def test_media_index_must_be_an_exact_nonnegative_integer(self):
        for index in (-1, True, False, 0.0, 1.5, "0", "1", None, [], {}):
            with self.subTest(index=index):
                errors = validate_source_post(post(media(index)))
                self.assertIn("invalid_or_duplicate_media_index", errors)

    def test_duplicate_index_is_rejected_with_distinct_media_ids(self):
        errors = validate_source_post(post(media(0), media(0, media_id="m2")))
        self.assertIn("invalid_or_duplicate_media_index", errors)

    def test_reversed_tuple_is_rejected_without_sorting_or_renumbering(self):
        bundle = post(media(4), media(1, media_id="m2"))
        self.assertIn("media_order_not_strictly_increasing", validate_source_post(bundle))
        self.assertEqual([item.media_index for item in bundle.media_items], [4, 1])
        self.assertEqual([item.source_post_media_id for item in bundle.media_items], ["m1", "m2"])

    def test_one_invalid_child_does_not_get_dropped_from_bundle(self):
        items = (media(0), media("bad", media_id="m2"), media(4, media_id="m3"))
        bundle = post(*items)
        self.assertIn("invalid_or_duplicate_media_index", validate_source_post(bundle))
        self.assertEqual(bundle.media_items, items)

    def test_real_x_adapter_keeps_filtered_url_gaps_in_original_order(self):
        import acquisition.x_gallerydl as adapter

        source = {"source_id": "s1", "source_platform": "x",
                  "source_url": "https://x.com/registered_owner",
                  "source_handle": "@registered_owner", "x_read_only": True,
                  "target_account_ids": ["night_scout"]}
        rows = [{"post_url": POST_URL, "tweet_id": "111", "tweet_content": "fixture",
                 "url": url, "extension": extension}
                for url, extension in (("https://cdn.example.invalid/image.jpg", "jpg"),
                                       ("http://cdn.example.invalid/skipped.jpg", "jpg"),
                                       ("https://cdn.example.invalid/video.mp4", "mp4"))]
        response = SimpleNamespace(returncode=0, stderr="",
                                   stdout="\n".join(json.dumps(row) for row in rows))
        with patch.object(adapter.shutil, "which", return_value="/offline/gallery-dl"), \
                patch.object(adapter.subprocess, "run", return_value=response):
            collected = adapter.XGalleryDlProfileAdapter().acquire(source, limit=3)
        self.assertEqual(len(collected), 1)
        self.assertEqual([item.media_index for item in collected[0].media_items], [0, 2])
        self.assertEqual([item.media_type for item in collected[0].media_items], ["image", "video"])
        self.assertEqual(validate_source_post(collected[0]), [])

    def test_real_persistence_skips_entire_invalid_bundles_before_data_append(self):
        import acquire_approved_source_posts as acquisition

        class Worksheet:
            def row_values(self, _row):
                return ["source_post_id", "canonical_post_url"]

            def get_all_records(self):
                return []

            def append_rows(self, *_args, **_kwargs):
                raise AssertionError("invalid bundle must not append parent or children")

        class Client:
            def _ensure_tab(self, _logical, _headers):
                return Worksheet()

            def _call_with_rate_limit_retry(self, _label, callback):
                return callback()

        bad = [post(media(canonical_post_url="https://x.com/third_party/status/999")),
               post(media(0), media(1)), post(media(4), media(1, media_id="m2")),
               post(media(False)), post(media(media_id=""))]
        result = acquisition.persist(Client(), bad)
        self.assertEqual(result["invalid_source_posts"], len(bad))
        self.assertEqual(result["saved_source_posts"], 0)
        self.assertEqual(result["saved_source_post_media"], 0)

    @staticmethod
    def persist_fixture(posts, existing=()):
        import acquire_approved_source_posts as acquisition

        class Worksheet:
            def __init__(self, headers, rows=()):
                self.headers = headers
                self.rows = [dict(row) for row in rows]
                self.appended = []

            def row_values(self, _row):
                return self.headers

            def get_all_records(self):
                return [dict(row) for row in self.rows]

            def append_rows(self, values, **_kwargs):
                rows = [dict(zip(self.headers, row)) for row in values]
                self.appended.extend(rows)
                self.rows.extend(rows)

        class Client:
            def __init__(self):
                self.sheets = {
                    logical: Worksheet(acquisition.TAB_DEFINITIONS[logical],
                                       existing if logical == "source_posts" else ())
                    for logical in ("source_posts", "source_post_media")
                }

            def _ensure_tab(self, logical, _headers):
                return self.sheets[logical]

            def _call_with_rate_limit_retry(self, _label, callback):
                return callback()

        client = Client()
        return acquisition.persist(client, posts), client.sheets

    @staticmethod
    def existing_parent(**changes):
        return {"source_post_id": "p1", "canonical_post_url": POST_URL,
                "source_id": "s1", "target_account_id": "night_scout", **changes}

    def test_existing_canonical_collision_cannot_append_orphan_children(self):
        result, sheets = self.persist_fixture(
            [post(media())], [self.existing_parent(source_post_id="other_parent")])
        self.assertEqual(result["invalid_source_posts"], 1)
        self.assertEqual(result["saved_source_posts"], 0)
        self.assertEqual(result["saved_source_post_media"], 0)
        self.assertFalse(sheets["source_posts"].appended)
        self.assertFalse(sheets["source_post_media"].appended)

    def test_existing_parent_collision_cannot_append_cross_post_children(self):
        result, sheets = self.persist_fixture(
            [post(media())], [self.existing_parent(canonical_post_url=POST_URL + "0")])
        self.assertEqual(result["invalid_source_posts"], 1)
        self.assertEqual(result["saved_source_posts"], 0)
        self.assertEqual(result["saved_source_post_media"], 0)
        self.assertFalse(sheets["source_post_media"].appended)

    def test_same_batch_parent_or_url_collision_rejects_whole_second_bundle(self):
        first = post(media())
        canonical_collision = replace(
            first, source_post_id="other_parent", source_id="other_source",
            target_account_id="liver_manager",
            media_items=(media(source_post_id="other_parent", media_id="m2"),))
        parent_collision = replace(
            first, canonical_post_url=POST_URL + "0",
            media_items=(media(canonical_post_url=POST_URL + "0", media_id="m2"),))
        for other in (canonical_collision, parent_collision):
            for ordered in ([first, other], [other, first]):
                with self.subTest(other=other.source_post_id, first=ordered[0].source_post_id):
                    result, sheets = self.persist_fixture(ordered)
                    self.assertEqual(result["invalid_source_posts"], 1)
                    self.assertEqual(result["saved_source_posts"], 1)
                    self.assertEqual(result["saved_source_post_media"], 1)
                    saved_parent = sheets["source_posts"].appended[0]
                    saved_child = sheets["source_post_media"].appended[0]
                    self.assertEqual(saved_parent["source_post_id"], ordered[0].source_post_id)
                    self.assertEqual(saved_child["source_post_id"], saved_parent["source_post_id"])
                    self.assertEqual(saved_child["canonical_post_url"], saved_parent["canonical_post_url"])

    def test_existing_parent_owner_mismatch_or_missing_owner_is_rejected(self):
        for changes in ({"source_id": "other_source"},
                        {"target_account_id": "liver_manager"},
                        {"source_id": ""}, {"target_account_id": ""}):
            with self.subTest(changes=changes):
                result, sheets = self.persist_fixture(
                    [post(media())], [self.existing_parent(**changes)])
                self.assertEqual(result["invalid_source_posts"], 1)
                self.assertEqual(result["saved_source_posts"], 0)
                self.assertEqual(result["saved_source_post_media"], 0)
                self.assertFalse(sheets["source_post_media"].appended)

    def test_same_batch_parent_owner_mismatch_is_rejected(self):
        first = post(media())
        for changes in ({"source_id": "other_source"}, {"target_account_id": "liver_manager"}):
            with self.subTest(changes=changes):
                other = replace(first, **changes, media_items=(media(1, media_id="m2"),))
                result, sheets = self.persist_fixture([first, other])
                self.assertEqual(result["invalid_source_posts"], 1)
                self.assertEqual(result["saved_source_posts"], 1)
                self.assertEqual(result["saved_source_post_media"], 1)
                self.assertEqual(sheets["source_post_media"].appended[0]["source_post_media_id"], "m1")

    def test_ambiguous_existing_bindings_cannot_use_last_matching_row(self):
        for conflicting in (self.existing_parent(source_post_id="other_parent"),
                            self.existing_parent(canonical_post_url=POST_URL + "0"),
                            self.existing_parent(source_id="other_source"),
                            self.existing_parent(target_account_id="liver_manager")):
            for rows in ([conflicting, self.existing_parent()],
                         [self.existing_parent(), conflicting]):
                with self.subTest(conflicting=conflicting, rows=rows):
                    result, sheets = self.persist_fixture([post(media())], rows)
                    self.assertEqual(result["invalid_source_posts"], 1)
                    self.assertEqual(result["saved_source_post_media"], 0)
                    self.assertFalse(sheets["source_post_media"].appended)

    def test_exact_existing_parent_can_gain_missing_child_without_reparenting(self):
        for account in ("night_scout", "liver_manager"):
            with self.subTest(account=account):
                bundle = replace(post(media()), target_account_id=account)
                existing = self.existing_parent(target_account_id=account)
                result, sheets = self.persist_fixture([bundle], [existing])
                self.assertEqual(result["invalid_source_posts"], 0)
                self.assertEqual(result["duplicate_source_posts"], 1)
                self.assertEqual(result["saved_source_posts"], 0)
                self.assertEqual(result["saved_source_post_media"], 1)
                self.assertFalse(sheets["source_posts"].appended)
                self.assertEqual(sheets["source_post_media"].appended[0]["source_post_id"], "p1")

    def test_exact_same_batch_parent_repeats_remain_deduplicated(self):
        bundle = post(media())
        result, sheets = self.persist_fixture([bundle, bundle])
        self.assertEqual(result["invalid_source_posts"], 0)
        self.assertEqual(result["duplicate_source_posts"], 1)
        self.assertEqual(result["saved_source_posts"], 1)
        self.assertEqual(result["saved_source_post_media"], 1)
        self.assertEqual(len(sheets["source_post_media"].appended), 1)


if __name__ == "__main__":
    unittest.main()
