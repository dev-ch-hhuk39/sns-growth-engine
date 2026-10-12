#!/usr/bin/env python3
"""Offline 5B-5D WSGI console security, real RSA signature and SQLite checks."""
from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import sqlite3
import sys
import tempfile
from datetime import timedelta
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from media_review_canonical_adapter import CanonicalProtectedReviewReader  # noqa: E402
from media_review_protected_evidence import (  # noqa: E402
    ProtectedEvidenceVault, initialize_trust_schema,
)
from media_review_queue_reconciliation import (  # noqa: E402
    ReviewQueueReconciliation, initialize_reconciliation_schema,
)
from media_review_secure_console import (  # noqa: E402
    ProtectedReviewConsole, ConsoleBlocked, COOKIE_NAME,
)
from media_review_transactional_ledger import initialize_review_schema  # noqa: E402
from media_review_verified_identity import (  # noqa: E402
    PinnedRS256SessionVerifier, SQLiteSessionAuthority,
)
from test_media_review_trusted_precommit import (  # noqa: E402
    NOW, ISSUER, good_context,
)

ACCOUNT = "liver_manager"
KEY = (ACCOUNT, "lm_1800_clip_media", "clip_001")
KID = "key_review_console_20261012"
SUB = "reviewer_0001"
SID = "session_5b5d_0001"
JTI = "jwt_id_5b5d_0001"
T = int(NOW.timestamp())
ORIGIN = "https://reviews.example.test"
PROOF_PREFIX = b"CONFIDENTIAL_ORIGINAL_PROOF_"


def b64(data):
    return base64.urlsafe_b64encode(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode(),
    ).decode().rstrip("=")


class TrustedSnapshotFixture:
    def __init__(self, source):
        self.source = source
        self.offline = False
        self.calls = 0

    def load(self, account_id, slot_id, queue_id):
        self.calls += 1
        if self.offline:
            raise OSError("private backend path; sensitive token")
        if (account_id, slot_id, queue_id) != KEY:
            raise ValueError("not in the authorized source")
        c = self.source
        return (
            copy.deepcopy(c.plan), copy.deepcopy(c.receipts),
            copy.deepcopy(c.queue),
        )


class TrustedInboxFixture:
    def __init__(self):
        self.keys = [KEY]
        self.offline = False

    def list_candidate_keys(self, account_id, limit):
        if self.offline:
            raise OSError("source failed with private access token")
        if account_id != ACCOUNT:
            return []
        return list(self.keys[:limit])


class FormCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        fields = dict(attrs)
        if tag == "form":
            self.current = {
                "action": fields.get("action", ""),
                "fields": {},
            }
        elif tag == "input" and self.current is not None:
            name = fields.get("name")
            if name:
                self.current["fields"][name] = fields.get("value", "")
        elif tag == "select" and self.current is not None:
            self._choice = fields.get("name")
        elif tag == "option" and self.current is not None:
            choice = getattr(self, "_choice", None)
            if choice and choice not in self.current["fields"]:
                self.current["fields"][choice] = fields.get("value", "")

    def handle_endtag(self, tag):
        if tag == "form" and self.current is not None:
            self.forms.append(self.current)
            self.current = None
            self._choice = None


class SecureConsoleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.public = cls.private.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    @classmethod
    def sign(cls, overrides=None, headers=None):
        claims = {
            "iss": ISSUER, "aud": "sns-growth-media-review", "sub": SUB,
            "sid": SID, "jti": JTI, "amr": ["pwd", "mfa"],
            "iat": T - 200, "nbf": T - 201, "exp": T + 3600,
            "auth_time": T - 220, "mfa_at": T - 120,
        }
        claims.update(overrides or {})
        head = {"alg": "RS256", "kid": KID, "typ": "JWT"}
        head.update(headers or {})
        payload = b64(head) + "." + b64(claims)
        signature = cls.private.sign(
            payload.encode("ascii"), padding.PKCS1v15(), hashes.SHA256(),
        )
        return payload + "." + base64.urlsafe_b64encode(signature).decode().rstrip("=")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "review.sqlite")
        self.token = self.sign()
        self.db = self.connection()
        initialize_review_schema(self.db)
        initialize_trust_schema(self.db)
        initialize_reconciliation_schema(self.db)
        self.db.execute(
            """INSERT INTO sns_review_sessions
               (session_id,subject,issuer,token_sha256,token_jti,
                authenticated_at,mfa_at,expires_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (SID, SUB, ISSUER, hashlib.sha256(self.token.encode()).hexdigest(),
             JTI, T - 220, T - 120, T + 3600),
        )
        self.db.execute(
            """INSERT INTO sns_review_account_grants
               (subject,account_id,role,enabled) VALUES (?,?,?,1)""",
            (SUB, ACCOUNT, "MEDIA_REVIEWER"),
        )
        self.context = good_context()
        self.snapshot = TrustedSnapshotFixture(self.context)
        self.inbox = TrustedInboxFixture()
        auth = self.verifier(self.db)
        vault = ProtectedEvidenceVault(self.db)
        for i, item in enumerate(self.context.evidence_by_id.values()):
            fields = (
                "evidence_id", "kind", "account_id", "slot_id", "queue_id",
                "media_asset_id", "source_id", "usage_scope",
                "allowed_platforms", "allowed_territories",
                "rights_valid_from", "rights_expires_at",
            )
            vault.attest(
                metadata={k: copy.deepcopy(item[k]) for k in fields},
                original_bytes=PROOF_PREFIX + str(i).encode(),
                human_verified_original=True, bearer_token="Bearer " + self.token,
                verifier=auth, trusted_issuer=ISSUER,
                operation_id=f"evop_console_proof_{i:06d}_2026", as_of=NOW,
            )
        self.console = ProtectedReviewConsole(
            origin=ORIGIN, trusted_issuer=ISSUER, csrf_key=b"s" * 32,
            database_factory=self.connection,
            verifier_factory=self.verifier,
            canonical_factory=lambda db: CanonicalProtectedReviewReader(
                source=self.snapshot, vault=ProtectedEvidenceVault(db),
            ),
            inbox=self.inbox, clock=lambda: NOW,
        )

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def connection(self):
        db = sqlite3.connect(self.path, isolation_level=None, timeout=2)
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def verifier(self, db):
        return PinnedRS256SessionVerifier(
            issuer=ISSUER, public_keys_by_kid={KID: self.public},
            sessions=SQLiteSessionAuthority(db),
        )

    def hit(
        self, action="/review", *, account=ACCOUNT, form=None,
        method=None, token=None, origin=ORIGIN, host="reviews.example.test",
        scheme="https", cookie=None, content_type="application/x-www-form-urlencoded",
        raw=None, fetch_site="same-origin",
    ):
        method = method or ("GET" if form is None and raw is None else "POST")
        if method == "GET":
            query = urlencode({"account": account})
            body = b""
        else:
            query = ""
            body = raw if raw is not None else urlencode(form or {}).encode()
        env = {
            "REQUEST_METHOD": method, "PATH_INFO": action, "QUERY_STRING": query,
            "wsgi.url_scheme": scheme, "HTTP_HOST": host, "HTTP_ORIGIN": origin,
            "HTTP_SEC_FETCH_SITE": fetch_site,
            "HTTP_COOKIE": cookie if cookie is not None else (
                COOKIE_NAME + "=" + (self.token if token is None else token)
            ),
            "CONTENT_TYPE": content_type, "CONTENT_LENGTH": str(len(body)),
            "wsgi.input": io.BytesIO(body),
        }
        captured = {}

        def start_response(status, headers):
            captured["status"] = int(status.split(" ", 1)[0])
            captured["headers"] = dict(headers)

        content = b"".join(self.console(env, start_response))
        return captured["status"], captured["headers"], content

    def form_from_page(self, action):
        status, headers, page = self.hit()
        self.assertEqual(status, 200)
        parser = FormCollector()
        parser.feed(page.decode())
        matches = [f["fields"] for f in parser.forms if f["action"] == action]
        self.assertTrue(matches, (action, page[:400]))
        return dict(matches[0])

    def records(self):
        return self.db.execute(
            "SELECT COUNT(*) FROM sns_media_review_events"
        ).fetchone()[0]

    def test_review_page_shows_metadata_not_original_caption_or_jwt(self):
        status, headers, body = self.hit()
        page = body.decode()
        self.assertEqual(status, 200)
        self.assertIn("証跡原本を取得", page)
        self.assertIn("確認したレビューを台帳に記録", page)
        self.assertIn("投稿許可にはなりません", page)
        self.assertIn("no-store", headers["Cache-Control"])
        self.assertIn("default-src 'none'", headers["Content-Security-Policy"])
        self.assertIn("DENY", headers["X-Frame-Options"])
        for private in (self.token, PROOF_PREFIX.decode(), "PRIVATE_POST_BODY",
                        "SENSITIVE_EVIDENCE", "secret.example"):
            self.assertNotIn(private, page)
        self.assertEqual(self.records(), 0)

    def test_guarded_review_from_form_only_records_and_does_not_post(self):
        form = self.form_from_page("/review/record")
        self.assertEqual(form["confirm"], "yes")
        original = copy.deepcopy(self.context)
        status, _, body = self.hit("/review/record", form=form)
        self.assertEqual(status, 200, body[:150])
        self.assertIn("投稿許可はありません", body.decode())
        self.assertEqual(self.records(), 1)
        self.assertEqual(
            ReviewQueueReconciliation(self.db).barrier(*KEY)["state"],
            "REVIEW_RECORDED_BLOCKED",
        )
        self.assertEqual(original, self.context)
        self.assertEqual(self.snapshot.calls > 0, True)
        self.assertNotIn(PROOF_PREFIX, body)

    def test_revoke_after_proof_and_queue_disappear(self):
        status, _, _ = self.hit("/review/record", form=self.form_from_page("/review/record"))
        self.assertEqual(status, 200)
        self.snapshot.offline = True
        self.inbox.keys = []
        revoke = self.form_from_page("/review/revoke")
        revoke["reason_code"] = "consent_withdrawn"
        self.assertEqual(self.hit("/review/revoke", form=revoke)[0], 200)
        self.assertEqual(self.records(), 2)
        self.assertEqual(
            ReviewQueueReconciliation(self.db).barrier(*KEY)["state"],
            "REVOKED_BLOCKED",
        )

    def test_inbox_outage_preserves_existing_revoke_without_new_review(self):
        form = self.form_from_page("/review/record")
        self.assertEqual(self.hit("/review/record", form=form)[0], 200)
        self.inbox.offline = True
        revoke = self.form_from_page("/review/revoke")
        revoke["reason_code"] = "review_reopened"
        self.assertEqual(self.hit("/review/revoke", form=revoke)[0], 200)
        self.assertEqual(self.records(), 2)
        status, _, page = self.hit()
        self.assertEqual(status, 200)
        self.assertNotIn("op_rec_", page.decode())

    def test_proof_download_is_authenticated_attached_and_nonsniff(self):
        data = self.form_from_page("/review/original")
        status, headers, original = self.hit("/review/original", form=data)
        self.assertEqual(status, 200)
        self.assertTrue(original.startswith(PROOF_PREFIX))
        self.assertEqual(headers["Content-Type"], "application/octet-stream")
        self.assertIn("attachment;", headers["Content-Disposition"])
        self.assertIn("no-store", headers["Cache-Control"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertFalse(self.records())

    def test_candidate_caption_is_only_available_via_authenticated_text(self):
        status, headers, page = self.hit()
        self.assertEqual(status, 200)
        self.assertNotIn("PRIVATE_POST_BODY", page.decode())
        form = self.form_from_page("/review/candidate")
        status, headers, data = self.hit("/review/candidate", form=form)
        self.assertEqual(status, 200)
        self.assertEqual(data, b"PRIVATE_POST_BODY")
        self.assertEqual(headers["Content-Type"], "text/plain; charset=utf-8")
        self.assertIn("no-store", headers["Cache-Control"])
        bad = dict(form)
        bad["csrf"] = "0" * 64
        self.assertEqual(self.hit("/review/candidate", form=bad)[0], 403)
        self.assertFalse(self.records())

    def test_candidate_text_html_is_not_interpreted_as_active_markup(self):
        self.context.queue["public_post_text"] = "<script>do_not_execute()</script>"
        form = self.form_from_page("/review/candidate")
        status, headers, body = self.hit("/review/candidate", form=form)
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "text/plain; charset=utf-8")
        self.assertIn(b"<script>", body)
        status, _, page = self.hit()
        self.assertEqual(status, 200)
        self.assertNotIn("<script>do_not_execute()", page.decode())

    def test_non_member_evidence_is_not_downloadable(self):
        data = self.form_from_page("/review/original")
        data["evidence_id"] = "ev_secret_not_in_current_draft"
        self.assertEqual(self.hit("/review/original", form=data)[0], 409)

    def test_queue_asset_scope_change_blocks_proof_access(self):
        data = self.form_from_page("/review/original")
        self.context.queue["media_asset_id"] = "changed_other_asset"
        self.assertEqual(self.hit("/review/original", form=data)[0], 409)

    def test_revoked_proof_is_no_longer_readable(self):
        data = self.form_from_page("/review/original")
        ProtectedEvidenceVault(self.db).revoke(
            evidence_id=data["evidence_id"],
            bearer_token="Bearer " + self.token, verifier=self.verifier(self.db),
            trusted_issuer=ISSUER, operation_id="evop_console_revoke_00001",
            expected_revision=1, as_of=NOW,
        )
        self.assertEqual(self.hit("/review/original", form=data)[0], 409)

    def test_invalid_tampered_token_missing_session_and_expired_mfa(self):
        form = self.form_from_page("/review/record")
        self.assertEqual(self.hit(token=self.token[:-6] + "AAAAAA")[0], 403)
        self.assertEqual(self.hit(cookie="")[0], 401)
        self.assertEqual(self.hit(cookie=COOKIE_NAME + "=" + self.token + "; "
                                  + COOKIE_NAME + "=" + self.token)[0], 401)
        self.db.execute(
            "UPDATE sns_review_sessions SET revoked_at=? WHERE session_id=?", (T, SID),
        )
        self.assertEqual(self.hit("/review/record", form=form)[0], 403)
        self.assertFalse(self.records())

    def test_disabled_account_permission_blocks_without_event(self):
        form = self.form_from_page("/review/record")
        self.db.execute(
            "UPDATE sns_review_account_grants SET enabled=0 WHERE subject=?", (SUB,),
        )
        self.assertEqual(self.hit("/review/record", form=form)[0], 403)
        self.assertEqual(self.hit()[0], 403)
        self.assertEqual(self.records(), 0)

    def test_unauthorized_account_no_cross_account_inbox_access(self):
        status, _, body = self.hit(account="night_scout")
        self.assertEqual(status, 403)
        self.assertNotIn("clip_001", body.decode())
        bad_form = self.form_from_page("/review/record")
        bad_form["account_id"] = "night_scout"
        self.assertEqual(self.hit("/review/record", form=bad_form)[0], 403)

    def test_origin_scheme_host_cross_site_and_malformed_form_block(self):
        data = self.form_from_page("/review/record")
        for request in (
            {"origin": "https://attacker.test"},
            {"scheme": "http"},
            {"host": "attacker.test"},
            {"fetch_site": "cross-site"},
            {"content_type": "application/json"},
            {"raw": b"garbled"},
        ):
            with self.subTest(request=request):
                status, _, _ = self.hit("/review/record", form=data, **request)
                self.assertNotEqual(status, 200)
        self.assertEqual(self.records(), 0)

    def test_wrong_csrf_bad_fields_or_no_confirmation_never_writes(self):
        good = self.form_from_page("/review/record")
        variants = [
            {**good, "csrf": "f" * 64},
            {**good, "confirm": "no"},
            {**good, "reviewer_id": SUB},
            {**good, "expected_ledger_version": "999"},
            {**good, "expected_queue_sha256": "f" * 64},
        ]
        for form in variants:
            with self.subTest(form=list(form)):
                self.assertNotEqual(self.hit("/review/record", form=form)[0], 200)
        raw = urlencode(good).encode() + b"&csrf=duplicate"
        self.assertEqual(self.hit("/review/record", raw=raw)[0], 400)
        self.assertFalse(self.records())

    def test_changed_content_same_revision_fails_stale_snapshot(self):
        form = self.form_from_page("/review/record")
        self.context.queue["public_post_text"] = "updated without revision"
        self.assertEqual(self.hit("/review/record", form=form)[0], 409)
        self.assertFalse(self.records())

    def test_replay_operation_and_stale_version_fail_closed(self):
        data = self.form_from_page("/review/record")
        self.assertEqual(self.hit("/review/record", form=data)[0], 200)
        self.assertEqual(self.hit("/review/record", form=data)[0], 409)
        self.assertEqual(self.records(), 1)
        revocation = self.form_from_page("/review/revoke")
        revocation["reason_code"] = "review_reopened"
        self.assertEqual(self.hit("/review/revoke", form=revocation)[0], 200)
        self.assertEqual(self.hit("/review/revoke", form=revocation)[0], 409)
        self.assertEqual(self.records(), 2)

    def test_oversized_forms_and_stale_session_age_are_denied(self):
        form = self.form_from_page("/review/record")
        self.assertEqual(
            self.hit("/review/record", raw=b"z" * 5000)[0], 413,
        )
        # JWT remains cryptographically signed, but session freshness
        # is independently checked by precommit _check_principal.
        self.console._clock = lambda: NOW + timedelta(minutes=31)
        self.assertEqual(self.hit("/review/record", form=form)[0], 403)
        self.assertFalse(self.records())

    def test_revocation_request_must_bind_exact_ledger_head(self):
        form = self.form_from_page("/review/record")
        self.assertEqual(self.hit("/review/record", form=form)[0], 200)
        revoke = self.form_from_page("/review/revoke")
        revoke["expected_ledger_head_sha256"] = "f" * 64
        self.assertEqual(self.hit("/review/revoke", form=revoke)[0], 409)
        self.assertEqual(self.records(), 1)

    def test_html_escapes_canonical_metadata_and_inbox_limits(self):
        self.context.queue["revision"] = 'rev_xxx"<script>'
        status, _, body = self.hit()
        page = body.decode()
        self.assertEqual(status, 200)
        self.assertNotIn('rev_xxx"<script>', page)
        self.assertIn("&quot;", page)
        self.assertNotIn("確認したレビューを台帳に記録", page)
        self.inbox.keys = [KEY] * 31
        self.assertEqual(self.hit()[0], 503)

    def test_stylesheet_is_static_and_no_session_material(self):
        status, headers, css = self.hit("/review/style.css", method="GET")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "text/css; charset=utf-8")
        self.assertIn(b"focus-visible", css)
        self.assertNotIn(self.token.encode(), css)
        self.assertIn("no-store", headers["Cache-Control"])
        self.assertEqual(self.records(), 0)

    def test_no_trusted_session_or_weak_csrf_key_can_be_bootstrapped(self):
        with self.assertRaises(ConsoleBlocked):
            ProtectedReviewConsole(
                origin=ORIGIN, trusted_issuer=ISSUER, csrf_key=b"short",
                database_factory=self.connection,
                verifier_factory=self.verifier,
                canonical_factory=lambda db: CanonicalProtectedReviewReader(
                    source=self.snapshot, vault=ProtectedEvidenceVault(db),
                ),
                inbox=self.inbox,
            )
        self.assertEqual(self.hit("/review/not-an-endpoint", method="GET")[0], 404)

    def test_missing_trusted_source_blocks_review_and_no_secret_in_error(self):
        self.snapshot.offline = True
        status, _, body = self.hit()
        self.assertEqual(status, 200)
        self.assertIn("候補と証跡の取得に失敗", body.decode())
        self.assertNotIn("private backend", body.decode())
        self.assertEqual(self.records(), 0)


if __name__ == "__main__":
    unittest.main()
