#!/usr/bin/env python3
"""6K/6L no-network Drive ACL preflight + reporting mirror canary contract."""
from __future__ import annotations

import copy
import json
import sys
import unittest
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from media_mirror_readonly_acl_preflight import (  # noqa: E402
    MirrorAclPreflightBlocked, ReadOnlyGoogleMirrorMetadata,
    read_only_acl_preflight,
)
from media_mirror_readonly_canary import (  # noqa: E402
    MirrorReadOnlyCanary, MirrorReadOnlyCanaryBlocked,
)
from media_mirror_sheets_adapter import (  # noqa: E402
    GspreadReportingFixedRow, preview_to_row,
)
import test_media_mirror_reporting_delivery as prior  # noqa: E402

NOW, DEST, ROW, REPORT, ORIGINAL, TAB = (
    prior.NOW, prior.DEST, prior.ROW,
    prior.REPORT, prior.ORIGINAL, prior.TAB,
)
EMAIL = "mirror-service@example.test"
MIME = "application/vnd.google-apps.spreadsheet"


class FakeCredential:
    service_account_email = EMAIL


class FakeResponse:
    def __init__(self, body: dict | str, status_code=200):
        self.status_code = status_code
        self.content = (
            json.dumps(body).encode("utf-8")
            if isinstance(body, dict) else body.encode("utf-8")
        )


class FakeReadOnlyGoogleSession:
    """Only GET methods exist. Never sends a real HTTP request."""

    def __init__(self):
        self.calls: list[dict] = []
        self.fail = False
        self.status = 200
        self.operational = {
            "id": ORIGINAL, "mimeType": MIME, "trashed": False,
            "capabilities": {"canEdit": False, "canModifyContent": False},
        }
        self.reporting = {
            "id": REPORT, "mimeType": MIME, "trashed": False,
            "capabilities": {"canEdit": True, "canModifyContent": True},
        }
        self.structure = {
            "spreadsheetId": REPORT,
            "sheets": [{
                "properties": {
                    "sheetId": 22, "title": TAB, "sheetType": "GRID",
                    "gridProperties": {"rowCount": 200, "columnCount": 12},
                }
            }],
        }

    def get(self, url, *, params, timeout, allow_redirects):
        self.calls.append({
            "method": "GET", "url": url,
            "params": dict(params), "timeout": timeout,
            "allow_redirects": allow_redirects,
        })
        if self.fail:
            raise ConnectionError("private-authentication-string-must-never-leak")
        if url == f"https://www.googleapis.com/drive/v3/files/{ORIGINAL}":
            body = self.operational
        elif url == f"https://www.googleapis.com/drive/v3/files/{REPORT}":
            body = self.reporting
        elif url == f"https://sheets.googleapis.com/v4/spreadsheets/{REPORT}":
            body = self.structure
        else:
            raise AssertionError("unexpected provider URL")
        return FakeResponse(copy.deepcopy(body), status_code=self.status)


class FakePinnedSpreadsheet:
    def __init__(self, ws):
        self.ws = ws

    def worksheet(self, tab):
        if tab != TAB:
            raise AssertionError("wrong reporting tab")
        return self.ws


class FakeCredentialBoundGspread:
    def __init__(self, creds, ws):
        self.auth = creds
        self.ws = ws
        self.opened: list[str] = []

    def open_by_key(self, identifier):
        self.opened.append(identifier)
        if identifier != REPORT:
            raise AssertionError("not the pinned reporting spreadsheet")
        return FakePinnedSpreadsheet(self.ws)


class ReadOnlyCanaryTests(prior.MirrorReportingDeliveryTests):
    """Includes 6J tests and all inherited source/rights/queue tests."""

    def setUp(self):
        super().setUp()
        self.creds = FakeCredential()
        self.provider = FakeReadOnlyGoogleSession()
        self.metadata = ReadOnlyGoogleMirrorMetadata(
            credentials=self.creds, session=self.provider,
        )
        self.gspread_client = FakeCredentialBoundGspread(
            self.creds, self.ws,
        )
        self.bound_adapter = GspreadReportingFixedRow.from_trusted_client(
            client=self.gspread_client, target=self.target,
        )
        self.canary = MirrorReadOnlyCanary(
            db=self.db, verifier=self.live_verifier,
            metadata=self.metadata, adapter=self.bound_adapter,
            expected_principal_email=EMAIL, allow_provider_reads=True,
        )

    def acl(self):
        return read_only_acl_preflight(
            client=self.metadata, target=self.target,
            expected_principal_email=EMAIL, observed_at=NOW,
        )

    def inspect_canary(self, event=None, **overrides):
        values = {
            "event_sha256": event or self.ident(),
            "destination_id": DEST,
            "service_token": self.token_live,
            "as_of": NOW,
        }
        values.update(overrides)
        return self.canary.inspect(**values)

    def test_exact_three_provider_gets_and_zero_writes(self):
        result = self.acl()
        self.assertEqual(result["status"], "READ_ONLY_ACL_PASSED_NOT_ACTIVATED")
        self.assertEqual(result["provider_metadata_checks"], 3)
        self.assertFalse(result["reporting_write_authorized"])
        self.assertFalse(result["sns_publish_authorized"])
        self.assertEqual(len(self.provider.calls), 3)
        self.assertEqual(self.ws.writes, 0)
        for call in self.provider.calls:
            self.assertEqual(call["method"], "GET")
            self.assertFalse(call["allow_redirects"])
            self.assertEqual(call["timeout"], 8)
            self.assertNotIn("token", str(call).lower())
            self.assertNotIn("private", str(call).lower())
        self.assertEqual(
            self.provider.calls[0]["url"],
            f"https://www.googleapis.com/drive/v3/files/{ORIGINAL}",
        )
        self.assertEqual(
            self.provider.calls[1]["url"],
            f"https://www.googleapis.com/drive/v3/files/{REPORT}",
        )
        self.assertEqual(
            self.provider.calls[2]["url"],
            f"https://sheets.googleapis.com/v4/spreadsheets/{REPORT}",
        )

    def test_operational_must_be_observed_noneditable(self):
        self.provider.operational["capabilities"]["canEdit"] = True
        with self.assertRaises(MirrorAclPreflightBlocked):
            self.acl()

    def test_operational_content_mutation_capability_denied(self):
        self.provider.operational["capabilities"]["canModifyContent"] = True
        with self.assertRaises(MirrorAclPreflightBlocked):
            self.acl()

    def test_reporting_must_have_both_edit_capabilities(self):
        self.provider.reporting["capabilities"]["canEdit"] = False
        with self.assertRaises(MirrorAclPreflightBlocked):
            self.acl()

    def test_reporting_missing_modify_capability_denied(self):
        del self.provider.reporting["capabilities"]["canModifyContent"]
        with self.assertRaises(MirrorAclPreflightBlocked):
            self.acl()

    def test_unknown_operational_permissions_are_not_proof(self):
        self.provider.operational.pop("capabilities")
        with self.assertRaises(MirrorAclPreflightBlocked):
            self.acl()

    def test_trashed_or_wrong_mime_rejected(self):
        self.provider.reporting["trashed"] = True
        with self.assertRaises(MirrorAclPreflightBlocked):
            self.acl()
        self.provider.reporting["trashed"] = False
        self.provider.reporting["mimeType"] = "application/vnd.google-apps.document"
        with self.assertRaises(MirrorAclPreflightBlocked):
            self.acl()

    def test_changed_provider_file_id_rejected(self):
        self.provider.reporting["id"] = ORIGINAL
        with self.assertRaises(MirrorAclPreflightBlocked):
            self.acl()

    def test_duplicate_tab_or_missing_tab_denied(self):
        duplicate = copy.deepcopy(self.provider.structure["sheets"][0])
        self.provider.structure["sheets"].append(duplicate)
        with self.assertRaises(MirrorAclPreflightBlocked):
            self.acl()
        self.provider.structure["sheets"] = []
        with self.assertRaises(MirrorAclPreflightBlocked):
            self.acl()

    def test_wrong_sheet_grid_dimensions_and_type_denied(self):
        props = self.provider.structure["sheets"][0]["properties"]
        props["gridProperties"]["rowCount"] = ROW - 1
        with self.assertRaises(MirrorAclPreflightBlocked):
            self.acl()
        props["gridProperties"]["rowCount"] = 200
        props["gridProperties"]["columnCount"] = 11
        with self.assertRaises(MirrorAclPreflightBlocked):
            self.acl()
        props["gridProperties"]["columnCount"] = 12
        props["sheetType"] = "OBJECT"
        with self.assertRaises(MirrorAclPreflightBlocked):
            self.acl()

    def test_provider_spreadsheet_id_mismatch_denied(self):
        self.provider.structure["spreadsheetId"] = ORIGINAL
        with self.assertRaises(MirrorAclPreflightBlocked):
            self.acl()

    def test_provider_denial_timeout_and_non_json_fail_closed(self):
        self.provider.status = 403
        with self.assertRaisesRegex(
            MirrorAclPreflightBlocked, "mirror_preflight_provider_denied",
        ):
            self.acl()
        self.provider.status = 200
        self.provider.fail = True
        with self.assertRaisesRegex(
            MirrorAclPreflightBlocked, "mirror_preflight_provider_unavailable",
        ):
            self.acl()
        self.provider.fail = False

    def test_provider_rejects_wrong_expected_principal(self):
        with self.assertRaises(MirrorAclPreflightBlocked):
            read_only_acl_preflight(
                client=self.metadata, target=self.target,
                expected_principal_email="wrong@example.test",
            )
        self.assertEqual(self.provider.calls, [])

    def test_fake_client_factory_returns_same_credentials(self):
        self.assertIs(self.bound_adapter.auth_credentials, self.creds)
        self.assertEqual(self.gspread_client.opened, [REPORT])
        self.assertIsNone(self.sheet_adapter.auth_credentials)

    def test_unbound_worksheet_cannot_claim_preflight_safety(self):
        with self.assertRaises(MirrorReadOnlyCanaryBlocked):
            MirrorReadOnlyCanary(
                db=self.db, verifier=self.live_verifier,
                metadata=self.metadata, adapter=self.sheet_adapter,
                expected_principal_email=EMAIL, allow_provider_reads=True,
            )

    def test_same_email_but_distinct_credentials_are_rejected(self):
        other = ReadOnlyGoogleMirrorMetadata(
            credentials=FakeCredential(), session=FakeReadOnlyGoogleSession(),
        )
        with self.assertRaises(MirrorReadOnlyCanaryBlocked):
            MirrorReadOnlyCanary(
                db=self.db, verifier=self.live_verifier,
                metadata=other, adapter=self.bound_adapter,
                expected_principal_email=EMAIL, allow_provider_reads=True,
            )

    def test_canary_provider_reads_disabled_by_default(self):
        self.claimed()
        disabled = MirrorReadOnlyCanary(
            db=self.db, verifier=self.live_verifier,
            metadata=self.metadata, adapter=self.bound_adapter,
            expected_principal_email=EMAIL,
        )
        with self.assertRaisesRegex(
            MirrorReadOnlyCanaryBlocked, "mirror_canary_reads_disabled",
        ):
            disabled.inspect(
                event_sha256=self.ident(), destination_id=DEST,
                service_token=self.token_live, as_of=NOW,
            )
        self.assertEqual(self.provider.calls, [])
        self.assertEqual(self.ws.get_calls, [])

    def test_canary_does_not_mutate_sqlite_or_provider(self):
        event = self.claimed()
        snapshot = self.db.total_changes
        result = self.inspect_canary(event)
        self.assertEqual(result["status"], "EMPTY_REQUIRES_APPROVAL_BLOCKED")
        self.assertEqual(self.db.total_changes, snapshot)
        self.assertEqual(self.ws.writes, 0)
        self.assertFalse(result["reporting_write_authorized"])
        self.assertFalse(result["sns_publish_authorized"])
        self.assertFalse(result["operational_queue_modified"])

    def test_current_exact_row_is_only_readback_match(self):
        event = self.claimed()
        self.ws.values = preview_to_row(self.writer.mirror_previews()[0])
        result = self.inspect_canary(event)
        self.assertEqual(result["status"], "MATCHED_BLOCKED")
        self.assertEqual(result["observed_version"], 1)
        self.assertEqual(self.ws.writes, 0)
        self.assertTrue(result["requires_separate_operator_approval"])

    def test_older_same_candidate_reported_without_write(self):
        self.prepare()
        previous = self.writer.mirror_previews()[0]
        self.change("HOLD")
        self.ws.values = preview_to_row(previous)
        self.claim()
        result = self.inspect_canary()
        self.assertEqual(result["status"], "OLDER_REQUIRES_APPROVAL_BLOCKED")
        self.assertEqual(result["source_version"], 2)
        self.assertEqual(result["observed_version"], 1)
        self.assertEqual(self.ws.writes, 0)

    def test_foreign_candidate_or_newer_row_is_conflict(self):
        event = self.claimed()
        fake = dict(self.writer.mirror_previews()[0])
        fake["queue_id"] = "other_queue"
        fake["writer_event_sha256"] = "f" * 64
        self.ws.values = preview_to_row(fake)
        result = self.inspect_canary(event)
        self.assertEqual(result["status"], "CONFLICT_BLOCKED")
        self.assertEqual(self.ws.writes, 0)

    def test_missing_acls_block_before_reporting_row_read(self):
        event = self.claimed()
        self.provider.operational["capabilities"]["canEdit"] = True
        with self.assertRaises(MirrorReadOnlyCanaryBlocked):
            self.inspect_canary(event)
        self.assertEqual(self.ws.get_calls, [])
        self.assertEqual(self.ws.writes, 0)

    def test_provider_outage_fails_without_row_read(self):
        event = self.claimed()
        self.provider.fail = True
        with self.assertRaisesRegex(
            MirrorReadOnlyCanaryBlocked, "mirror_canary_evidence_unavailable",
        ):
            self.inspect_canary(event)
        self.assertEqual(self.ws.get_calls, [])

    def test_corrupted_report_row_fails_closed(self):
        event = self.claimed()
        self.ws.values = ["=IMPORTXML(\"private\",\"//x\")"] + [""] * 11
        with self.assertRaises(MirrorReadOnlyCanaryBlocked):
            self.inspect_canary(event)
        self.assertEqual(self.ws.writes, 0)

    def test_bad_reviewer_or_rehearsal_service_not_accepted(self):
        event = self.claimed()
        for token in (self.bearer, self.service_jwt):
            with self.assertRaises(MirrorReadOnlyCanaryBlocked):
                self.inspect_canary(event, service_token=token)
        self.assertEqual(self.provider.calls, [])

    def test_claim_must_exist_and_be_unexpired(self):
        self.prepare()
        with self.assertRaises(MirrorReadOnlyCanaryBlocked):
            self.inspect_canary()
        self.claim()
        with self.assertRaises(MirrorReadOnlyCanaryBlocked):
            self.inspect_canary(as_of=NOW + timedelta(seconds=60))
        self.assertEqual(self.provider.calls, [])

    def test_changed_source_blocks_preflight(self):
        event = self.claimed()
        self.change("HOLD")
        with self.assertRaises(MirrorReadOnlyCanaryBlocked):
            self.inspect_canary(event)
        self.assertEqual(self.provider.calls, [])

    def test_unresolved_prior_delivery_claim_blocks_other_version(self):
        self.prepare()
        self.claim()
        old = self.ident()
        self.ws.fail_after_write = True
        result = self.deliver(old)
        self.assertEqual(result["status"], "OUTCOME_UNKNOWN_BLOCKED")
        self.ws.fail_after_write = False
        self.change("HOLD")
        self.claim(operation="mirror_claim_latest_for_canary_20261012_0001")
        with self.assertRaisesRegex(
            MirrorReadOnlyCanaryBlocked,
            "mirror_canary_unresolved_prior_delivery",
        ):
            self.inspect_canary(self.ident())
        self.assertEqual(self.provider.calls, [])

    def test_client_without_auth_credentials_cannot_be_bound(self):
        class ClientWithoutCredentials:
            pass

        with self.assertRaises(Exception):
            GspreadReportingFixedRow.from_trusted_client(
                client=ClientWithoutCredentials(), target=self.target,
            )


if __name__ == "__main__":
    unittest.main()
