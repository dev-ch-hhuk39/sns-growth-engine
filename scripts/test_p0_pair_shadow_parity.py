#!/usr/bin/env python3
"""Offline, adversarial two-export parity and blocked SQLite shadow tests."""
from __future__ import annotations

import copy
import importlib.util
import io
import json
import os
import sqlite3
import stat
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from p0_pair_shadow_parity import (  # noqa: E402
    P0PairBlocked, authorize_posting, compare_snapshots,
    initialize_ephemeral_shadow, stage_in_ephemeral_sqlite,
)

NOW = datetime(2026, 10, 14, 1, 0, tzinfo=timezone.utc)
Q1 = {
    "queue_id": "ns_1600_oct14", "account_id": "night_scout",
    "slot_id": "ns_1600", "platform": "threads", "status": "READY",
    "media_required": "false", "has_media": False, "media_type": "text",
}
Q2 = {
    **Q1, "queue_id": "lm_1700_oct14", "account_id": "liver_manager",
    "slot_id": "lm_1700",
}
Q3 = {**Q1, "queue_id": "ns_already_posted", "status": "POSTED"}
P3 = {
    "queue_id": Q3["queue_id"], "account_id": "night_scout",
    "status": "POSTED", "real_post": "true",
    "verification_status": "READ_AFTER_WRITE_PASS",
    "external_post_id": "p_private_123456789",
}


def shot(rows=None, posts=None, at=NOW):
    return {
        "schema": "sns_operational_queue_offline_metadata_v1",
        "observed_at": at.isoformat(),
        "queue_rows": copy.deepcopy([Q1, Q2, Q3] if rows is None else rows),
        "posted_rows": copy.deepcopy([P3] if posts is None else posts),
    }


def pair(before=None, after=None, *, now=NOW + timedelta(seconds=35), writers=165):
    return compare_snapshots(
        shot() if before is None else before,
        shot(at=NOW + timedelta(seconds=20)) if after is None else after,
        as_of=now, legacy_writer_sites=writers,
    )


class ParityTests(unittest.TestCase):
    def test_stable_two_capture_metadata_compares_without_auth(self):
        result = pair()
        self.assertEqual(result.report["pair_status"], "PASS_LOCAL_METADATA_ONLY")
        self.assertEqual(result.report["status"], "CUTOVER_BLOCKED")
        self.assertFalse(result.report["production_cutover_authorized"])
        self.assertFalse(result.report["publish_authorized"])
        self.assertEqual(result.report["posted_rows"], 1)
        self.assertEqual(result.report["queue_rows"], 3)
        self.assertEqual(result.report["legacy_write_calls_remaining"], 165)
        self.assertFalse(result.report["export_completeness_attested"])
        self.assertNotIn("ns_1600_oct14", json.dumps(result.report))
        self.assertNotIn("p_private_123456789", json.dumps(result.report))

    def test_row_order_irrelevant_but_metadata_identity_is_not(self):
        a = shot(at=NOW + timedelta(seconds=20))
        a["queue_rows"].reverse()
        self.assertEqual(pair(after=a).report["pair_status"], "PASS_LOCAL_METADATA_ONLY")

    def test_changed_media_marker_blocks_second_capture(self):
        a = shot(at=NOW + timedelta(seconds=20))
        a["queue_rows"][0]["media_type"] = "image"
        report = pair(after=a).report
        self.assertEqual(report["pair_status"], "BLOCKED")
        self.assertIn("P0_PAIR_ROW_METADATA_CHANGED", report["findings"])
        self.assertIn("P0_MEDIA_RIGHTS_NOT_IN_METADATA", report["findings"])

    def test_changed_slot_and_source_route_block(self):
        for field, value in (("slot_id", "new_slot"), ("content_route", "unreviewed")):
            with self.subTest(field=field):
                a = shot(at=NOW + timedelta(seconds=20))
                a["queue_rows"][0][field] = value
                self.assertIn("P0_PAIR_ROW_METADATA_CHANGED", pair(after=a).report["findings"])

    def test_new_queue_or_removed_queue_blocks(self):
        for rows in ([Q1, Q2], [Q1, Q2, Q3, {**Q2, "queue_id": "lm_new_row"}]):
            a = shot(rows=rows, at=NOW + timedelta(seconds=20))
            result = pair(after=a).report
            self.assertIn("P0_PAIR_IDENTITY_SET_CHANGED", result["findings"])
            self.assertEqual(result["pair_status"], "BLOCKED")

    def test_posted_result_id_change_blocks(self):
        a = shot(at=NOW + timedelta(seconds=20))
        a["posted_rows"][0]["external_post_id"] = "changed_external_provider_id"
        result = pair(after=a).report
        self.assertIn("P0_PAIR_ROW_METADATA_CHANGED", result["findings"])

    def test_post_added_removed_results_block(self):
        a = shot(posts=[], at=NOW + timedelta(seconds=20))
        result = pair(after=a).report
        self.assertIn("P0_PAIR_IDENTITY_SET_CHANGED", result["findings"])
        self.assertIn("P0_POSTED_QUEUE_RESULT_NOT_UNIQUE", result["findings"])

    def test_account_crossing_blocks_both_parity_and_preflight(self):
        a = shot(at=NOW + timedelta(seconds=20))
        a["queue_rows"][0]["account_id"] = "liver_manager"
        self.assertIn("P0_PAIR_ROW_METADATA_CHANGED", pair(after=a).report["findings"])

    def test_stale_processing_or_uncertain_blocks(self):
        b = shot(rows=[{**Q1, "status": "PUBLISH_OUTCOME_UNVERIFIED"}])
        a = shot(rows=[{**Q1, "status": "PUBLISH_OUTCOME_UNVERIFIED"}],
                 posts=[], at=NOW + timedelta(seconds=20))
        report = pair(before=b, after=a).report
        self.assertEqual(report["pair_status"], "BLOCKED")
        self.assertIn("P0_EXISTING_OUTCOME_UNVERIFIED", report["findings"])

    def test_beauty_is_reported_but_not_import_authorized(self):
        b = shot(rows=[{**Q1, "account_id": "beauty_account"}], posts=[])
        a = shot(rows=[{**Q1, "account_id": "beauty_account"}], posts=[],
                 at=NOW + timedelta(seconds=20))
        report = pair(before=b, after=a).report
        self.assertEqual(report["pair_status"], "BLOCKED")
        self.assertEqual(report["account_counts"]["beauty_account"]["before_queue"], 1)
        self.assertIn("P0_BEAUTY_ACCOUNT_NOT_IN_REHEARSAL_SCOPE", report["findings"])

    def test_no_independent_capture_timestamp_blocks(self):
        report = pair(after=shot(at=NOW)).report
        self.assertIn("P0_PAIR_CAPTURE_INTERVAL_INVALID", report["findings"])

    def test_backward_or_too_far_clock_blocks(self):
        for ts in (NOW - timedelta(seconds=1), NOW + timedelta(seconds=50)):
            report = pair(after=shot(at=ts)).report
            self.assertIn("P0_PAIR_CAPTURE_INTERVAL_INVALID", report["findings"])

    def test_expired_first_or_second_snapshot_blocks(self):
        report = pair(now=NOW + timedelta(seconds=135)).report
        self.assertIn("P0_PAIR_FIRST_CAPTURE_EXPIRED", report["findings"])
        self.assertIn("P0_PAIR_LATEST_CAPTURE_EXPIRED", report["findings"])

    def test_missing_ready_media_declaration_blocks(self):
        b = shot()
        a = shot(at=NOW + timedelta(seconds=20))
        del b["queue_rows"][0]["media_required"]
        del a["queue_rows"][0]["media_required"]
        self.assertIn("P0_READY_MEDIA_SCOPE_UNDECLARED", pair(before=b, after=a).report["findings"])

    def test_unsafe_snapshot_fields_never_pass(self):
        b = shot()
        b["queue_rows"][0]["public_post_text"] = "SECRET_PRIVATE_BODY"
        with self.assertRaises(Exception):
            pair(before=b)

    def test_no_rows_cannot_prove_snapshot_completeness(self):
        b = shot(rows=[], posts=[])
        a = shot(rows=[], posts=[], at=NOW + timedelta(seconds=20))
        result = pair(before=b, after=a).report
        self.assertIn("P0_PAIR_EMPTY_QUEUE_NOT_PROOF", result["findings"])

    def test_invalid_writer_count_refused(self):
        with self.assertRaises(Exception):
            pair(writers=-1)


class ShadowTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:", isolation_level=None)
        self.db.execute("PRAGMA foreign_keys=ON")
        initialize_ephemeral_shadow(self.db, explicitly_for_tests=True)
        self.check = pair()

    def tearDown(self):
        self.db.close()

    def test_clean_pair_stages_and_exact_readback(self):
        result = stage_in_ephemeral_sqlite(
            self.check, self.db, as_of=NOW + timedelta(seconds=35),
            explicit_temporary_rehearsal=True,
        )
        self.assertEqual(result["shadow_status"], "VERIFIED_TEMPORARY_METADATA_ONLY")
        self.assertEqual(result["temporary_shadow_queue_rows"], 3)
        self.assertEqual(result["temporary_shadow_posted_rows"], 1)
        self.assertTrue(result["shadow_manifest_verified"])
        self.assertFalse(result["publish_authorized"])
        self.assertEqual(result["operational_db_writes"], 0)
        dump = "\n".join(self.db.iterdump())
        self.assertNotIn(Q1["queue_id"], dump)
        self.assertNotIn(P3["external_post_id"], dump)
        self.assertNotIn("ns_1600", dump)

    def test_replay_stages_another_blocked_batch_not_live(self):
        self.assertEqual(stage_in_ephemeral_sqlite(
            self.check, self.db, as_of=NOW + timedelta(seconds=35),
            explicit_temporary_rehearsal=True,
        )["shadow_status"], "VERIFIED_TEMPORARY_METADATA_ONLY")
        self.assertFalse(stage_in_ephemeral_sqlite(
            self.check, self.db, as_of=NOW + timedelta(seconds=35),
            explicit_temporary_rehearsal=True,
        )["publish_authorized"])
        # No operational table or outbound client becomes available.
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM sns_p0_shadow_batch").fetchone()[0], 2)

    def test_denies_disk_databases_even_inside_temp_dir(self):
        with tempfile.TemporaryDirectory() as folder:
            db = sqlite3.connect(str(Path(folder) / "production_looking.db"),
                                 isolation_level=None)
            db.execute("PRAGMA foreign_keys=ON")
            try:
                with self.assertRaisesRegex(P0PairBlocked, "TEMPORARY_DATABASE_REQUIRED"):
                    initialize_ephemeral_shadow(db, explicitly_for_tests=True)
            finally:
                db.close()

    def test_attached_database_denied(self):
        self.db.execute("ATTACH DATABASE ':memory:' AS malicious_extra")
        with self.assertRaisesRegex(P0PairBlocked, "TEMPORARY_DATABASE_REQUIRED"):
            stage_in_ephemeral_sqlite(
                self.check, self.db, as_of=NOW + timedelta(seconds=35),
            explicit_temporary_rehearsal=True,
            )

    def test_foreign_keys_must_be_enforced(self):
        self.db.execute("PRAGMA foreign_keys=OFF")
        with self.assertRaisesRegex(P0PairBlocked, "FOREIGN_KEYS_REQUIRED"):
            stage_in_ephemeral_sqlite(
                self.check, self.db, as_of=NOW + timedelta(seconds=35),
            explicit_temporary_rehearsal=True,
            )

    def test_unreviewed_candidate_pair_does_not_stage(self):
        a = shot(at=NOW + timedelta(seconds=20))
        a["queue_rows"][0]["media_type"] = "video"
        bad = pair(after=a)
        with self.assertRaisesRegex(P0PairBlocked, "PAIR_NOT_STABLE"):
            stage_in_ephemeral_sqlite(bad, self.db,
                                      as_of=NOW + timedelta(seconds=35),
                                      explicit_temporary_rehearsal=True)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM sns_p0_shadow_batch").fetchone()[0], 0)

    def test_missing_explicit_flag_denied(self):
        with self.assertRaisesRegex(P0PairBlocked, "EXPLICIT_REHEARSAL_REQUIRED"):
            stage_in_ephemeral_sqlite(self.check, self.db, as_of=NOW + timedelta(seconds=35))

    def test_commit_failure_rolls_back_atomically(self):
        with self.assertRaisesRegex(P0PairBlocked, "INJECTED_TEST_FAILURE"):
            stage_in_ephemeral_sqlite(
                self.check, self.db, as_of=NOW + timedelta(seconds=35),
            explicit_temporary_rehearsal=True,
                test_failpoint="BEFORE_COMMIT",
            )
        self.assertFalse(self.db.in_transaction)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM sns_p0_shadow_batch").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM sns_p0_shadow_queue").fetchone()[0], 0)

    def test_immutable_rows_reject_update_and_delete(self):
        stage_in_ephemeral_sqlite(self.check, self.db, as_of=NOW + timedelta(seconds=35), explicit_temporary_rehearsal=True)
        for statement in (
            "UPDATE sns_p0_shadow_queue SET status='POSTED'",
            "DELETE FROM sns_p0_shadow_queue",
            "DELETE FROM sns_p0_shadow_batch",
            "UPDATE sns_p0_shadow_batch SET disposition='STAGED_BLOCKED'",
        ):
            with self.subTest(statement=statement), self.assertRaises(sqlite3.IntegrityError):
                self.db.execute(statement)

    def test_source_mutation_after_preflight_does_not_change_captured_rows(self):
        before = shot()
        after = shot(at=NOW + timedelta(seconds=20))
        check = pair(before=before, after=after)
        before["queue_rows"][0]["media_type"] = "video"
        after["queue_rows"][0]["media_type"] = "video"
        self.assertEqual(stage_in_ephemeral_sqlite(
            check, self.db, as_of=NOW + timedelta(seconds=35),
            explicit_temporary_rehearsal=True,
        )["shadow_status"], "VERIFIED_TEMPORARY_METADATA_ONLY")

    def test_mutation_of_staged_evidence_after_preflight_is_blocked(self):
        self.check.before_queue[0]["media_type"] = "video"
        self.check.after_queue[0]["media_type"] = "video"
        with self.assertRaisesRegex(P0PairBlocked, "P0_SHADOW_PREFLIGHT_EVIDENCE_CHANGED"):
            stage_in_ephemeral_sqlite(
                self.check, self.db, as_of=NOW + timedelta(seconds=35),
                explicit_temporary_rehearsal=True,
            )
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM sns_p0_shadow_batch").fetchone()[0], 0)

    def test_stale_check_cannot_stage_later_even_when_snapshots_match(self):
        with self.assertRaisesRegex(P0PairBlocked, "P0_SHADOW_PRECHECK_EXPIRED"):
            stage_in_ephemeral_sqlite(
                self.check, self.db, as_of=NOW + timedelta(minutes=2),
                explicit_temporary_rehearsal=True,
            )
        self.assertEqual(
            self.db.execute("SELECT COUNT(*) FROM sns_p0_shadow_batch").fetchone()[0], 0,
        )

    def test_never_returns_publishing_authorization(self):
        with self.assertRaisesRegex(P0PairBlocked, "NEVER_PUBLISH_AUTHORITY"):
            authorize_posting(provider="threads")

    def test_failed_readback_cannot_be_false_success(self):
        self.db.execute("""CREATE TRIGGER inject_bad_shadow_after_insert
            AFTER INSERT ON sns_p0_shadow_queue
            BEGIN SELECT RAISE(ABORT,'synthetic provider/storage failure'); END""")
        with self.assertRaisesRegex(P0PairBlocked, "SQLITE_OUTCOME_UNKNOWN"):
            stage_in_ephemeral_sqlite(self.check, self.db,
                                      as_of=NOW + timedelta(seconds=35),
                                      explicit_temporary_rehearsal=True)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM sns_p0_shadow_batch").fetchone()[0], 0)

    def test_duplicate_queue_id_with_crossaccount_never_stages(self):
        a = shot(rows=[Q1, {**Q1, "account_id": "liver_manager"}], posts=[],
                 at=NOW + timedelta(seconds=20))
        with self.assertRaises(P0PairBlocked):
            pair(after=a)


class CLISafety(unittest.TestCase):
    def load_cli(self, snapshot):
        audit = types.ModuleType("audit_queue_authority_cutover")
        class AuditBlocked(Exception):
            pass
        audit.AuditBlocked = AuditBlocked
        audit.legacy_writer_snapshot = lambda: {"sites": 165}
        audit.load_offline_snapshot = lambda path: snapshot[str(path)]
        source = Path(__file__).resolve().parent / "rehearse_p0_pair_shadow.py"
        with patch.dict(sys.modules, {"audit_queue_authority_cutover": audit}):
            spec = importlib.util.spec_from_file_location("phase6ai_pair_cli_test", source)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        return module

    def test_cli_readonly_pair_can_stage_only_memory(self):
        with tempfile.TemporaryDirectory() as folder:
            before = str(Path(folder) / "before.json")
            after = str(Path(folder) / "after.json")
            source = {before: shot(), after: shot(at=NOW + timedelta(seconds=20))}
            module = self.load_cli(source)
            with patch.object(sys, "argv", [
                "phase6ai", "--before", before, "--after", after, "--simulate",
            ]), patch.object(module, "datetime") as clock:
                clock.now.return_value = NOW + timedelta(seconds=35)
                result = module.report(module.argparse.Namespace(
                    before=Path(before), after=Path(after), simulate=True,
                ))
            self.assertEqual(result["shadow_status"], "VERIFIED_TEMPORARY_METADATA_ONLY")
            self.assertFalse(result["production_cutover_authorized"])
            self.assertEqual(result["provider_calls"], 0)

    def test_cli_never_accepts_apply_or_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            before = str(Path(folder) / "before.json")
            after = str(Path(folder) / "after.json")
            source = {before: shot(), after: shot(at=NOW + timedelta(seconds=20))}
            module = self.load_cli(source)
            report = Path(folder) / "report.json"
            args = ["phase6ai", "--before", before, "--after", after, "--simulate", "--output", str(report)]
            with patch.object(sys, "argv", args), patch.object(module, "datetime") as clock, redirect_stdout(io.StringIO()):
                clock.now.return_value = NOW + timedelta(seconds=35)
                self.assertEqual(module.main(), 2)
            data = json.loads(report.read_text(encoding="utf-8"))
            self.assertFalse(data["publish_authorized"])
            self.assertEqual(stat.S_IMODE(os.stat(report).st_mode), 0o600)
            with patch.object(sys, "argv", args), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as stopped:
                    module.main()
            self.assertEqual(stopped.exception.code, 2)
            with patch.object(sys, "argv", ["phase6ai", "--before", before,
                         "--after", after, "--simulate", "--apply"]), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as bad:
                    module.main()
            self.assertEqual(bad.exception.code, 2)

    def test_cli_requires_two_separate_absolute_files(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "before.json"
            module = self.load_cli({str(path): shot()})
            with self.assertRaisesRegex(P0PairBlocked, "TWO_SEPARATE_ABSOLUTE"):
                module.report(module.argparse.Namespace(
                    before=path, after=path, simulate=True,
                ))


if __name__ == "__main__":
    unittest.main()
