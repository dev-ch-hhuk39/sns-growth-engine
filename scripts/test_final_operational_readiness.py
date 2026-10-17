#!/usr/bin/env python3
"""Adversarial disk-evidence and side-effect contracts for the final report."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import final_operational_readiness as final
from audit_queue_authority_cutover import SCHEMA

NOW = datetime(2026, 10, 17, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]


class FinalOperationalReadinessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "metadata.json"
        self.snapshot = {
            "schema": SCHEMA, "observed_at": NOW.isoformat(),
            "queue_rows": [{"queue_id": "private_queue", "account_id": "night_scout",
                            "platform": "threads", "slot_id": "private_slot",
                            "status": "READY", "media_required": False}],
            "posted_rows": [],
        }
        inventory = patch.object(final, "legacy_writer_snapshot", return_value={"sites": 123})
        inventory.start()
        self.addCleanup(inventory.stop)

    def assess(self, snapshot=None):
        self.path.write_text(json.dumps(self.snapshot if snapshot is None else snapshot))
        before = self.path.read_bytes()
        result = final.build_report(self.path, now=NOW)
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(result["status"], "CUTOVER_BLOCKED")
        for key in ("production_ready", "publish_authorized", "production_cutover_authorized",
                    "sheets_write_authorized", "operational_sqlite_write_authorized"):
            self.assertIs(result[key], False)
        self.assertTrue(set(final.HARD_BLOCKERS).issubset(result["mandatory_production_blockers"]))
        self.assertNotIn("private_", json.dumps(result))
        return result

    def test_clean_metadata_is_not_production_proof(self):
        result = self.assess()
        self.assertEqual(result["snapshot_status"], "CHECKED_UNATTESTED_METADATA_ONLY")
        self.assertEqual(result["queue_rows_count"], 1)
        self.assertEqual(result["legacy_mutation_sites"], 123)
        self.assertEqual(result["findings"], [])

    def test_missing_and_malformed_are_not_ready(self):
        for path in (None, self.path):
            result = final.build_report(path, now=NOW)
            self.assertFalse(result["production_ready"])
            self.assertEqual(result["snapshot_status"], "NOT_VERIFIED")
            self.assertTrue(result["findings"])
        for raw in ('{"private_secret":', 'null', '[]', '{"status":"PASS"}'):
            self.path.write_text(raw)
            result = final.build_report(self.path, now=NOW)
            self.assertEqual(result["findings"], ["OFFLINE_SNAPSHOT_UNVERIFIABLE"])
            self.assertFalse(result["production_ready"])
            self.assertNotIn("private_secret", json.dumps(result))

    def test_forged_success_claims_are_not_evidence(self):
        for claim in (True, False, "true", "PASS", 1):
            with self.subTest(claim=claim):
                bad = {**self.snapshot, "production_ready": claim, "publish_authorized": claim}
                self.assertEqual(self.assess(bad)["snapshot_status"], "NOT_VERIFIED")

    def test_false_post_proof_is_blocked(self):
        self.snapshot["queue_rows"][0]["status"] = "POSTED"
        self.snapshot["posted_rows"] = [{
            "queue_id": "private_queue", "account_id": "night_scout", "status": "POSTED",
            "real_post": False, "external_post_id": "private_provider_id",
            "verification_status": "READ_AFTER_WRITE_PASS",
        }]
        self.assertIn("P0_POST_RESULT_PROOF_MISSING", self.assess()["findings"])

    def test_stale_future_and_invalid_time_fail_closed(self):
        for stamp in ((NOW - timedelta(days=1)).isoformat(),
                      (NOW + timedelta(days=1)).isoformat(), "private_bad_time"):
            with self.subTest(stamp=stamp):
                self.snapshot["observed_at"] = stamp
                self.assertNotEqual(self.assess()["snapshot_status"],
                                    "CHECKED_UNATTESTED_METADATA_ONLY")

    def test_queue_ambiguity_identity_beauty_and_media_are_reported(self):
        cases = [({"status": "PUBLISH_OUTCOME_UNVERIFIED"}, "P0_EXISTING_OUTCOME_UNVERIFIED"),
                 ({"account_id": "private_unknown"}, "P0_ACCOUNT_UNKNOWN"),
                 ({"account_id": "beauty_account"}, "P0_BEAUTY_ACCOUNT_NOT_IN_REHEARSAL_SCOPE"),
                 ({"media_required": True}, "P0_MEDIA_RIGHTS_NOT_IN_METADATA")]
        for fields, code in cases:
            snapshot = copy.deepcopy(self.snapshot)
            snapshot["queue_rows"][0].update(fields)
            with self.subTest(code=code):
                self.assertIn(code, self.assess(snapshot)["findings"])
        self.snapshot["queue_rows"].append(dict(self.snapshot["queue_rows"][0]))
        self.assertIn("P0_GLOBAL_QUEUE_ID_COLLISION", self.assess()["findings"])

    def test_inventory_failure_does_not_become_zero_writers(self):
        with patch.object(final, "legacy_writer_snapshot", side_effect=ValueError("private_secret")):
            result = self.assess()
        self.assertIsNone(result["legacy_mutation_sites"])
        self.assertEqual(result["snapshot_status"], "NOT_VERIFIED")

    def test_symlink_is_rejected(self):
        target = Path(self.tmp.name) / "other.json"
        target.write_text(json.dumps(self.snapshot))
        self.path.symlink_to(target)
        result = final.build_report(self.path, now=NOW)
        self.assertEqual(result["findings"], ["OFFLINE_SNAPSHOT_UNVERIFIABLE"])

    def test_real_cli_has_no_network_process_database_or_file_writes(self):
        self.snapshot["observed_at"] = datetime.now(timezone.utc).isoformat()
        self.path.write_text(json.dumps(self.snapshot))
        # Fresh interpreter: monitor imports and execution, not just declared
        # counters. Record attempted operations even if broad handlers catch them.
        harness = '''
import os, runpy, sys
violations = []
def audit(event, args):
    forbidden = event.startswith(("socket.", "subprocess.", "sqlite3.connect"))
    if event == "open":
        forbidden |= bool(args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
    if forbidden:
        violations.append(event)
        raise RuntimeError("SIDE_EFFECT_FORBIDDEN")
sys.addaudithook(audit)
sys.path.insert(0, "scripts")
sys.argv = ["scripts/final_operational_readiness.py", "--snapshot", sys.argv[1]]
try:
    runpy.run_path(sys.argv[0], run_name="__main__")
except SystemExit as exc:
    assert exc.code == 2
assert not violations, violations
'''
        completed = subprocess.run([sys.executable, "-B", "-c", harness, str(self.path)],
                                   cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["snapshot_status"], "CHECKED_UNATTESTED_METADATA_ONLY")
        self.assertGreater(result["legacy_mutation_sites"], 0)
        self.assertFalse(result["production_ready"])


if __name__ == "__main__":
    unittest.main()
