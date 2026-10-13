#!/usr/bin/env python3
"""Local SQLite-chain and Sheets-metadata cutover audit regression cases."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import closing, redirect_stderr
import io
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

import audit_queue_authority_cutover as audit  # noqa: E402
import test_media_mirror_outbox as fixtures  # noqa: E402

KEY, NOW = fixtures.KEY, fixtures.NOW


class CutoverReadOnlyAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.MirrorOutboxTests.setUpClass()
        cls.inventory = audit.legacy_writer_snapshot()

    def setUp(self):
        self.fixture = fixtures.MirrorOutboxTests(
            methodName="test_enqueued_in_same_writer_transaction",
        )
        self.fixture.setUp()
        self.fixture.prepare()
        self.protected = audit.inspect_protected_sqlite(self.fixture.db)
        self.snapshot = {
            "schema": audit.SCHEMA,
            "observed_at": NOW.isoformat(),
            "queue_rows": [{
                "queue_id": KEY[2], "account_id": KEY[0], "slot_id": KEY[1],
                "platform": "threads", "status": "WAITING_REVIEW",
                "media_required": "true", "media_asset_id": "asset_sample",
            }],
            "posted_rows": [],
        }

    def tearDown(self):
        self.fixture.db.close()
        self.fixture.tmp.cleanup()

    def assess(self, snapshot=None, protected=None, *, now=NOW):
        return audit.evaluate(
            snapshot if snapshot is not None else self.snapshot,
            protected if protected is not None else self.protected,
            self.inventory, now=now,
        )

    def codes(self, result):
        return {x["code"] for x in result["findings"]}

    def test_protected_chain_matches_exact_media_metadata_but_cannot_activate(self):
        result = self.assess()
        self.assertEqual(result["local_parity_status"], "PASS")
        self.assertFalse(result["production_cutover_authorized"])
        self.assertFalse(result["automatic_media_publish_authorized"])
        self.assertEqual(result["status"], "CUTOVER_BLOCKED")
        self.assertGreater(result["legacy_mutation_sites"], 0)
        self.assertNotIn("clip_001", json.dumps(result))
        self.assertNotIn("asset_sample", json.dumps(result))
        self.assertNotIn("private_original_evidence", json.dumps(result))

    def test_copied_media_ready_is_safety_block_even_with_protected_shadow(self):
        self.snapshot["queue_rows"][0]["status"] = "READY"
        result = self.assess()
        self.assertIn("LEGACY_MEDIA_DELIVERY_NOT_AUTHORIZED", self.codes(result))

    def test_missing_shadow_or_protected_row_detected(self):
        result = self.assess(protected={
            "status": "METADATA_CHAIN_CHECKED_LOCAL", "entries": {},
        })
        self.assertIn("PROTECTED_MEDIA_NOT_IN_SQLITE", self.codes(result))
        without_sheet = self.assess({**self.snapshot, "queue_rows": []})
        self.assertIn("PROTECTED_ROW_ABSENT_FROM_OFFLINE_SHEETS",
                      self.codes(without_sheet))

    def test_ambiguous_and_cross_account_results_are_blocking(self):
        row = self.snapshot["queue_rows"][0]
        row["status"] = "POSTED"
        self.snapshot["posted_rows"] = [{
            "queue_id": KEY[2], "account_id": "night_scout", "status": "POSTED",
            "real_post": "true", "external_post_id": "123",
            "verification_status": "READ_AFTER_WRITE_PASS",
        }]
        result = self.assess()
        self.assertIn("POSTED_RESULT_CROSS_ACCOUNT_COLLISION", self.codes(result))
        self.assertIn("POSTED_RESULT_NOT_UNIQUELY_VERIFIED", self.codes(result))
        self.assertIn("LEGACY_MEDIA_DELIVERY_NOT_AUTHORIZED", self.codes(result))
        # Never serialize provider identifiers or the operational queue ID.
        self.assertNotIn("123", json.dumps(result))

    def test_duplicate_queue_identity_is_global_not_per_account(self):
        self.snapshot["queue_rows"].append({
            "queue_id": KEY[2], "account_id": "night_scout",
            "slot_id": "ns_1600_original", "platform": "threads",
            "status": "WAITING_REVIEW",
        })
        result = self.assess()
        self.assertIn("GLOBAL_QUEUE_ID_COLLISION", self.codes(result))

    def test_unknown_outcome_and_outbox_not_settled(self):
        self.snapshot["queue_rows"][0]["status"] = "PUBLISH_OUTCOME_UNVERIFIED"
        entries = dict(self.protected["entries"])
        entries[KEY] = {**entries[KEY], "outbox_state": "UNCERTAIN_BLOCKED"}
        result = self.assess(protected={**self.protected, "entries": entries})
        self.assertIn("OPERATIONAL_OUTCOME_UNRESOLVED", self.codes(result))
        self.assertIn("PROTECTED_MIRROR_OUTCOME_NOT_SETTLED", self.codes(result))

    def test_freshness_rules_preserve_fail_closed(self):
        stale = self.assess(
            now=NOW + timedelta(hours=2),
        )
        self.assertIn("OFFLINE_SNAPSHOT_NOT_FRESH", self.codes(stale))
        self.assertIn("PROTECTED_OBSERVATION_EXPIRED", self.codes(stale))

    def test_protected_chain_corruption_is_not_silently_accepted(self):
        self.fixture.db.execute(
            "UPDATE sns_media_managed_queue_heads SET queue_sha256=?",
            ("f" * 64,),
        )
        with self.assertRaises(audit.AuditBlocked):
            audit.inspect_protected_sqlite(self.fixture.db)

    def test_database_is_read_only_when_opened_from_path(self):
        with closing(audit.open_readonly_db(Path(self.fixture.path))) as db:
            self.assertEqual(db.execute("PRAGMA query_only").fetchone()[0], 1)
            self.assertEqual(audit.inspect_protected_sqlite(db)["entries"].keys(),
                             self.protected["entries"].keys())
            with self.assertRaises(Exception):
                db.execute("UPDATE sns_media_managed_queue_heads SET version=2")

    def test_untrusted_snapshot_rejects_caption_token_url_and_unexpected_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "snapshot.json"
            path.write_text(json.dumps(self.snapshot), encoding="utf-8")
            self.assertEqual(audit.load_offline_snapshot(path), self.snapshot)
            for field in ("public_post_text", "api_key", "media_url"):
                bad = json.loads(json.dumps(self.snapshot))
                bad["queue_rows"][0][field] = "PRIVATE_TOKEN_HIDDEN"
                path.write_text(json.dumps(bad), encoding="utf-8")
                with self.subTest(field=field), self.assertRaisesRegex(
                    audit.AuditBlocked, "UNSAFE_FIELD",
                ):
                    audit.load_offline_snapshot(path)

    def test_global_unreviewed_writer_baseline_remains_unapproved(self):
        report = self.assess()
        self.assertIn("LEGACY_WRITERS_NOT_CUT_OVER",
                      report["mandatory_activation_blockers"])
        self.assertGreaterEqual(self.inventory["files"], 1)
        self.assertGreaterEqual(self.inventory["sites"], 1)
        self.assertEqual(self.inventory["source"],
                         "REVIEW_BASELINE_NOT_CUTOVER_AUTHORITY")

    def test_cli_cannot_accept_apply_and_never_contacts_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_path = Path(tmp) / "minimal.json"
            snapshot_path.write_text(json.dumps(self.snapshot), encoding="utf-8")
            with patch.object(sys, "argv", [
                "audit_queue_authority_cutover", "--snapshot",
                str(snapshot_path), "--protected-db", self.fixture.path,
                "--apply",
            ]), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stopped:
                audit.main()
            self.assertEqual(stopped.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
