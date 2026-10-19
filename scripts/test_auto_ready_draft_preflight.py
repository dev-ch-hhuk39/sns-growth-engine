#!/usr/bin/env python3
"""Regression tests for zero-side-effect AUTO_READY rollout preflight."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import auto_ready_draft_preflight as preflight


class AutoReadyDraftPreflightTests(unittest.TestCase):
    def test_draft_only_is_explicit_owner_hold(self):
        self.assertEqual(preflight.evaluate_policy({
            "schema_version": "content_quality_v2", "draft_only": True
        }), ("OWNER_REVIEW_REQUIRED", 2))

    def test_only_actual_boolean_false_can_pass(self):
        self.assertEqual(preflight.evaluate_policy({
            "schema_version": "content_quality_v2", "draft_only": False
        }), ("QUALITY_ROLLOUT_PREFLIGHT_PASS", 0))
        for value in ("false", 0, "", None):
            self.assertEqual(preflight.evaluate_policy({
                "schema_version": "content_quality_v2", "draft_only": value
            }), ("CONTENT_QUALITY_V2_POLICY_UNVERIFIED", 2))

    def test_unknown_schema_fails_closed(self):
        for value in (None, [], {}, {"schema_version": "v0", "draft_only": False}):
            self.assertEqual(preflight.evaluate_policy(value)[1], 2)

    def test_current_policy_remains_owner_review_only(self):
        policy = json.loads(preflight.DEFAULT_POLICY.read_text(encoding="utf-8"))
        self.assertEqual(preflight.evaluate_policy(policy), ("OWNER_REVIEW_REQUIRED", 2))

    def test_cli_never_discloses_policy_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "policy.json"
            p.write_text(json.dumps({
                "schema_version": "content_quality_v2",
                "draft_only": True, "secret_like_field": "DO_NOT_ECHO"
            }), encoding="utf-8")
            with patch("builtins.print") as output:
                rc = preflight.main(["--policy", str(p)])
            self.assertEqual(rc, 2)
            printed = " ".join(str(c.args[0]) for c in output.call_args_list)
            self.assertIn("OWNER_REVIEW_REQUIRED", printed)
            self.assertIn("PROVIDER_CALLS=0", printed)
            self.assertNotIn("DO_NOT_ECHO", printed)

    def test_missing_or_invalid_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "policy.json"
            with patch("builtins.print") as output:
                rc = preflight.main(["--policy", str(p)])
            self.assertEqual(rc, 2)
            self.assertIn("POLICY_UNVERIFIED", str(output.call_args_list))
            p.write_text("{invalid", encoding="utf-8")
            with patch("builtins.print") as output:
                rc = preflight.main(["--policy", str(p)])
            self.assertEqual(rc, 2)
            self.assertIn("POLICY_UNVERIFIED", str(output.call_args_list))


if __name__ == "__main__":
    unittest.main()
