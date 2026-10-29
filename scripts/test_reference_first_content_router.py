"""Focused contract for the shared reference-first route selector."""
from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from generation.content_mix_planner import plan_operational_threads_routes
from generation.reference_first_router import clip_eligibility, choose_reference_first_route, load_operational_mix
from run_media_production_pipeline import select_candidate


def passed_understanding() -> dict:
    return {
        "status": "PASS", "transcript_status": "PASS",
        "standalone_segment_confirmed": True, "standalone_story_score": 91,
        "clip_worthy": True,
    }


def main() -> None:
    for account_id in ("night_scout", "liver_manager"):
        mix = load_operational_mix(account_id)
        assert mix == {
            "new_text_generation": 5,
            "reference_text_generation": 30,
            "pdca_text_generation": 10,
            "direct_reference_media": 50,
            "approved_source_clip": 5,
        }
        routes = plan_operational_threads_routes(account_id, 20)
        assert routes.count("approved_source_clip") == 1
        assert routes.count("reference_text_generation") == 6
        assert routes.count("direct_reference_media") == 10

    forced = choose_reference_first_route(
        desired_route="approved_source_clip", source_has_direct_media_permission=True,
        content_understanding={"status": "PASS", "transcript_status": "PASS"},
    )
    assert forced["route"] == "direct_reference_media"
    assert forced["clip_eligible"] is False

    clip = choose_reference_first_route(
        desired_route="approved_source_clip", source_has_direct_media_permission=True,
        content_understanding=passed_understanding(),
    )
    assert clip["route"] == "approved_source_clip" and clip["clip_eligible"] is True

    no_permission = choose_reference_first_route(
        desired_route="direct_reference_media", source_has_direct_media_permission=False,
    )
    assert no_permission["status"] == "BLOCKED"
    assert "direct_media_permission_missing" in no_permission["reasons"]
    print("PASS reference-first routing: reference/quote=80%, direct comments are video-only, clip=5%")


class ClipEvidenceTests(unittest.TestCase):
    def test_existing_route_and_mix_contract(self):
        main()

    def test_confirmed_boolean_and_sheets_flags_remain_eligible(self):
        # Sheets get_all_records numericises a saved "1" to primitive int1.
        for field in ("standalone_segment_confirmed", "clip_worthy"):
            for value in (True, 1, "true", "TRUE", " True ", "1", "yes", " YES "):
                with self.subTest(field=field, value=value):
                    eligible, reasons = clip_eligibility({**passed_understanding(), field: value})
                    self.assertTrue(eligible, reasons)

    def test_false_and_unknown_flags_cannot_select_clip(self):
        invalid = (False, 0, 2, 1.0, None, "", "false", "FALSE", "0", "no", "unknown",
                   "approved", "pass", "on", [], [True], {}, {"confirmed": True})
        for field, reason in (("standalone_segment_confirmed", "standalone_segment_not_confirmed"),
                              ("clip_worthy", "clip_worthiness_not_confirmed")):
            for value in invalid:
                with self.subTest(field=field, value=value):
                    evidence = {**passed_understanding(), field: value}
                    eligible, reasons = clip_eligibility(evidence)
                    self.assertFalse(eligible)
                    self.assertIn(reason, reasons)
                    for permission in (True, False):
                        route = choose_reference_first_route(
                            desired_route="approved_source_clip",
                            source_has_direct_media_permission=permission,
                            content_understanding=evidence)
                        self.assertFalse(route["clip_eligible"])
                        self.assertEqual(route["route"], "direct_reference_media" if permission else "")
                        self.assertEqual(route["status"], "PASS" if permission else "BLOCKED")

    def test_missing_flags_are_unconfirmed(self):
        for field in ("standalone_segment_confirmed", "clip_worthy"):
            with self.subTest(field=field):
                evidence = passed_understanding()
                del evidence[field]
                self.assertFalse(clip_eligibility(evidence)[0])

    def test_nonfinite_and_invalid_scores_cannot_select_clip(self):
        invalid = (float("nan"), float("inf"), float("-inf"), "nan", "NaN", "inf", "Infinity",
                   "-Infinity", "1e10000", "not-a-score", "", None, {}, [], 10**1000)
        for score in invalid:
            with self.subTest(score=score):
                evidence = {**passed_understanding(), "standalone_story_score": score}
                eligible, reasons = clip_eligibility(evidence)
                self.assertFalse(eligible)
                self.assertIn("standalone_story_score_below_threshold", reasons)
                route = choose_reference_first_route(
                    desired_route="approved_source_clip", source_has_direct_media_permission=True,
                    content_understanding=evidence)
                self.assertEqual(route["route"], "direct_reference_media")
                self.assertFalse(route["clip_eligible"])

    def test_existing_eighty_five_minimum_is_preserved(self):
        for score in (84, 84.999, "84", "84.999", True, False):
            with self.subTest(score=score):
                self.assertFalse(clip_eligibility({**passed_understanding(), "standalone_story_score": score})[0])
        # The contract specifies a finite minimum; do not invent a new cap.
        for score in (85, 85.0, "85", "85.0", " 85 ", "8.5e1", 100, 101, 1e308):
            with self.subTest(score=score):
                self.assertTrue(clip_eligibility({**passed_understanding(), "standalone_story_score": score})[0])

    @staticmethod
    def candidate_fixture():
        text = "配信で伸び悩んだ時は、まず初見の人が入りやすい空気を整えること。入室へのお礼、今話している内容、気軽にコメントできる一言。この3つだけでも滞在しやすさは変わる。"
        source = {
            "source_video_id": "sv_router", "account_id": "liver_manager", "platform": "youtube",
            "canonical_video_url": "https://www.youtube.com/watch?v=abcdefghijk",
            "rights_status": "approved_creator_clip", "permission_status": "approved",
        }
        clip = {
            "clip_candidate_id": "clip_router", "source_video_id": "sv_router", "account_id": "liver_manager",
            "clip_status": "READY", "rights_status": "approved_creator_clip", "permission_status": "approved",
            "transcript_grounded": "true", "transcript_excerpt": text, "public_post_text": text,
            "start_seconds": "10", "end_seconds": "35", "alignment_status": "PASS", "clip_score": 99,
            **passed_understanding(), "standalone_segment_confirmed": "true", "clip_worthy": "true",
            "standalone_story_score": "85",
        }
        return clip, source

    def test_real_sheets_caller_rejects_false_flags_and_nonfinite_scores(self):
        clip, source = self.candidate_fixture()
        selected, _, reasons = select_candidate([clip], [source], [], account_id="liver_manager")
        self.assertIsNotNone(selected, reasons)
        invalid = (("standalone_segment_confirmed", "false"), ("clip_worthy", "false"),
                   ("standalone_story_score", 0), ("standalone_story_score", 0.0),
                   ("standalone_story_score", False), ("standalone_story_score", "0"),
                   ("standalone_story_score", float("nan")), ("standalone_story_score", "NaN"),
                   ("standalone_story_score", float("inf")), ("standalone_story_score", "Infinity"))
        for field, value in invalid:
            with self.subTest(field=field, value=value):
                selected, _, reasons = select_candidate([{**clip, field: value}], [source], [], account_id="liver_manager")
                self.assertIsNone(selected)
                self.assertTrue(any("clip_not_worthy:" in reason for reason in reasons), reasons)

    def test_legacy_ready_caller_evidence_remains_supported(self):
        clip, source = self.candidate_fixture()
        for field in ("standalone_segment_confirmed", "standalone_story_score", "clip_worthy"):
            del clip[field]
        selected, _, reasons = select_candidate([clip], [source], [], account_id="liver_manager")
        self.assertIsNotNone(selected, reasons)

        for status in ("READY", "AUTO_APPROVED", "MEDIA_READY"):
            for missing in (None, ""):
                with self.subTest(status=status, missing=missing):
                    row = {**clip, "clip_status": status, "standalone_story_score": missing,
                           "confidence_score": missing}
                    selected, _, reasons = select_candidate([row], [source], [], account_id="liver_manager")
                    self.assertIsNotNone(selected, reasons)

    def test_explicit_zero_legacy_confidence_is_not_replaced_by_ranking_score(self):
        clip, source = self.candidate_fixture()
        del clip["standalone_story_score"]
        for score in (0, 0.0, False, "0"):
            with self.subTest(score=score):
                selected, _, reasons = select_candidate(
                    [{**clip, "confidence_score": score}], [source], [], account_id="liver_manager")
                self.assertIsNone(selected)
                self.assertTrue(any("clip_not_worthy:" in reason for reason in reasons), reasons)

    def test_waiting_review_never_inherits_legacy_ready_scores(self):
        clip, source = self.candidate_fixture()
        clip.update(clip_status="WAITING_REVIEW", public_post_validator_status="PASS")
        selected, _, reasons = select_candidate([clip], [source], [], account_id="liver_manager")
        self.assertIsNone(selected)
        self.assertIn("clip_router:clip_not_ready", reasons)
        # Preparation can inspect review rows, but still requires explicit
        # standalone evidence rather than their high generic ranking score.
        selected, _, reasons = select_candidate(
            [clip], [source], [], account_id="liver_manager", allow_waiting_review=True)
        self.assertIsNotNone(selected, reasons)
        for missing in (None, ""):
            with self.subTest(missing=missing):
                selected, _, reasons = select_candidate(
                    [{**clip, "standalone_story_score": missing}], [source], [],
                    account_id="liver_manager", allow_waiting_review=True)
                self.assertIsNone(selected)
                self.assertTrue(any("clip_not_worthy:" in reason for reason in reasons), reasons)
        del clip["standalone_story_score"]
        selected, _, reasons = select_candidate(
            [clip], [source], [], account_id="liver_manager", allow_waiting_review=True)
        self.assertIsNone(selected)
        self.assertTrue(any("clip_not_worthy:" in reason for reason in reasons), reasons)

    def test_valid_understanding_cannot_bypass_actual_caller_rights_gate(self):
        clip, source = self.candidate_fixture()
        self.assertTrue(clip_eligibility(clip)[0])
        for field, value in (("rights_status", "reference_only"), ("permission_status", "pending")):
            with self.subTest(field=field):
                selected, _, reasons = select_candidate([{**clip, field: value}], [source], [], account_id="liver_manager")
                self.assertIsNone(selected)
                self.assertIn("clip_router:rights_or_permission_blocked", reasons)


if __name__ == "__main__":
    unittest.main()
