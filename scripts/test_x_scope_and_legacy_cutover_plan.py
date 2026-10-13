#!/usr/bin/env python3
"""Offline tests for the immutable X product stop and cutover plan."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from publishers.active_platform_policy import (  # noqa: E402
    ACTIVE_REAL_PUBLISH_PLATFORMS, allowed_for_real_post,
)
from publishers.factory import _SafetyStopPublisher, get_publisher  # noqa: E402
from publishers.x_publisher import XPublisher  # noqa: E402
from plan_legacy_writer_cutover import (  # noqa: E402
    CutoverPlanBlocked, build_plan, main,
)


class XProductScopeStop(unittest.TestCase):
    def test_active_platform_code_scope_is_not_env_config(self):
        self.assertEqual(ACTIVE_REAL_PUBLISH_PLATFORMS, frozenset({"threads"}))
        self.assertFalse(allowed_for_real_post("x"))
        self.assertTrue(allowed_for_real_post("threads"))
        self.assertFalse(allowed_for_real_post("note"))

    def test_every_X_path_blocked_despite_legacy_flags(self):
        flags = {
            "PUBLISH_ENABLED": "true", "ALLOW_REAL_X_POST": "true",
            "X_PUBLISHER_ENABLED": "true", "X_API_KEY": "not-a-real-key",
            "X_API_SECRET": "not-a-real-key", "X_ACCESS_TOKEN": "fake",
            "X_ACCESS_TOKEN_SECRET": "fake",
        }
        with patch.dict(os.environ, flags), patch(
            "requests.post", side_effect=AssertionError("X HTTP forbidden"),
        ) as outbound, patch(
            "config_loader.get_x_credentials",
            side_effect=AssertionError("no credential loader"),
        ) as creds:
            pub = XPublisher()
            result = pub.publish(
                "Synthetic text", account={"account_id": "night_scout"},
                derivative={"derivative_id": "d1"},
                queue_item={"queue_id": "q1", "platform": "x"},
                dry_run=False,
            )
            self.assertFalse(result.success)
            self.assertIn("X_REAL_POST_DISABLED_BY_PRODUCT_POLICY", result.message)
            self.assertIsNone(result.posted_url)
            self.assertIsNone(result.external_post_id)
            result2 = pub._publish_with_oauth1(
                text="Synthetic", creds=flags,
                account_id="night_scout", queue_id="q1",
                derivative_id="d1",
            )
            self.assertFalse(result2.success)
            self.assertIn("X_HTTP_SINK_DISABLED_BY_PRODUCT_POLICY", result2.message)
            self.assertEqual(outbound.call_count, 0)
            self.assertEqual(creds.call_count, 0)
            factory_pub = get_publisher("x", dry_run=False)
            self.assertIsInstance(factory_pub, _SafetyStopPublisher)
            denied = factory_pub.publish(
                "test", account={"account_id": "night_scout"},
                derivative={}, queue_item={"queue_id": "q1"}, dry_run=False,
            )
            self.assertFalse(denied.success)
            self.assertIsNone(denied.posted_url)
            self.assertIn("X_REAL_POST_DISABLED_BY_PRODUCT_POLICY", denied.message)

    def test_cli_blocks_X_before_initializing_real_sheets(self):
        import publish_queue
        with patch.object(
            publish_queue, "_init_sheets",
            side_effect=AssertionError("Sheets must never be opened"),
        ) as sheets, self.assertRaises(SystemExit) as stopped:
            publish_queue._run_real_post_mode(
                SimpleNamespace(
                    mock=False, use_sheets=True, dry_run=False,
                    confirm_real_post=True, queue_id_filter="q1",
                    account_id="night_scout", max_real_posts=1,
                    platform="x", platforms="x", status="READY", limit=1,
                ),
            )
        self.assertEqual(stopped.exception.code, 2)
        self.assertEqual(sheets.call_count, 0)

    def test_dry_run_X_validation_still_available(self):
        result = XPublisher().publish(
            "offline synthetic preview", account={"account_id": "night_scout"},
            derivative={}, queue_item={"queue_id": "q1"}, dry_run=True,
        )
        self.assertTrue(result.dry_run)
        self.assertTrue(result.success)
        self.assertIsNone(result.external_post_id)


class CutoverPlanOfflineTests(unittest.TestCase):
    def test_inventory_complete_but_never_authorizes_migration(self):
        plan = build_plan()
        self.assertEqual(plan["status"], "CUTOVER_BLOCKED")
        self.assertFalse(plan["release_approval"])
        self.assertFalse(plan["operational_source_selected"])
        self.assertGreater(plan["files"], 50)
        self.assertGreater(plan["mutation_sites"], 100)
        self.assertEqual(plan["mutation_sites"], plan["not_migrated_sites"])
        self.assertEqual(
            sum(plan["workstream_counts"].values()), plan["mutation_sites"],
        )
        self.assertTrue(all(
            row["migration_state"] == "NOT_MIGRATED"
            and row["external_side_effect_approved"] is False
            and row["cutover_authorized"] is False
            for row in plan["routes"]
        ))
        self.assertTrue(any(
            row["file"] == "scripts/process_threads_queue.py"
            and row["workstream"] == "P0_PUBLISH_AND_RESULT"
            for row in plan["routes"]
        ))
        self.assertTrue(any(
            row["file"] == "scripts/sync_publication_review.py"
            and row["workstream"] == "P0_QUEUE_AND_APPROVAL"
            for row in plan["routes"]
        ))

    def test_false_positive_owner_approval_not_inferred_from_fake_zero_writers(self):
        clean = build_plan(baseline={}, current={})
        self.assertEqual(clean["mutation_sites"], 0)
        self.assertEqual(clean["status"], "CUTOVER_BLOCKED")
        self.assertFalse(clean["release_approval"])

    def test_manifest_drift_blocks(self):
        with self.assertRaisesRegex(CutoverPlanBlocked, "BASELINE_DRIFT"):
            build_plan(
                baseline={"scripts/other.py": {"append_row": 1}},
                current={"scripts/other.py": {"append_row": 2}},
            )

    def test_no_output_in_worktree_and_cli_always_blocked(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "readonly-plan.json"
            with patch.object(sys, "argv", [
                "plan_legacy_writer_cutover", "--output", str(destination),
            ]), patch("builtins.print"):
                rc = main()
            self.assertEqual(rc, 2)
            import json
            saved = json.loads(destination.read_text(encoding="utf-8"))
            self.assertEqual(saved["status"], "CUTOVER_BLOCKED")
            self.assertEqual(saved["mutation_sites"], saved["not_migrated_sites"])
            self.assertNotIn("publish_authorized", str(saved))


if __name__ == "__main__":
    unittest.main()
