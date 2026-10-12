#!/usr/bin/env python3
"""6J fake-gspread transport and protected one-use delivery ledger tests.

No live Google credentials, API requests, Sheets writes or SNS posts.
"""
from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
import sys
import unittest
from datetime import timedelta
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from media_mirror_delivery_identity import (  # noqa: E402
    AUDIENCE, SCOPE, TOKEN_USE, MirrorDeliveryBlocked,
    PinnedLiveMirrorServiceVerifier, initialize_mirror_delivery_schema,
)
from media_mirror_readonly_acl_preflight import (  # noqa: E402
    ReadOnlyGoogleMirrorMetadata,
)
from media_mirror_canary_approval import (  # noqa: E402
    AUDIENCE as CANARY_AUDIENCE, SCOPE as CANARY_SCOPE,
    TOKEN_USE as CANARY_TOKEN_USE,
    PinnedTwoOperatorCanaryVerifier, initialize_canary_approval_schema,
)
from media_mirror_operator_grants import (  # noqa: E402
    initialize_operator_grant_schema,
)
from media_mirror_operator_idp import (  # noqa: E402
    AUDIENCE as IDP_AUDIENCE, SCOPE as IDP_SCOPE,
    TOKEN_USE as IDP_TOKEN_USE, ACR as IDP_ACR, PROFILE as IDP_PROFILE,
    PinnedOperatorIdpSessionVerifier, initialize_operator_idp_schema,
)
from media_mirror_reporting_delivery import _hash as delivery_hash  # noqa: E402
from media_mirror_reporting_delivery import IsolatedSheetsMirrorDelivery  # noqa: E402
from media_mirror_sheets_adapter import (  # noqa: E402
    FixedRowMirrorBlocked, GspreadReportingFixedRow,
    HEADERS, ReportingRowTarget, preview_to_row, row_to_preview,
)
import test_media_mirror_rehearsal as fixtures  # noqa: E402

KEY, NOW, ISSUER = fixtures.KEY, fixtures.NOW, fixtures.ISSUER
T = int(NOW.timestamp())
DEST = "destination_live_mirror_0001"
SUB = "mirror_delivery_service_0001"
SID = "mirror_delivery_session_00001"
JTI = "mirror_delivery_jti_00001"
KID = "mirror_delivery_key_20261012"
REPORT = "reporting_sheet_00001"
ORIGINAL = "operational_sheet_00001"
TAB = "mirror_preview_internal"
ROW = 7
IDP_ISSUER = ISSUER.rstrip("/") + "/human-identity"
IDP_KID = "canary_human_idp_signer_20261012"


def b64(obj):
    return base64.urlsafe_b64encode(
        json.dumps(obj,sort_keys=True,separators=(",",":")).encode("ascii")
    ).decode("ascii").rstrip("=")


class FakeGspreadWorksheet:
    """Exact methods used by gspread 6.2.1, no outbound network."""
    def __init__(self):
        self.spreadsheet_id = REPORT
        self.title = TAB
        self.row_count = 200
        self.col_count = 12
        self.header = list(HEADERS)
        self.values = []
        self.writes = 0
        self.get_calls = []
        self.update_calls = []
        self.fail_read = False
        self.fail_before_write = False
        self.fail_after_write = False

    def get(self, range_name, value_render_option=None):
        self.get_calls.append((range_name,value_render_option))
        if self.fail_read:
            raise OSError("network simulator: credential-secret-must-not-leak")
        if range_name == "A1:L1":
            return [list(self.header)]
        if range_name == f"A{ROW}:L{ROW}":
            return [list(self.values)] if self.values else []
        raise AssertionError("unexpected range")

    def update(self,range_name=None,values=None,value_input_option=None):
        self.update_calls.append((range_name,values,value_input_option))
        if (range_name != f"A{ROW}:L{ROW}"
                or value_input_option != "RAW"
                or not isinstance(values,list)
                or len(values) != 1 or len(values[0]) != 12):
            raise AssertionError("unsafe writer target")
        if self.fail_before_write:
            raise OSError("fake network timeout before write")
        self.values=list(values[0])
        self.writes+=1
        if self.fail_after_write:
            raise OSError("fake network timeout after write")
        return {"updatedCells":12}


class FixtureDeliveryCredentials:
    service_account_email = "reporting-mirror-fixture@example.test"


class FixtureDriveReadResponse:
    def __init__(self, body):
        self.status_code = 200
        self.content = json.dumps(body, sort_keys=True).encode("utf-8")


class FixtureDriveReadSession:
    """Exactly the 6K read-only capability API; never contacts Google."""

    def __init__(self):
        self.calls = []
        self.fail = False
        self.before_return = None
        self.operational_can_edit = False
        self.operational_can_modify_content = False
        self.reporting_can_edit = True
        self.reporting_can_modify_content = True

    def get(self, url, *, params, timeout, allow_redirects):
        self.calls.append(url)
        if self.before_return is not None:
            self.before_return(url)
        if self.fail:
            raise ConnectionError("offline_fixture_credential_unavailable")
        if url == f"https://www.googleapis.com/drive/v3/files/{ORIGINAL}":
            return FixtureDriveReadResponse({
                "id": ORIGINAL, "mimeType": "application/vnd.google-apps.spreadsheet",
                "trashed": False,
                "capabilities": {
                    "canEdit": self.operational_can_edit,
                    "canModifyContent": self.operational_can_modify_content,
                },
            })
        if url == f"https://www.googleapis.com/drive/v3/files/{REPORT}":
            return FixtureDriveReadResponse({
                "id": REPORT, "mimeType": "application/vnd.google-apps.spreadsheet",
                "trashed": False,
                "capabilities": {
                    "canEdit": self.reporting_can_edit,
                    "canModifyContent": self.reporting_can_modify_content,
                },
            })
        if url == f"https://sheets.googleapis.com/v4/spreadsheets/{REPORT}":
            return FixtureDriveReadResponse({
                "spreadsheetId": REPORT,
                "sheets": [{
                    "properties": {
                        "sheetId": 10, "title": TAB, "sheetType": "GRID",
                        "gridProperties": {"rowCount": 200, "columnCount": 12},
                    }
                }],
            })
        raise AssertionError("fixture_unknown_file_id")


class FixtureBoundSpreadsheet:
    def __init__(self, worksheet):
        self.worksheet_object = worksheet

    def worksheet(self, tab):
        if tab != TAB:
            raise AssertionError("fixture_unpinned_tab")
        return self.worksheet_object


class FixtureBoundGspreadClient:
    def __init__(self, credentials, worksheet):
        self.auth = credentials
        self.ws = worksheet

    def open_by_key(self, identifier):
        if identifier != REPORT:
            raise AssertionError("fixture_unpinned_workbook")
        return FixtureBoundSpreadsheet(self.ws)


class MirrorReportingDeliveryTests(fixtures.MirrorRehearsalTests):
    """Inherited 6I tests and new code-only delivery tests."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.live_private = rsa.generate_private_key(
            public_exponent=65537,key_size=2048,
        )
        cls.live_public = cls.live_private.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        cls.operator_private_keys = [
            rsa.generate_private_key(public_exponent=65537, key_size=2048)
            for _ in range(2)
        ]
        cls.operator_public_keys = [
            key.public_key().public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            for key in cls.operator_private_keys
        ]
        cls.operator_kids = (
            "canary_review_operator_key_01", "canary_review_operator_key_02",
        )
        cls.operator_subjects = (
            "canary_review_human_01", "canary_review_human_02",
        )
        cls.idp_private = rsa.generate_private_key(
            public_exponent=65537,key_size=2048,
        )
        cls.idp_public = cls.idp_private.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    @classmethod
    def idp_token(cls, slot, overrides=None, header_overrides=None):
        claims={
            "iss":IDP_ISSUER,"aud":IDP_AUDIENCE,
            "token_use":IDP_TOKEN_USE,"scope":IDP_SCOPE,
            "sub":cls.operator_subjects[slot],
            "sid":f"canary_idp_session_{slot}_20261012",
            "jti":f"canary_idp_token_{slot}_20261012",
            "acr":IDP_ACR,"amr":["mfa","webauthn"],
            "auth_time":T-90,"mfa_at":T-65,
            "iat":T-60,"nbf":T-60,"exp":T+180,
        }
        claims.update(overrides or {})
        header={"alg":"RS256","typ":"JWT","kid":IDP_KID}
        header.update(header_overrides or {})
        raw=b64(header)+"."+b64(claims)
        signed=cls.idp_private.sign(
            raw.encode("ascii"),padding.PKCS1v15(),hashes.SHA256(),
        )
        return raw+"."+base64.urlsafe_b64encode(signed).decode().rstrip("=")

    @classmethod
    def live_token(cls,overrides=None,header_overrides=None):
        claims={
            "iss":ISSUER,"aud":AUDIENCE,"token_use":TOKEN_USE,"scope":SCOPE,
            "sub":SUB,"sid":SID,"jti":JTI,
            "iat":T-60,"nbf":T-60,"exp":T+180,
        }
        claims.update(overrides or {})
        header={"alg":"RS256","typ":"JWT","kid":KID}
        header.update(header_overrides or {})
        msg=b64(header)+"."+b64(claims)
        sig=cls.live_private.sign(
            msg.encode("ascii"),padding.PKCS1v15(),hashes.SHA256(),
        )
        return msg+"."+base64.urlsafe_b64encode(sig).decode().rstrip("=")

    def setUp(self):
        super().setUp()
        initialize_mirror_delivery_schema(self.db)
        initialize_canary_approval_schema(self.db)
        initialize_operator_grant_schema(self.db)
        initialize_operator_idp_schema(self.db)
        self.idp_tokens=tuple(self.idp_token(slot) for slot in range(2))
        for slot,token in enumerate(self.idp_tokens):
            self.db.execute(
                """INSERT INTO sns_mirror_canary_idp_sessions(
                   session_id,subject,issuer,signer_kid,token_jti,
                   assertion_sha256,authenticated_at,mfa_at,issued_at,
                   expires_at,authentication_profile,enabled,revoked_at,
                   provisioned_by
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    f"canary_idp_session_{slot}_20261012",
                    self.operator_subjects[slot],IDP_ISSUER,IDP_KID,
                    f"canary_idp_token_{slot}_20261012",
                    hashlib.sha256(token.encode("ascii")).hexdigest(),
                    T-90,T-65,T-60,T+180,IDP_PROFILE,1,None,
                    "offline_test_idp_bridge",
                ),
            )
        self.identity_verifier=PinnedOperatorIdpSessionVerifier(
            db=self.db,issuer=IDP_ISSUER,
            public_keys_by_kid={IDP_KID:self.idp_public},
        )
        self.operator_gate = PinnedTwoOperatorCanaryVerifier(
            db=self.db, issuer=ISSUER,
            operators_by_kid={
                self.operator_kids[i]: (
                    self.operator_subjects[i], self.operator_public_keys[i],
                ) for i in range(2)
            },
            identity_verifier=self.identity_verifier,
        )
        self.token_live = self.live_token()
        self.db.execute(
            """INSERT INTO sns_mirror_delivery_sessions (
             session_id,subject,issuer,token_sha256,token_jti,issued_at,
             expires_at,revoked_at,enabled) VALUES(?,?,?,?,?,?,?,?,?)""",
            (SID,SUB,ISSUER,hashlib.sha256(
                self.token_live.encode("ascii"),
            ).hexdigest(),JTI,T-60,T+180,None,1),
        )
        self.db.execute(
            """INSERT INTO sns_mirror_delivery_destinations (
                destination_id,account_id,service_subject,
                reporting_spreadsheet_id,operational_spreadsheet_id,
                reporting_tab,mode,enabled
               ) VALUES(?,?,?,?,?,?,?,?)""",
            (DEST,KEY[0],SUB,REPORT,ORIGINAL,TAB,
             "ISOLATED_REPORTING_ONLY",1),
        )
        for index in range(2):
            self.db.execute(
                """INSERT INTO sns_mirror_canary_operator_grants(
                   signer_kid,signer_subject,account_id,destination_id,
                   approval_slot,grant_generation,valid_from,valid_until,
                   enabled,revoked_at,provisioned_by
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (self.operator_kids[index], self.operator_subjects[index],
                 KEY[0], DEST, index+1, 1, T-120, T+240, 1, None,
                 "synthetic_test_operator"),
            )
        self.db.execute(
            """INSERT INTO sns_mirror_delivery_row_map (
               destination_id,account_id,slot_id,queue_id,row_number
               ) VALUES(?,?,?,?,?)""", (DEST,*KEY,ROW),
        )
        self.ws=FakeGspreadWorksheet()
        self.target=ReportingRowTarget(REPORT,ORIGINAL,TAB,ROW)
        self.acl_credentials=FixtureDeliveryCredentials()
        self.acl_session=FixtureDriveReadSession()
        self.acl_metadata=ReadOnlyGoogleMirrorMetadata(
            credentials=self.acl_credentials,session=self.acl_session,
        )
        self.sheet_adapter=GspreadReportingFixedRow.from_trusted_client(
            client=FixtureBoundGspreadClient(self.acl_credentials,self.ws),
            target=self.target,
        )
        self.live_verifier=PinnedLiveMirrorServiceVerifier(
            db=self.db,issuer=ISSUER,
            public_keys_by_kid={KID:self.live_public},
        )
        self.engine=IsolatedSheetsMirrorDelivery(
            db=self.db,verifier=self.live_verifier,
            adapter=self.sheet_adapter,allow_reporting_write=True,
            acl_metadata=self.acl_metadata,
            expected_principal_email=self.acl_credentials.service_account_email,
            canary_approver=self.operator_gate,
        )

    def operator_signoffs(
        self, *, event=None, operation_id="delivery_run_20261012_000001",
        overrides=None, which=(0, 1), identity_tokens=None,
    ):
        event = event or self.ident()
        identity_tokens = self.idp_tokens if identity_tokens is None else identity_tokens
        preview = self.writer.mirror_previews()[0]
        claims = {
            "iss": ISSUER, "aud": CANARY_AUDIENCE,
            "token_use": CANARY_TOKEN_USE, "scope": CANARY_SCOPE,
            "iat": T-60, "nbf": T-60, "exp": T+180,
            "event_sha256": event, "operation_id": operation_id,
            "destination_id": DEST, "account_id": KEY[0],
            "slot_id": KEY[1], "queue_id": KEY[2],
            "row_number": ROW, "projection_sha256": delivery_hash(preview),
            "grant_generation": 1,
        }
        claims.update(overrides or {})
        result = []
        for slot in which:
            fields = dict(claims)
            fields["sub"] = self.operator_subjects[slot]
            fields["approval_slot"] = slot + 1
            fields["idp_session_id"] = f"canary_idp_session_{slot}_20261012"
            fields["idp_assertion_sha256"] = hashlib.sha256(
                identity_tokens[slot].encode("ascii"),
            ).hexdigest()
            fields["jti"] = f"canary_operator_{slot}_{operation_id}"
            header = {"typ": "JWT", "alg": "RS256", "kid": self.operator_kids[slot]}
            signed = b64(header) + "." + b64(fields)
            signature = self.operator_private_keys[slot].sign(
                signed.encode("ascii"), padding.PKCS1v15(), hashes.SHA256(),
            )
            result.append(
                signed + "." + base64.urlsafe_b64encode(signature).decode().rstrip("=")
            )
        return tuple(result)

    def claimed(self):
        self.prepare()
        self.claim()
        return self.ident()

    def deliver(self,event=None,**changes):
        args={
            "event_sha256":event or self.ident(),
            "destination_id":DEST,"service_token":self.token_live,
            "operation_id":"delivery_run_20261012_000001",
            "as_of":NOW,
        }
        args.update(changes)
        if "canary_approval_tokens" not in args:
            args["canary_approval_tokens"] = self.operator_signoffs(
                event=args["event_sha256"],
                operation_id=args["operation_id"],
            )
        if "identity_assertion_tokens" not in args:
            args["identity_assertion_tokens"]=self.idp_tokens
        return self.engine.deliver_once(**args)

    def recover(self,event=None,**changes):
        event=event or self.ident()
        current=self.engine.inspect(event_sha256=event,destination_id=DEST)
        args={
            "event_sha256":event,"destination_id":DEST,
            "service_token":self.token_live,
            "operation_id":"delivery_reconcile_20261012_000001",
            "expected_version":current["version"],
            "expected_audit_sha256":current["audit_sha256"],
            "as_of":NOW,
        }
        args.update(changes)
        return self.engine.reconcile_readonly(**args)

    def test_migration_refuses_missing_outbox(self):
        db=sqlite3.connect(":memory:",isolation_level=None)
        try:
            with self.assertRaises(MirrorDeliveryBlocked):
                initialize_mirror_delivery_schema(db)
        finally:
            db.close()

    def test_network_disabled_by_default(self):
        self.claimed()
        engine=IsolatedSheetsMirrorDelivery(
            db=self.db,verifier=self.live_verifier,
            adapter=self.sheet_adapter,
        )
        with self.assertRaisesRegex(
            MirrorDeliveryBlocked,"mirror_reporting_write_disabled",
        ):
            engine.deliver_once(
                event_sha256=self.ident(),destination_id=DEST,
                service_token=self.token_live,
                operation_id="delivery_disabled_20261012_00001",as_of=NOW,
            )
        self.assertEqual(self.ws.writes,0)
        self.assertFalse(self.count("sns_mirror_delivery_heads"))

    def test_live_token_not_reviewer_or_rehearsal_token(self):
        event=self.claimed()
        for token in (self.bearer,self.service_jwt):
            with self.assertRaises(MirrorDeliveryBlocked):
                self.deliver(event,service_token=token)
        self.assertEqual(self.ws.writes,0)

    def test_invalid_audience_signature_scope_or_expiry(self):
        event=self.claimed()
        for token in (
            self.live_token({"aud":"sns-growth-media-review"}),
            self.live_token({"scope":"mirror:rehearse"}),
            self.live_token({"token_use":"mirror_rehearsal_only"}),
            self.live_token({"exp":T+1500}),
            self.live_token(header_overrides={"alg":"none"}),
            self.token_live[:-18]+"invalid_signature",
        ):
            with self.subTest(token_type=token[:8]), self.assertRaises(MirrorDeliveryBlocked):
                self.deliver(event,service_token=token)
        self.assertEqual(self.ws.writes,0)

    def test_revoked_session_or_disabled_policy_blocks(self):
        event=self.claimed()
        self.db.execute(
            "UPDATE sns_mirror_delivery_sessions SET revoked_at=?", (T,),
        )
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(event)
        self.db.execute(
            "UPDATE sns_mirror_delivery_sessions SET revoked_at=NULL",
        )
        self.db.execute(
            "UPDATE sns_mirror_delivery_destinations SET enabled=0",
        )
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(event)
        self.assertEqual(self.ws.writes,0)

    def test_unapproved_row_and_account_cannot_write(self):
        event=self.claimed()
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "UPDATE sns_mirror_delivery_destinations SET account_id='night_scout'",
            )
        self.db.execute(
            "UPDATE sns_mirror_delivery_destinations SET service_subject='outsider_service'",
        )
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(event)
        self.assertEqual(self.ws.writes,0)

    def test_operational_sheet_cannot_be_target(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                """UPDATE sns_mirror_delivery_destinations
                   SET reporting_spreadsheet_id=operational_spreadsheet_id""",
            )
        with self.assertRaises(FixedRowMirrorBlocked):
            ReportingRowTarget(ORIGINAL,ORIGINAL,TAB,ROW).validate()

    def test_wrong_worksheet_spreadsheet_id_blocks_write(self):
        event=self.claimed()
        self.ws.spreadsheet_id=ORIGINAL
        result=self.deliver(event)
        self.assertEqual(result["status"],"OUTCOME_UNKNOWN_BLOCKED")
        self.assertEqual(self.ws.writes,0)

    def test_wrong_worksheet_tab_blocks_write(self):
        event=self.claimed()
        self.ws.title="operational_queue"
        result=self.deliver(event)
        self.assertEqual(result["status"],"OUTCOME_UNKNOWN_BLOCKED")
        self.assertEqual(self.ws.writes,0)

    def test_untrusted_reporting_header_blocks_write(self):
        event=self.claimed()
        self.ws.header=["unknown_header"]*12
        result=self.deliver(event)
        self.assertEqual(result["status"],"OUTCOME_UNKNOWN_BLOCKED")
        self.assertEqual(self.ws.writes,0)

    def test_one_realistic_gspread_row_update_and_exact_readback(self):
        event=self.claimed()
        result=self.deliver(event)
        self.assertEqual(result["status"],"READBACK_VERIFIED_BLOCKED")
        self.assertTrue(result["reporting_write_attempted"])
        self.assertTrue(result["reporting_readback_matched"])
        self.assertFalse(result["publish_authorized"])
        self.assertFalse(result["operational_queue_modified"])
        self.assertEqual(self.ws.writes,1)
        self.assertEqual(len(self.ws.values),12)
        self.assertEqual(self.ws.get_calls[-1],(f"A{ROW}:L{ROW}","FORMULA"))
        self.assertEqual(self.ws.update_calls[0][0],f"A{ROW}:L{ROW}")
        self.assertEqual(self.ws.update_calls[0][2],"RAW")
        self.assertEqual(
            row_to_preview(self.ws.values),
            self.writer.mirror_previews()[0],
        )

    def test_duplicate_write_never_retried(self):
        event=self.claimed()
        self.deliver(event)
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(event,operation_id="delivery_retry_20261012_000001")
        self.assertEqual(self.ws.writes,1)

    def test_timeout_after_write_is_unknown_until_read_only_reconciliation(self):
        event=self.claimed()
        self.ws.fail_after_write=True
        result=self.deliver(event)
        self.assertEqual(result["status"],"OUTCOME_UNKNOWN_BLOCKED")
        self.assertEqual(self.ws.writes,1)
        self.ws.fail_after_write=False
        recovered=self.recover(event)
        self.assertEqual(recovered["status"],"RECONCILED_BLOCKED")
        self.assertTrue(recovered["reporting_readback_matched"])
        self.assertEqual(self.ws.writes,1)

    def test_timeout_before_write_unknown_does_not_retry(self):
        event=self.claimed()
        self.ws.fail_before_write=True
        result=self.deliver(event)
        self.assertEqual(result["status"],"OUTCOME_UNKNOWN_BLOCKED")
        self.assertEqual(self.ws.writes,0)
        self.ws.fail_before_write=False
        with self.assertRaises(MirrorDeliveryBlocked):
            self.recover(event)
        self.assertEqual(self.ws.writes,0)

    def test_recovery_late_after_reviewer_claim_expires(self):
        event=self.claimed()
        self.ws.fail_after_write=True
        self.deliver(event)
        self.ws.fail_after_write=False
        result=self.recover(event,as_of=NOW+timedelta(seconds=65))
        self.assertEqual(result["status"],"RECONCILED_BLOCKED")
        self.assertEqual(self.ws.writes,1)

    def test_stale_writer_rejected_before_network(self):
        event=self.claimed()
        self.change("HOLD")
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(event)
        self.assertEqual(self.ws.writes,0)

    def test_existing_same_projection_is_readback_only(self):
        event=self.claimed()
        self.ws.values=preview_to_row(self.writer.mirror_previews()[0])
        result=self.deliver(event)
        self.assertEqual(result["status"],"READBACK_VERIFIED_BLOCKED")
        self.assertFalse(result["reporting_write_attempted"])
        self.assertEqual(self.ws.writes,0)

    def test_valid_older_version_mirror_gets_bounded_update(self):
        self.prepare()
        prior=self.writer.mirror_previews()[0]
        self.change("HOLD")
        latest=self.writer.mirror_previews()[0]
        self.ws.values=preview_to_row(prior)
        self.claim()
        event=self.ident()
        result=self.deliver(event)
        self.assertEqual(result["status"],"READBACK_VERIFIED_BLOCKED")
        self.assertEqual(self.ws.writes,1)
        self.assertEqual(row_to_preview(self.ws.values),latest)

    def test_newer_existing_row_conflicts_without_write(self):
        event=self.claimed()
        candidate=dict(self.writer.mirror_previews()[0])
        candidate["writer_version"]+=1
        candidate["writer_event_sha256"]="f"*64
        self.ws.values=preview_to_row(candidate)
        result=self.deliver(event)
        self.assertEqual(result["status"],"CONFLICT_BLOCKED")
        self.assertEqual(self.ws.writes,0)

    def test_foreign_queue_row_conflicts_without_write(self):
        event=self.claimed()
        candidate=dict(self.writer.mirror_previews()[0])
        candidate["queue_id"]="foreign_queue"
        candidate["writer_event_sha256"]="f"*64
        self.ws.values=preview_to_row(candidate)
        result=self.deliver(event)
        self.assertEqual(result["status"],"CONFLICT_BLOCKED")
        self.assertEqual(self.ws.writes,0)

    def test_formula_and_bad_headers_are_rejected(self):
        fake=FakeGspreadWorksheet()
        adapter=GspreadReportingFixedRow(
            worksheet=fake,target=self.target,
        )
        fake.values=["=IMPORTXML(\"url\",\"//a\")"]+[""]*11
        with self.assertRaises(FixedRowMirrorBlocked):
            adapter.read()
        fake.values=[]
        fake.header=["wrong"]*12
        with self.assertRaises(FixedRowMirrorBlocked):
            adapter.read()

    def test_failed_final_db_insert_preserves_prepared_and_never_retries(self):
        event=self.claimed()
        self.db.execute(
            """CREATE TRIGGER fail_delivery_finalize
               BEFORE INSERT ON sns_mirror_delivery_events
               WHEN NEW.action='READBACK_VERIFIED'
               BEGIN SELECT RAISE(ABORT,'fault'); END""",
        )
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(event)
        self.assertEqual(
            self.engine.inspect(
                event_sha256=event,destination_id=DEST,
            )["status"],"PREPARED_BLOCKED",
        )
        self.assertEqual(self.ws.writes,1)
        self.db.execute("DROP TRIGGER fail_delivery_finalize")
        result=self.recover(event)
        self.assertEqual(result["status"],"RECONCILED_BLOCKED")
        self.assertEqual(self.ws.writes,1)

    def test_wrong_outbox_cannot_read_back_older_queue_version(self):
        event=self.claimed()
        self.ws.fail_after_write=True
        self.deliver(event)
        self.ws.fail_after_write=False
        self.change("HOLD")
        with self.assertRaises(MirrorDeliveryBlocked):
            self.recover(event)

    def test_write_target_mapping_immutable_and_unique(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                """UPDATE sns_mirror_delivery_row_map
                   SET row_number=99 WHERE destination_id=?""",(DEST,),
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                """INSERT INTO sns_mirror_delivery_row_map
                   (destination_id,account_id,slot_id,queue_id,row_number)
                   VALUES (?,?,?,?,?)""",
                (DEST,KEY[0],"slot_other","queue_other",ROW),
            )

    def test_tamper_event_and_head_detected(self):
        event=self.claimed()
        self.deliver(event)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("DELETE FROM sns_mirror_delivery_events")
        self.db.execute(
            "UPDATE sns_mirror_delivery_heads SET projection_sha256=?",
            ("f"*64,),
        )
        with self.assertRaises(MirrorDeliveryBlocked):
            self.engine.inspect(event_sha256=event,destination_id=DEST)

    def test_second_sqlite_connection_cannot_repeat_write(self):
        event=self.claimed()
        self.deliver(event)
        other=sqlite3.connect(self.path,isolation_level=None,timeout=2)
        other.execute("PRAGMA foreign_keys=ON")
        try:
            verifier=PinnedLiveMirrorServiceVerifier(
                db=other,issuer=ISSUER,
                public_keys_by_kid={KID:self.live_public},
            )
            external_idp=PinnedOperatorIdpSessionVerifier(
                db=other,issuer=IDP_ISSUER,
                public_keys_by_kid={IDP_KID:self.idp_public},
            )
            gate=PinnedTwoOperatorCanaryVerifier(
                db=other, issuer=ISSUER,
                operators_by_kid={
                    self.operator_kids[i]: (
                        self.operator_subjects[i], self.operator_public_keys[i],
                    ) for i in range(2)
                },
                identity_verifier=external_idp,
            )
            second=IsolatedSheetsMirrorDelivery(
                db=other,verifier=verifier,adapter=self.sheet_adapter,
                allow_reporting_write=True,acl_metadata=self.acl_metadata,
                expected_principal_email=self.acl_credentials.service_account_email,
                canary_approver=gate,
            )
            operation="delivery_second_connection_20261012"
            with self.assertRaises(MirrorDeliveryBlocked):
                second.deliver_once(
                    event_sha256=event,destination_id=DEST,
                    service_token=self.token_live,
                    operation_id=operation,
                    as_of=NOW,
                    canary_approval_tokens=self.operator_signoffs(
                        event=event,operation_id=operation,
                    ),
                    identity_assertion_tokens=self.idp_tokens,
                )
            self.assertEqual(self.ws.writes,1)
        finally:
            other.close()

    def test_block_other_revision_when_previous_outcome_unknown(self):
        event=self.claimed()
        self.ws.fail_after_write=True
        self.deliver(event)
        self.ws.fail_after_write=False
        self.change("HOLD")
        self.claim(operation="mirror_claim_new_revision_20261012_0001")
        other_event=self.ident()
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(
                other_event,operation_id="delivery_new_revision_20261012_001",
            )
        self.assertEqual(self.ws.writes,1)

    def test_write_claim_requires_unexpired_reviewer_lease(self):
        event=self.claimed()
        with self.assertRaises(MirrorDeliveryBlocked):
            self.deliver(event,as_of=NOW+timedelta(seconds=61))
        self.assertEqual(self.ws.writes,0)

    def test_revoked_service_prevents_read_only_recovery(self):
        event=self.claimed()
        self.ws.fail_after_write=True
        self.deliver(event)
        self.ws.fail_after_write=False
        self.db.execute("UPDATE sns_mirror_delivery_sessions SET enabled=0")
        with self.assertRaises(MirrorDeliveryBlocked):
            self.recover(event)
        self.assertEqual(self.ws.writes,1)

    def test_bad_report_header_must_not_be_created_implicitly(self):
        self.claimed()
        self.ws.header=[]
        result=self.deliver()
        self.assertEqual(result["status"],"OUTCOME_UNKNOWN_BLOCKED")
        self.assertEqual(self.ws.writes,0)
        self.assertNotIn("A1:L1",[x[0] for x in self.ws.update_calls])

    def test_unapproved_transport_must_not_be_bootstrapped(self):
        with self.assertRaises(MirrorDeliveryBlocked):
            IsolatedSheetsMirrorDelivery(
                db=self.db,verifier=self.live_verifier,
                adapter=object(),allow_reporting_write=True,
            )

    def test_no_provider_sdk_ever_invoked_during_tests(self):
        self.assertEqual(self.ws.writes,0)
        self.assertEqual(self.ws.get_calls,[])


if __name__ == "__main__":
    unittest.main()
