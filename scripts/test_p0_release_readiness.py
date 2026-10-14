#!/usr/bin/env python3
"""Off-network integration tests for the Phase 6AH–6AL cutover *denial*."""
from __future__ import annotations

import copy
import importlib.util
import io
import json
import os
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
from p0_release_readiness import P0ReleaseBlocked, run_rehearsal  # noqa: E402
from test_p0_pair_shadow_parity import Q1, Q2, Q3, P3, NOW, shot  # noqa: E402


class BlockedCAS(Exception):
    pass


class FakeCASLedger:
    mode = "normal"
    instances = []

    def __init__(self, db):
        self.rows = {}
        self.calls = []
        self.instances.append(self)

    def observe(self, *, account_id, queue_id, source_sha256, **kwargs):
        if FakeCASLedger.mode == "io_failure":
            raise RuntimeError("NEVER REPEAT A PRIVATE TOKEN")
        self.rows[queue_id] = "OBSERVED_BLOCKED"
        self.calls.append("observe")
        return {"status": "OBSERVED_BLOCKED",
                "revision": 1, "head_sha256": "a" * 64,
                "publish_authorized": FakeCASLedger.mode == "bad_observe",
                "sheets_write_allowed": False}

    def claim(self, *, queue_id, **kwargs):
        self.calls.append("claim")
        if self.rows.get(queue_id) != "OBSERVED_BLOCKED":
            if FakeCASLedger.mode == "allow_replay":
                return {"status": "CLAIMED_BLOCKED", "dispatch_allowed": False}
            raise BlockedCAS("not eligible for retry")
        self.rows[queue_id] = "CLAIMED_BLOCKED"
        return {"status": "CLAIMED_BLOCKED", "revision": 2,
                "head_sha256": "b" * 64,
                "dispatch_allowed": FakeCASLedger.mode == "bad_claim",
                "publish_authorized": False, "sheets_write_allowed": False}

    def quarantine(self, *, queue_id, **kwargs):
        self.calls.append("quarantine")
        self.rows[queue_id] = "OUTCOME_UNKNOWN_BLOCKED"
        return {"status": "CLAIMED_BLOCKED" if FakeCASLedger.mode == "bad_unknown"
                else "OUTCOME_UNKNOWN_BLOCKED",
                "revision": 3, "head_sha256": "c" * 64,
                "publish_authorized": False,
                "dispatch_allowed": False, "sheets_write_allowed": False}

    def inspect(self, *, queue_id):
        return {"status": self.rows[queue_id]}


class FakeCASModule:
    P0RehearsalBlocked = BlockedCAS
    P0QueueRehearsal = FakeCASLedger
    schema_calls = 0

    @classmethod
    def initialize_rehearsal_schema(cls, db, *, explicit_local_test_only):
        assert explicit_local_test_only
        assert db.execute("PRAGMA database_list").fetchone()[2] == ""
        cls.schema_calls += 1


def frozen_plan(*, p0=71, other=94):
    return {
        "status": "CUTOVER_BLOCKED",
        "release_approval": False,
        "operational_source_selected": False,
        "mutation_sites": p0 + other,
        "not_migrated_sites": p0 + other,
        "workstream_counts": {"P0_PUBLISH_AND_RESULT": p0,
                              "P1_METRICS_AND_FEEDBACK": other},
    }


def run(*, before=None, after=None, now=None, plan=None, module=FakeCASModule):
    return run_rehearsal(
        shot() if before is None else before,
        shot(at=NOW + timedelta(seconds=20)) if after is None else after,
        as_of=NOW + timedelta(seconds=35) if now is None else now,
        legacy_plan=frozen_plan() if plan is None else plan,
        cas_module=module,
    )


class OfflineReadinessTests(unittest.TestCase):
    def setUp(self):
        FakeCASLedger.mode = "normal"
        FakeCASLedger.instances = []
        FakeCASModule.schema_calls = 0

    def test_complete_local_chain_never_enables_production(self):
        report = run()
        self.assertEqual(report["status"], "CUTOVER_BLOCKED")
        self.assertEqual(report["local_rehearsal_status"], "PASS_LOCAL_NOT_PRODUCTION")
        self.assertEqual(report["shadow_status"], "PASS_LOCAL_MEMORY_ONLY")
        self.assertEqual(report["cas_status"], "PASS_LOCAL_BLOCKED_CAS_ONLY")
        self.assertEqual(report["ready_candidate_count"], 2)
        self.assertEqual(report["cas_unknown_outcome_quarantined_count"], 2)
        self.assertEqual(report["legacy_p0_mutation_calls_remaining"], 71)
        self.assertEqual(report["legacy_all_mutation_calls_remaining"], 165)
        self.assertEqual(FakeCASModule.schema_calls, 1)
        self.assertEqual(len(FakeCASLedger.instances), 1)
        self.assertEqual(FakeCASLedger.instances[0].calls.count("claim"), 4)
        for field in ("production_cutover_authorized", "publish_authorized",
                      "sheets_write_authorized", "operational_sqlite_write_authorized",
                      "external_writers_frozen", "media_rights_verified"):
            self.assertIs(report[field], False)
        self.assertEqual(report["provider_call_count"], 0)
        self.assertEqual(report["external_write_count"], 0)
        for text in (Q1["queue_id"], Q2["queue_id"], P3["external_post_id"]):
            self.assertNotIn(text, json.dumps(report))

    def test_second_capture_changed_blocks_every_shadow_and_cas_action(self):
        changed = shot(at=NOW + timedelta(seconds=20))
        changed["queue_rows"][0]["slot_id"] = "unreviewed_changed_slot"
        report = run(after=changed)
        self.assertEqual(report["status"], "CUTOVER_BLOCKED")
        self.assertEqual(report["local_rehearsal_status"], "NOT_PROVEN")
        self.assertEqual(report["shadow_status"], "NOT_STAGED")
        self.assertEqual(report["cas_status"], "NOT_TESTED")
        self.assertIn("P0_RELEASE_PAIR_FAILED", report["findings"])
        self.assertEqual(FakeCASModule.schema_calls, 0)

    def test_identity_mismatch_or_media_rights_blocks_before_staging(self):
        for changed in (
            {**Q1, "account_id": "liver_manager"},
            {**Q1, "media_type": "video", "media_required": "true"},
            {**Q1, "status": "PUBLISH_OUTCOME_UNVERIFIED"},
        ):
            after = shot(at=NOW + timedelta(seconds=20))
            after["queue_rows"][0] = changed
            with self.subTest(changed=changed):
                self.assertIn("P0_RELEASE_PAIR_FAILED", run(after=after)["findings"])
        self.assertEqual(FakeCASModule.schema_calls, 0)

    def test_stale_pair_rejected(self):
        report = run(now=NOW + timedelta(minutes=7))
        self.assertIn("P0_RELEASE_PAIR_FAILED", report["findings"])
        self.assertEqual(FakeCASModule.schema_calls, 0)

    def test_no_ready_candidate_never_claims_local_cas(self):
        before = shot(rows=[Q3], posts=[P3])
        after = shot(rows=[Q3], posts=[P3], at=NOW + timedelta(seconds=20))
        report = run(before=before, after=after)
        self.assertEqual(report["shadow_status"], "PASS_LOCAL_MEMORY_ONLY")
        self.assertEqual(report["cas_status"], "NOT_EXERCISED_NO_READY_CANDIDATES")
        self.assertEqual(report["local_rehearsal_status"], "NOT_PROVEN")
        self.assertEqual(FakeCASModule.schema_calls, 0)

    def test_large_candidate_set_must_not_launch_cas(self):
        rows = [{**Q1, "queue_id": f"candidate_{i:04d}"} for i in range(257)]
        before = shot(rows=rows, posts=[])
        after = shot(rows=rows, posts=[], at=NOW + timedelta(seconds=20))
        report = run(before=before, after=after)
        self.assertEqual(report["findings"], ["P0_RELEASE_REHEARSAL_SCOPE_TOO_LARGE"])
        self.assertEqual(FakeCASModule.schema_calls, 0)

    def test_invalid_or_falsely_approved_legacy_plan_rejected(self):
        cases = (
            {**frozen_plan(), "release_approval": True},
            {**frozen_plan(), "status": "PASS"},
            {**frozen_plan(), "not_migrated_sites": 0},
            {**frozen_plan(), "workstream_counts": {"P0_X": 1}},
            {**frozen_plan(), "operational_source_selected": True},
        )
        for plan in cases:
            with self.subTest(plan=plan), self.assertRaises(P0ReleaseBlocked):
                run(plan=plan)

    def test_zero_legacy_sites_never_means_production_granted(self):
        report = run(plan=frozen_plan(p0=0, other=0))
        self.assertEqual(report["status"], "CUTOVER_BLOCKED")
        self.assertFalse(report["production_cutover_authorized"])
        self.assertIn("OPERATOR_APPROVED_SINGLE_WRITER_CUTOVER_MISSING",
                      report["mandatory_production_blockers"])

    def test_unsafe_cas_observe_is_fail_closed(self):
        FakeCASLedger.mode = "bad_observe"
        report = run()
        self.assertIn("P0_RELEASE_CAS_OBSERVE_UNSAFE", report["findings"])
        self.assertEqual(report["local_rehearsal_status"], "NOT_PROVEN")

    def test_unsafe_cas_claim_is_fail_closed(self):
        FakeCASLedger.mode = "bad_claim"
        report = run()
        self.assertIn("P0_RELEASE_CAS_CLAIM_UNSAFE", report["findings"])

    def test_unsafe_cas_unknown_is_fail_closed(self):
        FakeCASLedger.mode = "bad_unknown"
        report = run()
        self.assertIn("P0_RELEASE_CAS_UNKNOWN_UNSAFE", report["findings"])

    def test_cas_replay_allowed_is_fail_closed(self):
        FakeCASLedger.mode = "allow_replay"
        report = run()
        self.assertIn("P0_RELEASE_CAS_RETRY_NOT_BLOCKED", report["findings"])

    def test_exception_does_not_leak_private_details(self):
        FakeCASLedger.mode = "io_failure"
        report = run()
        self.assertEqual(report["findings"], ["P0_RELEASE_LOCAL_INTEGRATION_UNVERIFIABLE"])
        self.assertNotIn("PRIVATE TOKEN", json.dumps(report))

    def test_missing_installed_cas_blocks(self):
        with patch("p0_release_readiness._get_cas_module",
                   side_effect=P0ReleaseBlocked("P0_CAS_LOCAL_MODULE_UNAVAILABLE")):
            report = run(module=None)
        self.assertEqual(report["findings"], ["P0_CAS_LOCAL_MODULE_UNAVAILABLE"])
        self.assertEqual(report["shadow_status"], "PASS_LOCAL_MEMORY_ONLY")
        self.assertEqual(report["local_rehearsal_status"], "NOT_PROVEN")

    def test_snapshot_dictionaries_are_not_mutated(self):
        original = shot()
        later = shot(at=NOW + timedelta(seconds=20))
        before_copy, after_copy = copy.deepcopy(original), copy.deepcopy(later)
        run(before=original, after=later)
        self.assertEqual(original, before_copy)
        self.assertEqual(later, after_copy)


class CLISafetyTests(unittest.TestCase):
    def import_cli(self):
        path = Path(__file__).resolve().parent / "rehearse_p0_release_candidate.py"
        spec = importlib.util.spec_from_file_location("p0_release_cli_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_no_apply_is_accepted(self):
        cli = self.import_cli()
        with patch.object(sys, "argv", ["rehearse", "--simulate", "--apply"]), \
                redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stop:
            cli.main()
        self.assertEqual(stop.exception.code, 2)

    def test_requires_simulate_and_independent_absolute_files(self):
        cli = self.import_cli()
        with tempfile.TemporaryDirectory() as folder:
            first = Path(folder) / "a.json"
            second = Path(folder) / "b.json"
            first.write_text("{}")
            os.link(first, second)
            with self.assertRaises(P0ReleaseBlocked):
                cli.report(types.SimpleNamespace(before=first, after=second,
                                                 simulate=True))
            with self.assertRaises(P0ReleaseBlocked):
                cli.report(types.SimpleNamespace(before=first, after=first,
                                                 simulate=True))
            with self.assertRaises(P0ReleaseBlocked):
                cli.report(types.SimpleNamespace(before=first, after=second,
                                                 simulate=False))

    def test_cli_error_scrubbed_without_provider_module(self):
        cli = self.import_cli()
        with tempfile.TemporaryDirectory() as folder:
            before = Path(folder) / "one.json"
            after = Path(folder) / "two.json"
            before.write_text("SECRET TEXT")
            after.write_text("SECRET TEXT")
            with patch.object(sys, "argv", ["rehearse", "--before", str(before),
                                      "--after", str(after), "--simulate"]), \
                    redirect_stdout(io.StringIO()) as out:
                self.assertEqual(cli.main(), 2)
            self.assertIn("CUTOVER_BLOCKED", out.getvalue())
            self.assertNotIn("SECRET TEXT", out.getvalue())

    def test_cli_integrates_source_parser_inventory_and_blocked_cas(self):
        cli = self.import_cli()
        with tempfile.TemporaryDirectory() as folder:
            first = Path(folder) / "before.json"
            second = Path(folder) / "after.json"
            first.write_text(json.dumps(shot()))
            second.write_text(json.dumps(shot(at=NOW + timedelta(seconds=20))))
            parser_stub = types.ModuleType("audit_queue_authority_cutover")
            parser_stub.load_offline_snapshot = lambda path: json.loads(path.read_text())
            inventory_stub = types.ModuleType("plan_legacy_writer_cutover")
            inventory_stub.build_plan = frozen_plan
            module_stub = types.ModuleType("p0_queue_cas_rehearsal")
            module_stub.initialize_rehearsal_schema = FakeCASModule.initialize_rehearsal_schema
            module_stub.P0QueueRehearsal = FakeCASLedger
            module_stub.P0RehearsalBlocked = BlockedCAS
            args = types.SimpleNamespace(before=first, after=second, simulate=True)
            with patch.dict(sys.modules, {
                "audit_queue_authority_cutover": parser_stub,
                "plan_legacy_writer_cutover": inventory_stub,
                "p0_queue_cas_rehearsal": module_stub,
            }), patch.object(cli, "datetime") as mocked_clock:
                mocked_clock.now.return_value = NOW + timedelta(seconds=35)
                result = cli.report(args)
            self.assertEqual(result["local_rehearsal_status"], "PASS_LOCAL_NOT_PRODUCTION")
            self.assertEqual(result["cas_unknown_outcome_quarantined_count"], 2)
            self.assertEqual(result["status"], "CUTOVER_BLOCKED")
            self.assertFalse(result["publish_authorized"])

    def test_cli_source_drift_blocks_without_cas_import(self):
        cli = self.import_cli()
        with tempfile.TemporaryDirectory() as folder:
            first = Path(folder) / "before.json"
            second = Path(folder) / "after.json"
            first.write_text(json.dumps(shot()))
            changed = shot(at=NOW + timedelta(seconds=20))
            changed["queue_rows"][0]["slot_id"] = "unreviewed"
            second.write_text(json.dumps(changed))
            parser_stub = types.ModuleType("audit_queue_authority_cutover")
            parser_stub.load_offline_snapshot = lambda path: json.loads(path.read_text())
            inventory_stub = types.ModuleType("plan_legacy_writer_cutover")
            inventory_stub.build_plan = frozen_plan
            module_stub = types.ModuleType("p0_queue_cas_rehearsal")
            module_stub.P0QueueRehearsal = FakeCASLedger
            with patch.dict(sys.modules, {
                "audit_queue_authority_cutover": parser_stub,
                "plan_legacy_writer_cutover": inventory_stub,
                "p0_queue_cas_rehearsal": module_stub,
            }), patch.object(cli, "datetime") as mocked_clock:
                mocked_clock.now.return_value = NOW + timedelta(seconds=35)
                result = cli.report(types.SimpleNamespace(
                    before=first, after=second, simulate=True,
                ))
            self.assertEqual(result["findings"], ["P0_RELEASE_PAIR_FAILED"])
            self.assertEqual(result["shadow_status"], "NOT_STAGED")
            self.assertEqual(result["cas_status"], "NOT_TESTED")

    def test_report_write_only_once_0600(self):
        cli = self.import_cli()
        with tempfile.TemporaryDirectory() as folder:
            before, after = Path(folder)/"a.json", Path(folder)/"b.json"
            before.write_text("untrusted")
            after.write_text("untrusted")
            report = Path(folder) / "result.json"
            args = ["rehearse", "--before", str(before), "--after", str(after),
                    "--simulate", "--output", str(report)]
            with patch.object(sys, "argv", args), redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(), 2)
            self.assertEqual(stat.S_IMODE(report.stat().st_mode), 0o600)
            self.assertFalse(json.loads(report.read_text())["publish_authorized"])
            with patch.object(sys, "argv", args), redirect_stdout(io.StringIO()), \
                    redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stop:
                cli.main()
            self.assertEqual(stop.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
