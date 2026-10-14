#!/usr/bin/env python3
"""Pure, offline, provider-free adversarial P0 metadata preflight checks."""
from __future__ import annotations

import copy
import importlib.util
import io
import json
import os
import stat
import tempfile
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from p0_snapshot_cutover_preflight import (  # noqa: E402
    P0PreflightBlocked, inspect, simulate_to_rehearsal,
)

NOW = datetime(2026, 10, 14, 0, 0, tzinfo=timezone.utc)
QUEUE = {
    "queue_id": "night_1600_1014", "account_id": "night_scout",
    "slot_id": "ns_slot_1", "platform": "threads", "status": "READY",
    "media_required": "false", "has_media": False, "media_type": "text",
}


def sample(rows=None, posts=None, observed_at=NOW):
    return {
        "schema": "sns_operational_queue_offline_metadata_v1",
        "observed_at": observed_at.isoformat(),
        "queue_rows": copy.deepcopy([QUEUE] if rows is None else rows),
        "posted_rows": copy.deepcopy([] if posts is None else posts),
    }


def posted(q=None, **changes):
    q = q or QUEUE
    return {**{
        "queue_id": q["queue_id"], "account_id": q["account_id"],
        "status": "POSTED", "real_post": "true",
        "verification_status": "READ_AFTER_WRITE_PASS",
        "external_post_id": "post_abcdefghi",
    }, **changes}


class FakeRehearsal:
    def __init__(self, *, status="OBSERVED_BLOCKED"):
        self.calls = []
        self.status = status

    def observe(self, **kw):
        self.calls.append(kw)
        return {"status": self.status, "publish_authorized": False,
                "sheets_write_allowed": False}


class P0PreflightSafety(unittest.TestCase):
    def plan(self, snapshot=None, at=NOW, writers=165):
        return inspect(sample() if snapshot is None else snapshot,
                       as_of=at, legacy_writer_sites=writers)

    def codes(self, snapshot=None, at=NOW):
        return {item["code"] for item in self.plan(snapshot, at=at).report["findings"]}

    def test_valid_ready_text_stages_only_blocked_local_metadata(self):
        plan = self.plan()
        self.assertEqual(plan.report["parity_status"], "PASS_LOCAL_METADATA_ONLY")
        self.assertEqual(plan.report["candidate_count"], 1)
        self.assertEqual(plan.report["status"], "CUTOVER_BLOCKED")
        self.assertFalse(plan.report["publish_authorized"])
        self.assertFalse(plan.report["production_cutover_authorized"])
        self.assertFalse(plan.report["sheets_write_authorized"])
        self.assertFalse(plan.report["sqlite_operational_write_authorized"])
        self.assertEqual(plan.report["legacy_write_calls_remaining"], 165)
        self.assertEqual(plan.report["per_account_counts"]["night_scout"]["ready_rows"], 1)
        self.assertEqual(plan.report["per_account_counts"]["beauty_account"]["queue_rows"], 0)
        self.assertNotIn(QUEUE["queue_id"], json.dumps(plan.report))

    def test_both_p0_accounts_can_be_rehearsed_in_same_snapshot(self):
        other = {**QUEUE, "account_id": "liver_manager", "queue_id": "liver_slot_1"}
        result = self.plan(sample([QUEUE, other]))
        self.assertEqual(len(result.candidates), 2)
        self.assertEqual(result.report["parity_status"], "PASS_LOCAL_METADATA_ONLY")

    def test_published_queue_with_unique_verified_result_is_clean_metadata(self):
        queue = {**QUEUE, "status": "POSTED"}
        plan = self.plan(sample([queue], [posted()]))
        self.assertEqual(plan.report["parity_status"], "PASS_LOCAL_METADATA_ONLY")
        self.assertEqual(plan.report["candidate_count"], 0)

    def test_global_queue_collision_even_cross_account(self):
        other = {**QUEUE, "account_id": "liver_manager"}
        self.assertIn("P0_GLOBAL_QUEUE_ID_COLLISION",
                      self.codes(sample([QUEUE, other])))

    def test_post_cross_account_detected(self):
        self.assertIn("P0_POST_CROSS_ACCOUNT", self.codes(sample(
            [{**QUEUE, "status": "POSTED"}], [posted(account_id="liver_manager")]
        )))

    def test_duplicate_provider_post_id_global(self):
        other = {**QUEUE, "status": "POSTED", "queue_id": "another_q"}
        first = {**QUEUE, "status": "POSTED"}
        results = [posted(), posted(other)]
        self.assertIn("P0_EXTERNAL_POST_ID_COLLISION",
                      self.codes(sample([first, other], results)))

    def test_duplicate_posted_result_for_one_queue(self):
        self.assertIn("P0_POST_RESULT_DUPLICATE_QUEUE",
                      self.codes(sample([{**QUEUE, "status": "POSTED"}], [
                          posted(), posted(external_post_id="post_second"),
                      ])))

    def test_all_unknown_outcome_statuses_block(self):
        for status in (
            "PROCESSING", "POSTED_SAVE_UNVERIFIED", "POSTED_SAVE_FAILED",
            "PUBLISH_OUTCOME_UNVERIFIED",
        ):
            with self.subTest(status=status):
                self.assertIn("P0_EXISTING_OUTCOME_UNVERIFIED",
                              self.codes(sample([{**QUEUE, "status": status}])))

    def test_media_variants_block_even_if_ready(self):
        variants = [
            {"media_required": "true"}, {"has_media": True},
            {"media_asset_id": "asset_1"}, {"media_type": "video"},
            {"publisher_media_type": "image"},
        ]
        for mutation in variants:
            with self.subTest(mutation=mutation):
                self.assertIn("P0_MEDIA_RIGHTS_NOT_IN_METADATA",
                              self.codes(sample([{**QUEUE, **mutation}])))

    def test_beauty_requires_separate_approval_even_when_text_ready(self):
        self.assertIn("P0_BEAUTY_ACCOUNT_NOT_IN_REHEARSAL_SCOPE",
                      self.codes(sample([{**QUEUE, "account_id": "beauty_account"}])))

    def test_unknown_account_and_non_threads_are_blocking(self):
        self.assertIn("P0_ACCOUNT_UNKNOWN",
                      self.codes(sample([{**QUEUE, "account_id": "random_account"}])))
        self.assertIn("P0_PLATFORM_NOT_IN_SCOPE",
                      self.codes(sample([{**QUEUE, "platform": "x"}])))

    def test_snapshot_future_and_age_boundaries(self):
        self.assertIn("P0_OFFLINE_SNAPSHOT_STALE_OR_FUTURE",
                      self.codes(sample(observed_at=NOW - timedelta(minutes=6))))
        self.assertIn("P0_OFFLINE_SNAPSHOT_STALE_OR_FUTURE",
                      self.codes(sample(observed_at=NOW + timedelta(seconds=121))))
        self.assertIn("P0_REHEARSAL_OBSERVATION_NOT_FRESH",
                      self.codes(sample(observed_at=NOW - timedelta(seconds=100))))

    def test_sensitive_columns_or_non_strict_types_refused(self):
        for bad in (
            {**QUEUE, "public_post_text": "SECRET_MESSAGE"},
            {**QUEUE, "access_token": "SECRET_MESSAGE"},
            {**QUEUE, "media_url": "https://example.invalid/private"},
            {**QUEUE, "has_media": 1},
        ):
            with self.subTest(keys=list(bad)), self.assertRaisesRegex(
                P0PreflightBlocked, "P0_SNAPSHOT_UNSAFE_COLUMNS",
            ):
                self.plan(sample([bad]))

    def test_missing_timestamp_or_naive_clock_refused(self):
        with self.assertRaises(P0PreflightBlocked):
            self.plan(sample(observed_at=NOW.replace(tzinfo=None)))
        with self.assertRaises(P0PreflightBlocked):
            self.plan(at=NOW.replace(tzinfo=None))

    def test_missing_ready_slot_refused(self):
        self.assertIn("P0_READY_SLOT_MISSING",
                      self.codes(sample([{**QUEUE, "slot_id": ""}])))

    def test_invalid_queue_ids_and_ambiguous_media_scope_block(self):
        bad_ids = ("q", "=HYPERLINK(fake)", "x" * 140)
        for qid in bad_ids:
            with self.subTest(qid=qid[:10]):
                self.assertIn("P0_QUEUE_ID_NOT_REHEARSAL_SAFE",
                              self.codes(sample([{**QUEUE, "queue_id": qid}])))
        self.assertIn("P0_READY_MEDIA_SCOPE_UNDECLARED",
                      self.codes(sample([{k:v for k,v in QUEUE.items()
                                          if k != "media_required"}])))
        self.assertIn("P0_READY_MEDIA_SCOPE_UNDECLARED",
                      self.codes(sample([{**QUEUE, "media_required": "unknown"}])))

    def test_posted_queue_without_exact_result_refused(self):
        self.assertIn("P0_POSTED_QUEUE_RESULT_NOT_UNIQUE",
                      self.codes(sample([{**QUEUE, "status": "POSTED"}])))

    def test_result_orphan_and_missing_verification_refused(self):
        self.assertIn("P0_POST_ORPHAN_OR_AMBIGUOUS",
                      self.codes(sample([QUEUE], [posted(queue_id="unknown") ])))
        codes = self.codes(sample([{**QUEUE, "status": "POSTED"}], [
            posted(verification_status="NOT_VERIFIED", external_post_id=""),
        ]))
        self.assertIn("P0_POST_RESULT_PROOF_MISSING", codes)

    def test_result_for_nonposted_queue_is_refused(self):
        self.assertIn("P0_POST_WITH_NONPOSTED_QUEUE",
                      self.codes(sample([QUEUE], [posted()])))

    def test_untrusted_writers_input_refused(self):
        for value in (-1, True, "165"):
            with self.assertRaises(P0PreflightBlocked):
                self.plan(writers=value)

    def test_source_digest_deterministic_and_changed_with_snapshot(self):
        first = self.plan()
        second = self.plan()
        self.assertEqual(first.candidates, second.candidates)
        changed = self.plan(sample([{**QUEUE, "slot_id": "ns_changed_slot"}]))
        self.assertNotEqual(first.candidates[0][2], changed.candidates[0][2])

    def test_rehearsal_refuses_a_non_p0_writer_type(self):
        fake_module = types.ModuleType("p0_queue_cas_rehearsal")
        fake_module.P0QueueRehearsal = FakeRehearsal
        with patch.dict(sys.modules, {"p0_queue_cas_rehearsal": fake_module}):
            with self.assertRaisesRegex(P0PreflightBlocked, "NON_REHEARSAL_WRITER_REJECTED"):
                simulate_to_rehearsal(self.plan(), ledger=object(), as_of=NOW)

    def test_blocked_preflight_never_calls_ledger(self):
        fake_module = types.ModuleType("p0_queue_cas_rehearsal")
        fake_module.P0QueueRehearsal = FakeRehearsal
        writer = FakeRehearsal()
        with patch.dict(sys.modules, {"p0_queue_cas_rehearsal": fake_module}):
            with self.assertRaisesRegex(P0PreflightBlocked, "BLOCKED_BY_FINDINGS"):
                simulate_to_rehearsal(
                    self.plan(sample([{**QUEUE, "media_type": "video"}])),
                    ledger=writer, as_of=NOW,
                )
        self.assertEqual(writer.calls, [])

    def test_successful_observations_are_still_permanently_blocked(self):
        fake_module = types.ModuleType("p0_queue_cas_rehearsal")
        fake_module.P0QueueRehearsal = FakeRehearsal
        writer = FakeRehearsal()
        plan = self.plan()
        with patch.dict(sys.modules, {"p0_queue_cas_rehearsal": fake_module}):
            report = simulate_to_rehearsal(plan, ledger=writer, as_of=NOW)
        self.assertEqual(report["simulated_observation_count"], 1)
        self.assertEqual(writer.calls[0]["source_sha256"], plan.candidates[0][2])
        self.assertEqual(writer.calls[0]["account_id"], "night_scout")
        self.assertFalse(report["publish_authorized"])
        self.assertNotIn(QUEUE["queue_id"], json.dumps(report))

    def test_unblocked_plan_rejects_expired_after_planning(self):
        fake_module = types.ModuleType("p0_queue_cas_rehearsal")
        fake_module.P0QueueRehearsal = FakeRehearsal
        writer = FakeRehearsal()
        with patch.dict(sys.modules, {"p0_queue_cas_rehearsal": fake_module}):
            with self.assertRaisesRegex(P0PreflightBlocked, "SOURCE_STALE"):
                simulate_to_rehearsal(self.plan(), ledger=writer,
                                      as_of=NOW + timedelta(minutes=3))
        self.assertFalse(writer.calls)

    def test_malicious_fake_ledger_success_status_rejected(self):
        fake_module = types.ModuleType("p0_queue_cas_rehearsal")
        fake_module.P0QueueRehearsal = FakeRehearsal
        with patch.dict(sys.modules, {"p0_queue_cas_rehearsal": fake_module}):
            with self.assertRaisesRegex(P0PreflightBlocked, "RESULT_NOT_BLOCKED"):
                simulate_to_rehearsal(self.plan(),
                    ledger=FakeRehearsal(status="PUBLISH_AUTHORIZED"), as_of=NOW)


class SnapshotCLIContract(unittest.TestCase):
    def test_read_only_cli_runs_synthetic_temp_only_and_never_returns_success(self):
        snapshot = sample(observed_at=datetime.now(timezone.utc))
        audit_stub = types.ModuleType("audit_queue_authority_cutover")
        class AuditBlocked(Exception):
            pass
        audit_stub.AuditBlocked = AuditBlocked
        audit_stub.load_offline_snapshot = lambda unused_path: snapshot
        audit_stub.legacy_writer_snapshot = lambda: {"sites": 165}
        p0_stub = types.ModuleType("p0_queue_cas_rehearsal")
        class P0RehearsalBlocked(Exception):
            pass
        class SyntheticOnlyLedger(FakeRehearsal):
            def __init__(self, _db):
                super().__init__()
        p0_stub.P0QueueRehearsal = SyntheticOnlyLedger
        p0_stub.P0RehearsalBlocked = P0RehearsalBlocked
        p0_stub.initialize_rehearsal_schema = lambda _db, explicit_local_test_only: None
        source = Path(__file__).parent / "rehearse_p0_snapshot_cutover.py"
        with patch.dict(sys.modules, {
            "audit_queue_authority_cutover": audit_stub,
            "p0_queue_cas_rehearsal": p0_stub,
        }):
            spec = importlib.util.spec_from_file_location("phase6ah_cli_synthetic", source)
            self.assertIsNotNone(spec)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            with tempfile.TemporaryDirectory() as folder:
                dest = Path(folder) / "report.json"
                with patch.object(sys, "argv", [
                    "rehearse_p0_snapshot_cutover", "--snapshot", "/tmp/fake-input.json",
                    "--simulate", "--output", str(dest),
                ]), redirect_stdout(io.StringIO()) as out:
                    self.assertEqual(module.main(), 2)
                report = json.loads(dest.read_text(encoding="utf-8"))
                self.assertEqual(report["simulated_observation_count"], 1)
                self.assertEqual(report["status"], "CUTOVER_BLOCKED")
                self.assertEqual(report["provider_calls"], 0)
                self.assertFalse(report["production_cutover_authorized"])
                self.assertNotIn(QUEUE["queue_id"], out.getvalue())
                self.assertEqual(stat.S_IMODE(os.stat(dest).st_mode), 0o600)
                with patch.object(sys, "argv", [
                    "rehearse_p0_snapshot_cutover", "--snapshot", "/tmp/fake-input.json",
                    "--simulate", "--output", str(dest),
                ]), redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                    with self.assertRaises(SystemExit) as second:
                        module.main()
                self.assertEqual(second.exception.code, 2)
                with patch.object(sys, "argv", [
                    "rehearse_p0_snapshot_cutover", "--snapshot", "/tmp/fake-input.json",
                    "--apply",
                ]), redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as apply:
                        module.main()
                self.assertEqual(apply.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
