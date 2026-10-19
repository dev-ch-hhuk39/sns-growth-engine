#!/usr/bin/env python3
"""Offline regression: legacy text AUTO_READY must never authorize V2, media or posting."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

import auto_ready_draft_preflight as gate
import generate_threads_ideas_from_references as generator
import maintain_text_ready_inventory as inventory


class AutonomousTextIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.quality = json.loads(gate.DEFAULT_POLICY.read_text(encoding="utf-8"))
        self.mode = json.loads(gate.AUTONOMOUS_POLICY.read_text(encoding="utf-8"))

    def evaluate(self, *, account: str = "night_scout",
                 quality: dict | None = None, mode: dict | None = None) -> tuple[str, int]:
        with tempfile.TemporaryDirectory() as tmp:
            q = Path(tmp) / "quality.json"
            m = Path(tmp) / "autonomous.json"
            q.write_text(json.dumps(self.quality if quality is None else quality))
            m.write_text(json.dumps(self.mode if mode is None else mode))
            return gate.autonomous_text_policy_status(
                account, quality_policy_path=q, autonomous_policy_path=m,
            )

    def test_all_three_active_accounts_allow_isolated_text_mode(self) -> None:
        for account in ("night_scout", "liver_manager", "beauty_account"):
            with self.subTest(account=account):
                self.assertEqual(self.evaluate(account=account),
                                 ("AUTONOMOUS_TEXT_ONLY_PREFLIGHT_PASS", 0))

    def test_v2_editorial_candidates_must_remain_draft_only(self) -> None:
        for key, value in (("draft_only", False), ("publishing_enabled", True),
                           ("schema_version", "unrecognized")):
            with self.subTest(key=key):
                self.assertEqual(self.evaluate(quality={**self.quality, key: value})[1], 2)

    def test_autonomous_mode_hard_gates_are_fail_closed(self) -> None:
        values = (
            ("auto_ready_enabled", False),
            ("kill_switch", True),
            ("allow_unknown_rights", True),
            ("allow_third_party_media", True),
            ("allow_media_posts", True),
            ("media_operations_delegated", False),
            ("min_quality_score", 50),
            ("min_safety_score", 10),
            ("max_risk_score", 80),
            ("max_similarity_to_source", 0.9),
            ("allowed_platforms_for_post", ["threads", "x"]),
            ("blocked_platforms_for_post", []),
            ("allowed_accounts", ["night_scout", "tiktok_shop"]),
            ("allowed_accounts", [{"account": "night_scout"}]),
            ("blocked_platforms_for_post", None),
            ("max_similarity_to_source", float("nan")),
        )
        for key, value in values:
            with self.subTest(key=key):
                self.assertEqual(self.evaluate(mode={**self.mode, key: value})[1], 2)

    def test_unknown_or_extra_account_is_rejected(self) -> None:
        for account in ("tiktok_shop", "all", "", "night_scout;injected"):
            with self.subTest(account=account):
                self.assertEqual(self.evaluate(account=account)[1], 2)

    def test_policy_files_missing_or_bad_are_rejected_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing"
            self.assertEqual(gate.autonomous_text_policy_status(
                "night_scout", autonomous_policy_path=missing,
            ), ("AUTONOMOUS_TEXT_POLICY_UNVERIFIED", 2))
            invalid = Path(tmp) / "invalid.json"
            invalid.write_text("{not-json")
            self.assertEqual(gate.autonomous_text_policy_status(
                "night_scout", autonomous_policy_path=invalid,
            ), ("AUTONOMOUS_TEXT_POLICY_UNVERIFIED", 2))

    def test_legacy_generators_remain_closed_without_explicit_opt_in(self) -> None:
        ref = generator.run_reference_generation("night_scout", 1, apply=True)
        offline = generator.run_offline_original_generation(
            "night_scout", 1, apply=True, slot_id="ns_0900", schedule_date_jst="2026-10-19",
        )
        self.assertEqual(ref["status"], "DRAFT_ONLY")
        self.assertEqual(offline["status"], "DRAFT_ONLY")
        with patch.object(generator, "autonomous_text_policy_status", return_value=("BLOCKED", 2)):
            guarded = generator.run_reference_generation(
                "night_scout", 1, apply=True, allow_autonomous_text_generation=True,
            )
            self.assertEqual(guarded["status"], "DRAFT_ONLY")

    def test_explicit_text_generation_keeps_review_status_and_cannot_post(self) -> None:
        for account in ("night_scout", "liver_manager", "beauty_account"):
            args = argparse.Namespace(
                account_id=account, platform="threads", source="references", top_n=2,
                apply=True, confirm_generate=True, offline_original=False,
                autonomous_text_generation=True,
            )
            plan = generator.build_plan(args)
            self.assertEqual(plan["status"], "WILL_RUN")
            self.assertEqual(plan["safety"]["candidate_status"], "WAITING_REVIEW")
            self.assertFalse(plan["safety"]["delegate_posts"])
            self.assertFalse(plan["safety"]["worker_selectable"])
            self.assertFalse(plan["safety"]["real_post_possible_now"])
            args.source = "clips"
            self.assertEqual(generator.build_plan(args)["status"], "BLOCKED")
            args.source = "references"
            args.confirm_generate = False
            self.assertEqual(generator.build_plan(args)["status"], "BLOCKED")

    def test_inventory_routes_pass_flag_but_never_real_post_flag(self) -> None:
        slot = {"slot_id": "ns_1400_reference", "post_type": "reference_text",
                "business_date_jst": "2026-10-19", "theme": ""}
        for route, cmd in inventory._generation_commands("night_scout", slot):
            with self.subTest(route=route):
                self.assertIn("--autonomous-text-generation", cmd)
                self.assertIn("--confirm-generate", cmd)
                self.assertNotIn("--confirm-real-post", cmd)
        beauty_slot = {"slot_id": "beauty_test", "post_type": "original_text",
                       "business_date_jst": "2026-10-19", "theme": ""}
        offline = inventory._generation_commands("beauty_account", beauty_slot, offline_only=True)
        self.assertEqual(len(offline), 1)
        self.assertIn("--autonomous-text-generation", offline[0][1])

if __name__ == "__main__":
    unittest.main()
