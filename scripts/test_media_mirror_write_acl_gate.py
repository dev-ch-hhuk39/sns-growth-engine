#!/usr/bin/env python3
"""Phase 5B-6M mandatory Google ACL evidence at reporting write time.

Uses ephemeral JWT and a fake bounded provider GET session plus a local
fake worksheet. This code must never load live service account credentials.
"""
from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from media_mirror_delivery_identity import MirrorDeliveryBlocked  # noqa: E402
from media_mirror_readonly_acl_preflight import (  # noqa: E402
    ReadOnlyGoogleMirrorMetadata,
)
from media_mirror_reporting_delivery import IsolatedSheetsMirrorDelivery  # noqa: E402
from media_mirror_sheets_adapter import GspreadReportingFixedRow  # noqa: E402
import test_media_mirror_reporting_delivery as prior  # noqa: E402


class MirrorWriteAclGateTests(prior.MirrorReportingDeliveryTests):
    """Replays all prior delivery regressions before 6M security cases."""

    def test_enabled_writer_needs_acl_metadata(self):
        with self.assertRaisesRegex(
            MirrorDeliveryBlocked, "mirror_delivery_acl_binding_required",
        ):
            IsolatedSheetsMirrorDelivery(
                db=self.db, verifier=self.live_verifier,
                adapter=self.sheet_adapter, allow_reporting_write=True,
            )

    def test_enabled_writer_rejects_direct_worksheet_even_with_metadata(self):
        direct = GspreadReportingFixedRow(
            worksheet=self.ws, target=self.target,
        )
        with self.assertRaisesRegex(
            MirrorDeliveryBlocked, "mirror_delivery_acl_binding_required",
        ):
            IsolatedSheetsMirrorDelivery(
                db=self.db, verifier=self.live_verifier,
                adapter=direct, allow_reporting_write=True,
                acl_metadata=self.acl_metadata,
                expected_principal_email=self.acl_credentials.service_account_email,
            )
        self.assertEqual(self.ws.writes, 0)

    def test_same_email_different_credentials_not_sufficient(self):
        impostor = prior.FixtureDeliveryCredentials()
        self.assertIsNot(impostor, self.acl_credentials)
        other_meta = ReadOnlyGoogleMirrorMetadata(
            credentials=impostor, session=prior.FixtureDriveReadSession(),
        )
        with self.assertRaisesRegex(
            MirrorDeliveryBlocked, "mirror_delivery_acl_binding_required",
        ):
            IsolatedSheetsMirrorDelivery(
                db=self.db, verifier=self.live_verifier,
                adapter=self.sheet_adapter, allow_reporting_write=True,
                acl_metadata=other_meta,
                expected_principal_email=impostor.service_account_email,
            )

    def test_wrong_pinned_principal_rejected_before_provider_get(self):
        with self.assertRaises(MirrorDeliveryBlocked):
            IsolatedSheetsMirrorDelivery(
                db=self.db, verifier=self.live_verifier,
                adapter=self.sheet_adapter, allow_reporting_write=True,
                acl_metadata=self.acl_metadata,
                expected_principal_email="different@example.test",
            )
        self.assertEqual(self.acl_session.calls, [])

    def test_synthetic_success_checks_acls_twice_before_one_put(self):
        event = self.claimed()
        result = self.deliver(event)
        self.assertEqual(result["status"], "READBACK_VERIFIED_BLOCKED")
        self.assertEqual(self.ws.writes, 1)
        self.assertTrue(result["reporting_readback_matched"])
        self.assertFalse(result["publish_authorized"])
        self.assertFalse(result["operational_queue_modified"])
        urls = self.acl_session.calls
        self.assertEqual(len(urls), 6)
        self.assertEqual(urls[:3], urls[3:])
        self.assertEqual(
            urls[0],
            f"https://www.googleapis.com/drive/v3/files/{prior.ORIGINAL}",
        )
        self.assertEqual(
            urls[1],
            f"https://www.googleapis.com/drive/v3/files/{prior.REPORT}",
        )
        self.assertEqual(
            urls[2],
            f"https://sheets.googleapis.com/v4/spreadsheets/{prior.REPORT}",
        )

    def test_each_acl_check_precedes_actual_fake_put(self):
        self.claimed()
        original = self.ws.update
        counts = []

        def wrapper(*args, **kwargs):
            counts.append(len(self.acl_session.calls))
            return original(*args, **kwargs)

        self.ws.update = wrapper
        self.deliver()
        self.assertEqual(counts, [6])
        self.assertEqual(self.ws.writes, 1)

    def test_operational_edit_access_blocks_before_row_read(self):
        self.claimed()
        self.acl_session.operational_can_edit = True
        result = self.deliver()
        self.assertEqual(result["status"], "OUTCOME_UNKNOWN_BLOCKED")
        self.assertFalse(result["reporting_write_attempted"])
        self.assertEqual(self.ws.writes, 0)
        self.assertEqual(self.ws.get_calls, [])
        self.assertEqual(self.count("sns_mirror_delivery_events"), 2)

    def test_operational_content_write_capability_blocks(self):
        self.claimed()
        self.acl_session.operational_can_modify_content = True
        result = self.deliver()
        self.assertEqual(result["status"], "OUTCOME_UNKNOWN_BLOCKED")
        self.assertEqual(self.ws.writes, 0)

    def test_reporting_write_acl_missing_blocks(self):
        self.claimed()
        self.acl_session.reporting_can_edit = False
        result = self.deliver()
        self.assertEqual(result["status"], "OUTCOME_UNKNOWN_BLOCKED")
        self.assertEqual(self.ws.writes, 0)
        self.assertEqual(self.ws.get_calls, [])

    def test_reporting_modify_capability_missing_blocks(self):
        self.claimed()
        self.acl_session.reporting_can_modify_content = False
        result = self.deliver()
        self.assertEqual(result["status"], "OUTCOME_UNKNOWN_BLOCKED")
        self.assertEqual(self.ws.writes, 0)

    def test_midflight_acl_change_after_first_read_aborts_put(self):
        self.claimed()

        def change_on_fourth_provider_get(_url):
            if len(self.acl_session.calls) == 4:
                self.acl_session.operational_can_edit = True

        self.acl_session.before_return = change_on_fourth_provider_get
        result = self.deliver()
        self.assertEqual(result["status"], "OUTCOME_UNKNOWN_BLOCKED")
        self.assertFalse(result["reporting_write_attempted"])
        self.assertEqual(len(self.acl_session.calls), 4)
        self.assertEqual(self.ws.writes, 0)
        self.assertEqual(len(self.ws.get_calls), 2)

    def test_midflight_reporting_acl_change_aborts_put(self):
        self.claimed()

        def withdraw_before_second_probe(_url):
            if len(self.acl_session.calls) == 4:
                self.acl_session.reporting_can_modify_content = False

        self.acl_session.before_return = withdraw_before_second_probe
        result = self.deliver()
        self.assertEqual(result["status"], "OUTCOME_UNKNOWN_BLOCKED")
        self.assertEqual(self.ws.writes, 0)

    def test_synthetic_provider_outage_is_sanitized_and_no_retry(self):
        event = self.claimed()
        self.acl_session.fail = True
        result = self.deliver(event)
        self.assertEqual(result["status"], "OUTCOME_UNKNOWN_BLOCKED")
        self.assertEqual(self.ws.writes, 0)
        self.assertNotIn("fixture_credential", str(result))
        self.acl_session.fail = False
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(
                event, operation_id="delivery_6m_try_again_20261012_001",
            )
        self.assertEqual(self.ws.writes, 0)

    def test_revoked_service_after_first_acl_round_blocks_write(self):
        event = self.claimed()

        def revoke_on_first_reporting_tab_metadata(_url):
            if len(self.acl_session.calls) == 3:
                self.db.execute(
                    "UPDATE sns_mirror_delivery_sessions SET enabled=0",
                )

        self.acl_session.before_return = revoke_on_first_reporting_tab_metadata
        result = self.deliver(event)
        self.assertEqual(result["status"], "OUTCOME_UNKNOWN_BLOCKED")
        self.assertEqual(self.ws.writes, 0)
        self.assertEqual(self.count("sns_mirror_delivery_events"), 2)

    def test_report_is_already_identical_still_requires_first_acl_probe(self):
        event = self.claimed()
        self.ws.values = prior.preview_to_row(self.writer.mirror_previews()[0])
        result = self.deliver(event)
        self.assertEqual(result["status"], "READBACK_VERIFIED_BLOCKED")
        self.assertFalse(result["reporting_write_attempted"])
        self.assertEqual(len(self.acl_session.calls), 3)
        self.assertEqual(self.ws.writes, 0)

    def test_reconciliation_refuses_new_operational_write_permission(self):
        event = self.claimed()
        self.ws.fail_after_write = True
        result = self.deliver(event)
        self.assertEqual(result["status"], "OUTCOME_UNKNOWN_BLOCKED")
        self.assertEqual(self.ws.writes, 1)
        self.ws.fail_after_write = False
        self.acl_session.operational_can_edit = True
        with self.assertRaisesRegex(
            MirrorDeliveryBlocked, "mirror_delivery_readback_unavailable",
        ):
            self.recover(event)
        self.assertEqual(
            self.engine.inspect(event_sha256=event, destination_id=prior.DEST)[
                "status"
            ], "OUTCOME_UNKNOWN_BLOCKED",
        )
        self.acl_session.operational_can_edit = False
        result = self.recover(event)
        self.assertEqual(result["status"], "RECONCILED_BLOCKED")
        self.assertEqual(self.ws.writes, 1)

    def test_unclaimed_cannot_obtain_any_google_acl_checks(self):
        self.prepare()
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver()
        self.assertEqual(self.acl_session.calls, [])
        self.assertEqual(self.ws.writes, 0)

    def test_change_credentials_after_init_blocks_at_acl_runtime(self):
        self.claimed()
        self.sheet_adapter.auth_credentials = prior.FixtureDeliveryCredentials()
        result = self.deliver()
        self.assertEqual(result["status"], "OUTCOME_UNKNOWN_BLOCKED")
        self.assertEqual(self.ws.writes, 0)

    def test_no_real_service_principal_or_sheet_used(self):
        self.assertNotIn("@gmail.com", self.acl_credentials.service_account_email)
        self.assertEqual(self.acl_session.calls, [])
        self.assertEqual(self.ws.writes, 0)
        # The synthetic DB is not the production SQLite DB.
        self.assertIsInstance(self.db, sqlite3.Connection)


if __name__ == "__main__":
    unittest.main()
