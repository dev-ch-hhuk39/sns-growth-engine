#!/usr/bin/env python3
"""Offline Golden proof contracts; synthetic fixtures are not production proof."""
from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from media.golden_evidence import (  # noqa: E402
    validate_metadata_provenance, validate_registered_binding, validate_semantic_evidence,
)

VIDEO = "abcdefghijk"
CHANNEL = "UC" + "a" * 22
DIGEST = hashlib.sha256(b"offline synthetic video fixture").hexdigest()
ASSET = "ma_" + DIGEST[:24]


def fixture(platform="x", account="night_scout"):
    profile = "https://x.com/registered_owner" if platform == "x" else "https://www.youtube.com/@registered_owner"
    url = profile + "/status/123456789" if platform == "x" else "https://www.youtube.com/watch?v=" + VIDEO
    item = {"source_id": "registered_source", "account_id": account,
            "source_handle": "@registered_owner", "url": url}
    source = {"source_id": "registered_source", "source_platform": platform,
              "source_handle": "@registered_owner", "source_url": profile,
              "target_account_ids": [account], "active": True}
    result = validate_registered_binding(item, [source])
    assert result["status"] == "PASS", result
    return item, source, result["binding"]


def metadata(platform="x"):
    if platform == "x":
        return {"id": "separate-media-id", "display_id": "123456789", "uploader_id": "registered_owner",
                "webpage_url": "https://x.com/registered_owner/status/123456789", "formats": [{"vcodec": "h264"}]}
    return {"id": VIDEO, "display_id": VIDEO, "uploader_id": "@registered_owner",
            "webpage_url": "https://www.youtube.com/shorts/" + VIDEO,
            "channel_url": "https://www.youtube.com/channel/" + CHANNEL, "channel_id": CHANNEL}


def proof(binding):
    return {"schema_version": 1, "account_id": binding["account_id"], "source_id": binding["source_id"],
            "canonical_url": binding["canonical_url"], "external_post_id": binding["external_post_id"],
            "media_asset_id": ASSET, "content_hash": DIGEST,
            "analysis": {"status": "PASS", "aggregate_status": "PASS_VISION", "provider": "gemini",
                "vision_status": "PASS", "http_status": 200, "response_schema_status": "PASS",
                "visual_summary": "人物が机に置いた紙を手に取る映像。", "visible_action": "人物が紙を手に取る。",
                "key_moment": "紙をカメラに向ける場面。",
                "visual_facts": [{"id": "VF1", "type": "visible_action", "text": "人物が紙を手に取る。"}],
                "visual_evidence": {"status": "UNDERSTOOD", "provider": "gemini", "media_asset_id": ASSET,
                                    "content_hash": DIGEST, "frame_hashes": [hashlib.sha256(b"offline frame fixture").hexdigest()]},
                "transcript_status": "UNAVAILABLE", "transcript_text": ""}}


class RegisteredBindingTests(unittest.TestCase):
    def test_valid_both_account_platform_bindings_do_not_grant_permissions(self):
        for platform in ("x", "youtube"):
            for account in ("night_scout", "liver_manager"):
                item, source, expected = fixture(platform, account)
                item.update(allow_download=True, permission_status="approved", media_asset_id="forged_asset")
                result = validate_registered_binding(item, [source])
                self.assertEqual(result["binding"], expected)
                self.assertNotIn("allow_download", expected)
                self.assertNotIn("media_asset_id", expected)

    def test_missing_or_duplicate_source_is_refused(self):
        item, source, _ = fixture()
        for rows in ([], [source, source], [{**source, "source_id": "other"}]):
            result = validate_registered_binding(item, rows)
            self.assertEqual(result["status"], "BLOCKED")
            self.assertEqual(result["binding"], {})

    def test_inactive_blocked_retired_source_is_refused(self):
        item, source, _ = fixture()
        for changes in ({"active": False}, {"active": "false"}, {"active": 0}, {"blocked": True},
                        {"retired_from_runtime_selection": True}, {"editorial_selection_status": "retired"}):
            self.assertEqual(validate_registered_binding(item, [{**source, **changes}])["status"], "BLOCKED")

    def test_account_scope_cannot_be_replaced_by_manifest(self):
        item, source, _ = fixture()
        for account in ("liver_manager", "beauty_account", "", None):
            self.assertEqual(validate_registered_binding({**item, "account_id": account}, [source])["status"], "BLOCKED")

    def test_profile_platform_and_author_mismatch_are_refused(self):
        item, source, _ = fixture()
        for changes in ({"source_handle": "@other"}, {"source_url": "https://x.com/other"},
                        {"source_url": "https://x.com/registered_owner/status/123"}, {"source_platform": "youtube"},
                        {"source_url": "https://x.com.evil.invalid/registered_owner"}):
            self.assertEqual(validate_registered_binding(item, [{**source, **changes}])["status"], "BLOCKED")
        self.assertEqual(validate_registered_binding({**item, "source_handle": "@other"}, [source])["status"], "BLOCKED")
        self.assertEqual(validate_registered_binding({**item, "url": "https://x.com/other/status/123456789"}, [source])["status"], "BLOCKED")

    def test_only_https_individual_urls_are_admitted(self):
        item, source, _ = fixture()
        for url in ("http://x.com/registered_owner/status/123456789", "https://x.com/registered_owner",
                    "https://x.com.evil.invalid/registered_owner/status/123456789",
                    "https://user:password@x.com/registered_owner/status/123456789",
                    "https://x.com:8080/registered_owner/status/123456789"):
            self.assertEqual(validate_registered_binding({**item, "url": url}, [source])["status"], "BLOCKED")

    def test_youtube_url_aliases_keep_case_sensitive_exact_video_id(self):
        item, source, expected = fixture("youtube")
        for url in ("https://youtu.be/" + VIDEO, "https://www.youtube.com/shorts/" + VIDEO):
            self.assertEqual(validate_registered_binding({**item, "url": url}, [source])["binding"], expected)
        for url in ("https://www.youtube.com/watch?v=" + VIDEO + "x", "https://www.youtube.com/watch?v=a&v=b"):
            self.assertEqual(validate_registered_binding({**item, "url": url}, [source])["status"], "BLOCKED")


class MetadataTests(unittest.TestCase):
    def test_x_positive_extracted_author_and_status_allow_separate_media_id(self):
        _, _, binding = fixture()
        result = validate_metadata_provenance(binding, metadata())
        self.assertEqual(result["status"], "PASS", result)

    def test_x_url_echo_or_formats_without_extracted_identity_is_refused(self):
        _, _, binding = fixture()
        for value in ({"formats": [{"vcodec": "h264"}]},
                      {"webpage_url": binding["canonical_url"], "formats": [{"vcodec": "h264"}]},
                      {"original_url": binding["canonical_url"], "formats": [{"vcodec": "h264"}]},
                      {k: v for k, v in metadata().items() if k != "display_id"},
                      {k: v for k, v in metadata().items() if k != "uploader_id"}):
            self.assertEqual(validate_metadata_provenance(binding, value)["status"], "BLOCKED")

    def test_x_alternative_actual_author_fields_are_supported(self):
        _, _, binding = fixture()
        for author_field in ("author_handle", "channel_id"):
            value = metadata()
            value[author_field] = value.pop("uploader_id")
            self.assertEqual(validate_metadata_provenance(binding, value)["status"], "PASS")

    def test_x_mismatch_retweet_quote_and_missing_video_are_refused(self):
        _, _, binding = fixture()
        for changes in ({"display_id": "1234567890"}, {"uploader_id": "other"},
                        {"webpage_url": "https://x.com/other/status/123456789"},
                        {"is_retweet": True}, {"quoted_status_id": "123"}, {"formats": []}, {"formats": 123}):
            self.assertEqual(validate_metadata_provenance(binding, {**metadata(), **changes})["status"], "BLOCKED")

    def test_youtube_requires_positive_id_page_and_registered_author(self):
        _, _, binding = fixture("youtube")
        self.assertEqual(validate_metadata_provenance(binding, metadata("youtube"))["status"], "PASS")
        for changes in ({"id": "wrongvideo1"}, {"webpage_url": "https://www.youtube.com/watch?v=wrongvideo1"},
                        {"webpage_url": ""}, {"uploader_id": "@other"}, {"uploader_id": ""},
                        {"uploader_id": "", "uploader": "registered_owner"}, {"display_id": "wrongvideo1"}):
            self.assertEqual(validate_metadata_provenance(binding, {**metadata("youtube"), **changes})["status"], "BLOCKED")

    def test_youtube_profile_url_is_positive_author_evidence(self):
        _, _, binding = fixture("youtube")
        value = metadata("youtube")
        value.pop("uploader_id")
        value["uploader_url"] = "https://www.youtube.com/@registered_owner"
        self.assertEqual(validate_metadata_provenance(binding, value)["status"], "PASS")
        value["uploader_url"] = "https://www.youtube.com/@other"
        self.assertEqual(validate_metadata_provenance(binding, value)["status"], "BLOCKED")

    def test_youtube_channel_id_is_not_a_handle_but_can_match_registered_channel(self):
        _, _, binding = fixture("youtube")
        value = metadata("youtube")
        value["uploader_id"] = CHANNEL
        self.assertEqual(validate_metadata_provenance(binding, value)["status"], "BLOCKED")
        bound = {**binding, "registered_channel_id": CHANNEL}
        self.assertEqual(validate_metadata_provenance(bound, value)["status"], "PASS")
        value["channel_id"] = "UC" + "b" * 22
        self.assertEqual(validate_metadata_provenance(bound, value)["status"], "BLOCKED")


class SemanticTests(unittest.TestCase):
    def setUp(self):
        _, _, self.binding = fixture()
        self.valid = proof(self.binding)

    def check_blocked(self, value, digest=DIGEST):
        result = validate_semantic_evidence(self.binding, digest, value)
        self.assertEqual(result["status"], "BLOCKED", result)
        self.assertEqual(result["context"], {})

    def test_full_sha_bound_gemini_schema_normalizes_to_verified_visual(self):
        result = validate_semantic_evidence(self.binding, DIGEST, self.valid)
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(result["context"]["visual_status"], "VISUAL_VERIFIED")

    def test_missing_or_summary_only_legacy_proof_cannot_pass(self):
        for value in (None, {}, {"status": "PASS", "summary": "description", "representative_frame_count": "3"},
                      {**self.valid, "analysis": {"status": "PASS", "summary": "description"}}):
            self.check_blocked(value)

    def test_schema_and_identity_envelope_mismatch_are_refused(self):
        for key, bad in (("schema_version", True), ("schema_version", 2), ("account_id", "liver_manager"),
                         ("source_id", "another_source"), ("external_post_id", "1234567890"),
                         ("canonical_url", "https://x.com/registered_owner/status/123456780"),
                         ("media_asset_id", "unbound_asset"), ("content_hash", "b" * 64)):
            self.check_blocked({**self.valid, key: bad})

    def test_changed_actual_bytes_cannot_inherit_old_proof(self):
        self.check_blocked(self.valid, hashlib.sha256(b"different video").hexdigest())
        for invalid in ("", "not-sha", "A" * 64):
            self.check_blocked(self.valid, invalid)

    def test_inner_evidence_hash_and_asset_must_match_actual_envelope(self):
        for key, bad in (("content_hash", "c" * 64), ("media_asset_id", "different_asset")):
            value = deepcopy(self.valid)
            value["analysis"]["visual_evidence"][key] = bad
            self.check_blocked(value)

    def test_retired_unknown_provider_and_incomplete_provider_response_are_refused(self):
        for change in ({"http_status": 503}, {"http_status": "200"}, {"response_schema_status": "BLOCKED"},
                       {"visual_facts": []}, {"visual_summary": ""}, {"key_moment": ""},
                       {"vision_status": "UNAVAILABLE"}, {"provider": "github_models_vision"}):
            self.check_blocked({**self.valid, "analysis": {**self.valid["analysis"], **change}})
        for provider in ("github_models_vision", "unknown", ""):
            value = deepcopy(self.valid)
            value["analysis"]["visual_evidence"]["provider"] = provider
            self.check_blocked(value)

    def test_status_pass_ocr_or_asr_only_cannot_be_visual_understanding(self):
        for aggregate in ("PASS_OCR_ONLY", "PASS_ASR_ONLY"):
            value = deepcopy(self.valid)
            value["analysis"].update(aggregate_status=aggregate, vision_status="UNAVAILABLE", transcript_status="PASS")
            value["analysis"]["visual_evidence"]["status"] = "EXTRACTED_ONLY"
            self.check_blocked(value)

    def test_frame_hashes_require_nonempty_sha_list(self):
        for hashes in ([], "a" * 64, ["not-sha"], [None], ["A" * 64]):
            value = deepcopy(self.valid)
            value["analysis"]["visual_evidence"]["frame_hashes"] = hashes
            self.check_blocked(value)

    def test_repeated_analysis_identity_must_not_rewrite_parent(self):
        for key, bad in (("account_id", "liver_manager"), ("source_id", "other"),
                         ("media_asset_id", "other_asset"), ("content_hash", "d" * 64)):
            self.check_blocked({**self.valid, "analysis": {**self.valid["analysis"], key: bad}})

    def test_only_independently_bound_custom_asset_id_is_supported(self):
        bound = {**self.binding, "media_asset_id": "independently_bound_asset"}
        value = deepcopy(self.valid)
        value["media_asset_id"] = bound["media_asset_id"]
        value["analysis"]["visual_evidence"]["media_asset_id"] = bound["media_asset_id"]
        self.assertEqual(validate_semantic_evidence(bound, DIGEST, value)["status"], "PASS")
        self.check_blocked(value)

    def test_pure_verification_does_not_call_provider_subprocess_or_read_files(self):
        with patch("subprocess.run", side_effect=AssertionError("no subprocess")), \
                patch.object(Path, "read_text", side_effect=AssertionError("no file read")):
            self.assertEqual(validate_semantic_evidence(self.binding, DIGEST, self.valid)["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
