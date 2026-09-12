#!/usr/bin/env python3
"""Account-specific clip ranking must not borrow another account's domain."""
import unittest

from media_growth_schemas import score_clip_candidate


class ClipScoringAccountIsolationTests(unittest.TestCase):
    def score(self, account, text):
        return score_clip_candidate({"target_account_id": account, "rights_status": "approved_creator_clip"},
                                    has_transcript=True, transcript_excerpt=text)

    def test_beauty_uses_beauty_evidence(self):
        good = self.score("beauty_account", "コスメのメイクとスキンケアを選ぶ")
        wrong = self.score("beauty_account", "配信の初見とコメントとリスナー")
        self.assertGreater(good["creator_relevance"], wrong["creator_relevance"])
        self.assertEqual(wrong["creator_relevance"], 4)
        self.assertEqual(good["liver_manager_fit"], 0)

    def test_liver_keeps_existing_evidence_and_weights(self):
        scores = self.score("liver_manager", "配信の初見とコメントとリスナー")
        self.assertEqual(scores["creator_relevance"], 16)
        self.assertEqual(scores["liver_manager_fit"], 16)
        self.assertEqual(self.score("liver_manager", "コスメとスキンケア")["creator_relevance"], 4)

    def test_night_keeps_existing_evidence_and_weights(self):
        scores = self.score("night_scout", "夜職の時給とノルマと客層")
        self.assertEqual(scores["creator_relevance"], 16)
        self.assertEqual(scores["liver_manager_fit"], 0)
        self.assertEqual(self.score("night_scout", "配信の初見とコメント")["creator_relevance"], 4)

    def test_unknown_account_does_not_default_to_liver(self):
        scores = self.score("unknown", "配信の初見とコメントとリスナー")
        self.assertEqual(scores["creator_relevance"], 4)
        self.assertEqual(scores["liver_manager_fit"], 0)

    def test_rights_and_score_caps_unchanged(self):
        scores = score_clip_candidate({"target_account_id": "beauty_account", "rights_status": "third_party_reference_only"},
                                      has_transcript=True, transcript_excerpt="コスメのメイクとスキンケアを選ぶ")
        self.assertEqual(scores["rights_score"], 0)
        self.assertEqual(scores["risk_score"], 4)
        self.assertLessEqual(scores["creator_relevance"], 18)
        self.assertLessEqual(scores["clip_score"], 100)


if __name__ == "__main__":
    unittest.main()
