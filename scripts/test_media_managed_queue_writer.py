#!/usr/bin/env python3
"""Offline Phase 5B-6F queue writer and read-only Sheets mirror contract."""
from __future__ import annotations

import sqlite3
import sys
import unittest
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from media_managed_queue_writer import (  # noqa: E402
    ManagedQueueBlocked, MediaManagedQueueWriter,
    SQLiteManagedOperationalSnapshot, ZERO, initialize_managed_queue_schema,
)
from media_review_canonical_adapter import CanonicalProtectedReviewReader  # noqa: E402
from media_review_protected_evidence import ProtectedEvidenceVault  # noqa: E402
from media_review_trusted_precommit import PrecommitBlocked  # noqa: E402
from media_shadow_queue_authority import ShadowQueueBlocked  # noqa: E402
from media_dispatch_guard import MediaDispatchGuard  # noqa: E402
import test_media_shadow_queue_authority as fixtures  # noqa: E402

KEY, NOW, ISSUER = fixtures.KEY, fixtures.NOW, fixtures.ISSUER
BIND_ID = "manage_bind_20261012_000001"


class ManagedQueueWriterTests(fixtures.ShadowQueueAuthorityTests):
    """Includes inherited 49 full protected-review and shadow tests."""

    def setUp(self):
        super().setUp()
        initialize_managed_queue_schema(self.db)
        self.writer = MediaManagedQueueWriter(self.db)

    def bind(self, *, operation=BIND_ID, **overrides):
        args = {
            "key": KEY, "operation_id": operation,
            "verifier": self.verifier, "bearer": self.bearer,
            "trusted_issuer": ISSUER, "canonical": self.local(),
            "as_of": NOW,
        }
        args.update(overrides)
        return self.writer.bind(**args)

    def prepare(self):
        self.capture()
        return self.bind()

    def managed_reader(self):
        return CanonicalProtectedReviewReader(
            source=SQLiteManagedOperationalSnapshot(
                db=self.db, vault=self.vault, clock=lambda: self.read_clock,
            ), vault=self.vault,
        )

    def change(self, action, *, version=1, sha=None, operation=None, **overrides):
        if sha is None:
            sha = self.writer.inspect(key=KEY)["writer_event_sha256"]
        args = {
            "key": KEY, "operation_id": (
                operation or f"manage_{action.lower()}_20261012_00001"
            ),
            "action": action, "expected_version": version,
            "expected_head_sha256": sha, "verifier": self.verifier,
            "bearer": self.bearer, "trusted_issuer": ISSUER, "as_of": NOW,
        }
        args.update(overrides)
        return self.writer.transition(**args)

    def test_migration_requires_shadow_and_review_database(self):
        db = sqlite3.connect(":memory:", isolation_level=None)
        try:
            with self.assertRaisesRegex(
                ManagedQueueBlocked, "managed_migration_missing_parent",
            ):
                initialize_managed_queue_schema(db)
        finally:
            db.close()

    def test_managed_write_needs_existing_fresh_signed_shadow(self):
        with self.assertRaises(ManagedQueueBlocked):
            self.bind()
        self.assertEqual(self.count("sns_media_managed_queue_heads"), 0)

    def test_bound_queue_is_nonauthorizing_and_mirror_is_sanitized(self):
        bound = self.prepare()
        self.assertEqual(bound["status"], "MANAGED_BLOCKED")
        for flag in ("publish_authorized", "dispatch_allowed",
                     "sheets_write_allowed", "mirror_published"):
            self.assertIs(bound[flag], False)
        self.assertEqual(self.count("sns_media_managed_queue_heads"), 1)
        self.assertEqual(self.count("sns_media_managed_queue_events"), 1)
        self.assertEqual(self.count("sns_media_sheet_mirror_previews"), 1)
        preview = self.writer.mirror_previews()
        self.assertEqual(len(preview), 1)
        self.assertTrue(preview[0]["view_only"])
        self.assertFalse(preview[0]["publish_authorized"])
        self.assertNotIn("public_post_text", str(preview))
        self.assertNotIn(self.jwt, str(preview))
        self.assertNotIn("private_original_evidence", str(preview))
        self.assertEqual(self.managed_reader().load_current(*KEY).queue,
                         self.context.queue)

    def test_unauthorized_reviewer_cannot_bind_or_control_queue(self):
        self.capture()
        for overridden in (
            {"bearer": "Bearer fake"},
            {"bearer": "Bearer " + self.token({"aud": "invalid"})},
            {"verifier": None},
            {"trusted_issuer": "https://invalid.example"},
        ):
            with self.subTest(override=list(overridden)), self.assertRaises(ManagedQueueBlocked):
                self.bind(**overridden)
        self.assertEqual(self.count("sns_media_managed_queue_events"), 0)
        self.bind()
        with self.assertRaises(ManagedQueueBlocked):
            self.change("HOLD", bearer="Bearer fake")
        self.assertEqual(self.count("sns_media_managed_queue_events"), 1)

    def test_external_json_canonical_adapter_cannot_bind(self):
        self.capture()
        with self.assertRaises(ManagedQueueBlocked):
            self.bind(canonical=self.external)
        self.assertEqual(self.count("sns_media_managed_queue_heads"), 0)

    def test_account_mismatch_and_invalid_operation_denied(self):
        self.capture()
        with self.assertRaises(Exception):
            self.bind(key=("night_scout", KEY[1], KEY[2]))
        with self.assertRaises(ManagedQueueBlocked):
            self.bind(operation="approve_all")
        self.assertFalse(self.count("sns_media_managed_queue_heads"))

    def test_no_shadow_refresh_allowed_after_managed_binding(self):
        self.prepare()
        info = self.shadow.inspect(key=KEY)
        with self.assertRaises(ShadowQueueBlocked):
            self.capture(
                operation="shadow_refresh_after_managed_20261012_00001",
                expected_version=info["shadow_version"],
                expected_head_sha256=info["shadow_event_sha256"],
            )
        self.assertEqual(self.count("sns_media_shadow_queue_events"), 1)

    def test_downstream_review_intent_dispatch_share_managed_queue(self):
        self.prepare()
        self.canonical = self.managed_reader()
        self.source_fixture.offline = True
        self.review_and_match()
        intent = self.reserve()
        self.assertEqual(intent["status"], "HELD_BLOCKED")
        staged = MediaDispatchGuard(self.db).stage(
            key=KEY, operation_id="dispatch_managed_20261012_00001",
            expected_intent_version=1,
            verifier=self.verifier, bearer=self.bearer,
            trusted_issuer=ISSUER, source=self.canonical, as_of=NOW,
        )
        self.assertEqual(staged["status"], "STAGED_BLOCKED")
        self.assertFalse(staged["publish_authorized"])
        self.assertFalse(staged["dispatch_allowed"])

    def test_operator_hold_blocks_internal_review_and_mirrors_latest_only(self):
        self.prepare()
        stopped = self.change("HOLD")
        self.assertEqual(stopped["status"], "HOLD_BLOCKED")
        with self.assertRaises(PrecommitBlocked):
            self.managed_reader().load_current(*KEY)
        preview = self.writer.mirror_previews()
        self.assertEqual(len(preview), 1)
        self.assertEqual(preview[0]["writer_version"], 2)
        self.assertEqual(preview[0]["writer_state"], "HOLD_BLOCKED")
        self.assertFalse(preview[0]["publish_authorized"])
        self.assertEqual(self.count("sns_media_sheet_mirror_previews"), 2)

    def test_terminal_archive_cannot_resume_or_rebind(self):
        self.prepare()
        hold = self.change("HOLD")
        archive = self.change(
            "ARCHIVE", version=2, sha=hold["writer_event_sha256"],
            operation="manage_archive_20261012_00002",
        )
        self.assertEqual(archive["status"], "ARCHIVED_BLOCKED")
        with self.assertRaises(ManagedQueueBlocked):
            self.change("HOLD", version=3,
                        sha=archive["writer_event_sha256"])
        with self.assertRaises(ManagedQueueBlocked):
            self.bind(operation="manage_duplicate_bind_20261012_001")
        self.assertEqual(self.count("sns_media_managed_queue_events"), 3)

    def test_review_ledger_exists_then_writer_rebind_is_forbidden(self):
        self.capture()
        self.canonical = self.local()
        self.review_and_match()
        with self.assertRaises(ManagedQueueBlocked):
            self.bind()
        self.assertEqual(self.count("sns_media_managed_queue_heads"), 0)

    def test_cas_mismatch_duplicate_operations_and_old_versions_rejected(self):
        self.prepare()
        with self.assertRaises(ManagedQueueBlocked):
            self.change("HOLD", sha=ZERO)
        with self.assertRaises(ManagedQueueBlocked):
            self.bind()
        self.change("HOLD")
        with self.assertRaises(ManagedQueueBlocked):
            self.change("HOLD", version=1)
        self.assertEqual(self.count("sns_media_managed_queue_events"), 2)

    def test_same_content_shadow_observation_needs_explicit_reconcile(self):
        self.prepare()
        head = self.shadow.inspect(key=KEY)
        unchanged = self.observe(
            version=head["shadow_version"],
            sha=head["shadow_event_sha256"],
        )
        self.assertEqual(unchanged["status"], "SHADOW_BLOCKED")
        with self.assertRaises(PrecommitBlocked):
            self.managed_reader().load_current(*KEY)
        synced = self.writer.reconcile_observation(
            key=KEY, operation_id="manage_reconcile_20261012_00001",
            expected_version=1, expected_head_sha256=(
                self.writer.inspect(key=KEY)["writer_event_sha256"]
            ), verifier=self.verifier, bearer=self.bearer,
            trusted_issuer=ISSUER, as_of=NOW,
        )
        self.assertEqual(synced["status"], "MANAGED_BLOCKED")
        self.assertEqual(synced["writer_version"], 2)
        self.assertEqual(self.managed_reader().load_current(*KEY).queue,
                         self.context.queue)
        self.assertEqual(self.writer.mirror_previews()[0]["writer_version"], 2)

    def test_shadow_drift_quarantines_future_read_and_reconcile(self):
        self.prepare()
        head = self.shadow.inspect(key=KEY)
        self.context.queue["public_post_text"] = "edited externally"
        self.observe(version=head["shadow_version"],
                     sha=head["shadow_event_sha256"])
        with self.assertRaises(ManagedQueueBlocked):
            self.writer.reconcile_observation(
                key=KEY, operation_id="manage_drift_sync_20261012_00001",
                expected_version=1,
                expected_head_sha256=self.writer.inspect(key=KEY)["writer_event_sha256"],
                verifier=self.verifier, bearer=self.bearer,
                trusted_issuer=ISSUER, as_of=NOW,
            )
        with self.assertRaises(PrecommitBlocked):
            self.managed_reader().load_current(*KEY)

    def test_rights_revocation_blocks_managed_read(self):
        self.prepare()
        ref = next(iter(self.context.evidence_by_id))
        self.vault.revoke(
            evidence_id=ref, bearer_token=self.bearer,
            verifier=self.verifier, trusted_issuer=ISSUER,
            operation_id="evop_managed_revoke_20261012_00001",
            expected_revision=1, as_of=NOW,
        )
        with self.assertRaises(PrecommitBlocked):
            self.managed_reader().load_current(*KEY)

    def test_expired_observation_blocks_managed_read(self):
        self.prepare()
        self.read_clock = NOW + timedelta(seconds=92)
        with self.assertRaises(PrecommitBlocked):
            self.managed_reader().load_current(*KEY)

    def test_mirror_row_tamper_is_detected_and_never_transmitted(self):
        self.prepare()
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "UPDATE sns_media_sheet_mirror_previews SET projection_json='{}'",
            )
        # A malicious direct INSERT cannot impersonate the latest event.
        self.db.execute(
            """INSERT INTO sns_media_sheet_mirror_previews(
               event_sha256,account_id,slot_id,queue_id,
               writer_version,projection_sha256,projection_json)
               VALUES (?,?,?,?,?,?,?)""",
            ("f" * 64, *KEY, 3, "a" * 64, '{}'),
        )
        self.assertEqual(len(self.writer.mirror_previews()), 1)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("DELETE FROM sns_media_sheet_mirror_previews")

    def test_event_immutable_and_head_hash_tamper_detected(self):
        self.prepare()
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("DELETE FROM sns_media_managed_queue_events")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "UPDATE sns_media_managed_queue_events SET action='ARCHIVE'",
            )
        self.db.execute(
            "UPDATE sns_media_managed_queue_heads SET queue_sha256=?",
            ("f" * 64,),
        )
        with self.assertRaises(ManagedQueueBlocked):
            self.writer.inspect(key=KEY)

    def test_atomic_rollback_when_mirror_insert_fails(self):
        self.capture()
        self.db.execute(
            """CREATE TRIGGER deny_mirror BEFORE INSERT
               ON sns_media_sheet_mirror_previews
               BEGIN SELECT RAISE(ABORT,'injected_failure'); END""",
        )
        with self.assertRaises(ManagedQueueBlocked):
            self.bind()
        self.assertEqual(self.count("sns_media_managed_queue_heads"), 0)
        self.assertEqual(self.count("sns_media_managed_queue_events"), 0)
        self.assertFalse(self.db.in_transaction)

    def test_two_connections_cannot_bind_same_candidate(self):
        self.prepare()
        other = sqlite3.connect(self.path, isolation_level=None, timeout=2)
        other.execute("PRAGMA foreign_keys=ON")
        try:
            writer = MediaManagedQueueWriter(other)
            vault = ProtectedEvidenceVault(other)
            reader = CanonicalProtectedReviewReader(
                source=fixtures.SQLiteShadowOperationalSnapshot(
                    db=other, vault=vault, clock=lambda: NOW,
                ), vault=vault,
            )
            with self.assertRaises(ManagedQueueBlocked):
                writer.bind(
                    key=KEY, operation_id="manage_other_connection_20261012_001",
                    verifier=self.make_verifier(other), bearer=self.bearer,
                    trusted_issuer=ISSUER, canonical=reader, as_of=NOW,
                )
            self.assertEqual(self.count("sns_media_managed_queue_events"), 1)
        finally:
            other.close()

    def test_mirror_preview_no_live_sheets_writer_or_publish_api(self):
        source = (
            ROOT / "scripts" / "media_managed_queue_writer.py"
        ).read_text(encoding="utf-8")
        for token in (
            "requests.post(", "gspread", "update_queue_item(",
            "_publish_container(", "PUBLISH_ENABLED",
            "sheets_write_allowed=True", "publish_authorized=True",
        ):
            self.assertNotIn(token, source)
        self.assertEqual(self.writer.mirror_previews(), [])


if __name__ == "__main__":
    unittest.main()
