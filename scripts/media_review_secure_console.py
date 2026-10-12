#!/usr/bin/env python3
"""5B-5D: injection-only authenticated reviewer console and WSGI transport.

No executable server, bootstrap account, key discovery, login endpoint, queue
writer, READY transition or publisher. Production requires separately
provisioned trusted IdP/queue readers, cookies, TLS and protected DB.
"""
from __future__ import annotations

import hashlib
import json
import hmac
import html
import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Protocol
from urllib.parse import parse_qs, urlsplit

from build_media_human_review_plan import MEDIA_SLOTS
from build_media_review_approval_receipts import (
    _sha256, _validate_history, _validate_plan,
)
from media_review_canonical_adapter import CanonicalProtectedReviewReader
from media_review_protected_evidence import ProtectedEvidenceVault
from media_review_queue_reconciliation import (
    ReviewQueueReconciliation, queue_fingerprint, _key,
)
from media_review_transactional_ledger import (
    REVOKE_REASONS, ZERO, _head,
    _validate_event_history, record_review, revoke_review,
)
from media_review_trusted_precommit import (
    CanonicalReviewContext, ReviewRequest,
    _check_principal, evaluate_precommit,
)
from media_review_verified_identity import (
    PinnedRS256SessionVerifier,
)

COOKIE_NAME = "__Host-sns-review"
MAX_FORM_BYTES = 4096
MAX_INBOX_ITEMS = 30
MAX_COOKIE_BYTES = 6000
OP_RE = re.compile(r"op_[A-Za-z0-9_.:-]{12,110}\Z")
SAFE_VERSION = re.compile(r"(?:0|[1-9][0-9]{0,2})\Z")
GET_FIELDS = frozenset({"account"})
POST_RECORD = frozenset({
    "account_id", "slot_id", "queue_id", "csrf", "operation_id",
    "confirm", "expected_ledger_version", "expected_ledger_head_sha256",
    "expected_queue_revision", "expected_queue_sha256", "expected_plan_sha256",
    "expected_receipts_head_sha256", "draft_event_sha256",
})
POST_REVOKE = frozenset({
    "account_id", "slot_id", "queue_id", "csrf", "operation_id",
    "expected_ledger_version", "expected_ledger_head_sha256",
    "reason_code", "confirm",
})
POST_ORIGINAL = frozenset({
    "account_id", "slot_id", "queue_id", "csrf", "evidence_id",
})
POST_CANDIDATE = frozenset({"account_id", "slot_id", "queue_id", "csrf"})
SECURITY_HEADERS = (
    ("Cache-Control", "no-store, private"),
    ("Pragma", "no-cache"),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("X-Frame-Options", "DENY"),
    ("Content-Security-Policy",
     "default-src 'none'; base-uri 'none'; object-src 'none'; "
     "frame-ancestors 'none'; form-action 'self'; style-src 'self'"),
)
CSS = """
:root{font-family:-apple-system,BlinkMacSystemFont,'Hiragino Kaku Gothic ProN',
'Yu Gothic',sans-serif;color:#243047;background:#f5f7fa}
*{box-sizing:border-box}
body{margin:0;padding:3rem 1.5rem}
main{max-width:900px;margin:0 auto}
h1{font-size:1.9rem;letter-spacing:-.02em;margin:0 0 1.3rem}
h2{font-size:1.15rem;margin:0 0 .7rem}
h3{font-size:1rem;margin:1.5rem 0 .7rem}
section{background:white;border:1px solid #dfe5ed;border-radius:14px;
padding:1.5rem;margin:1.25rem 0;box-shadow:0 2px 11px rgba(20,30,50,.045)}
section>p{overflow-wrap:anywhere}
ul{list-style:none;padding:0}
li{padding:1rem;margin:.5rem 0;background:#f5f7fa;border-radius:8px;
overflow-wrap:anywhere}
form{margin:1rem 0;display:flex;flex-wrap:wrap;gap:.7rem;align-items:center}
label{display:block;flex-basis:100%;line-height:1.7;font-size:.92rem}
button{background:#184e8f;border:0;border-radius:8px;color:white;
padding:.7rem 1.1rem;font-size:.95rem;font-weight:600;cursor:pointer}
button:hover{background:#113a6b}
button:focus-visible,select:focus-visible,input:focus-visible{
outline:3px solid #d18d23;outline-offset:3px}
select{padding:.5rem;border:1px solid #aab6c7;border-radius:8px}
hr{border:0}
main>p{line-height:1.8}
@media(max-width:600px){body{padding:1.2rem .8rem}section{padding:1rem}}
""".strip().encode("utf-8")
RESPONSES = {
    200: "200 OK", 400: "400 Bad Request", 401: "401 Unauthorized",
    403: "403 Forbidden", 404: "404 Not Found", 405: "405 Method Not Allowed",
    409: "409 Conflict", 413: "413 Content Too Large",
    421: "421 Misdirected Request", 503: "503 Service Unavailable",
}


class ConsoleBlocked(ValueError):
    """Only short reason codes: never use raw request/provider exception text."""

    def __init__(self, code: str, status: int = 403) -> None:
        super().__init__(code)
        self.status = status


class TrustedReviewInbox(Protocol):
    def list_candidate_keys(
        self, account_id: str, limit: int,
    ) -> list[tuple[str, str, str]]:
        """Return server-owned keys, NEVER untrusted client-supplied JSON."""


@dataclass(frozen=True)
class ConsoleResult:
    status: int
    data: bytes
    content_type: str = "text/html; charset=utf-8"
    headers: tuple[tuple[str, str], ...] = ()


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _hidden(name: str, value: Any) -> str:
    return (f'<input type="hidden" name="{_escape(name)}" '
            f'value="{_escape(value)}">')


def _exact_values(raw: str, allowed: frozenset[str]) -> dict[str, str]:
    try:
        fields = parse_qs(
            raw, keep_blank_values=True, strict_parsing=True,
            max_num_fields=18, encoding="utf-8", errors="strict",
        )
    except (ValueError, UnicodeError):
        raise ConsoleBlocked("input_invalid", 400) from None
    if set(fields) != allowed or any(len(value) != 1 for value in fields.values()):
        raise ConsoleBlocked("input_invalid", 400)
    return {key: value[0] for key, value in fields.items()}


def _cookie(environ: dict[str, Any]) -> str:
    raw = environ.get("HTTP_COOKIE", "")
    if not isinstance(raw, str) or len(raw) > MAX_COOKIE_BYTES:
        raise ConsoleBlocked("session_unavailable", 401)
    found: list[str] = []
    for field in raw.split(";"):
        if "=" not in field:
            continue
        name, value = field.strip().split("=", 1)
        if name == COOKIE_NAME:
            found.append(value)
    if (len(found) != 1 or len(found[0]) > 4096
            or re.fullmatch(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", found[0]) is None):
        raise ConsoleBlocked("session_unavailable", 401)
    return found[0]


def _candidate_request(
    context: CanonicalReviewContext, key: tuple[str, str, str],
) -> ReviewRequest:
    try:
        plan = _validate_plan(context.plan)
        plan_digest = _sha256(context.plan)
        events, head_digest = _validate_history(
            context.receipts, plan_digest, plan,
        )
        matching = [
            event for event in events
            if (event["account_id"], event["slot_id"], event["queue_id"]) == key
        ]
        if not matching:
            raise ValueError()
        latest = matching[-1]
        return ReviewRequest(
            account_id=key[0], slot_id=key[1], queue_id=key[2],
            expected_queue_revision=context.queue["revision"],
            expected_plan_sha256=plan_digest,
            expected_receipts_head_sha256=head_digest,
            draft_event_sha256=latest["event_sha256"],
            confirm_human_review=True,
            expected_queue_sha256=queue_fingerprint(context.queue),
        )
    except Exception:
        raise ConsoleBlocked("candidate_unavailable", 409) from None


def _ledger(db: sqlite3.Connection, key: tuple[str, str, str]) -> dict[str, Any]:
    try:
        head = _head(db, key)
        _validate_event_history(db, key, head)
        return head
    except Exception:
        raise ConsoleBlocked("review_history_unavailable", 503) from None


class ProtectedReviewConsole:
    """WSGI handler with no default verifier, DB, inbox, host, or HTTP runner."""

    def __init__(
        self, *,
        origin: str,
        trusted_issuer: str,
        csrf_key: bytes,
        database_factory: Callable[[], sqlite3.Connection],
        verifier_factory: Callable[[sqlite3.Connection], PinnedRS256SessionVerifier],
        canonical_factory: Callable[[sqlite3.Connection], CanonicalProtectedReviewReader],
        inbox: TrustedReviewInbox,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        parsed = urlsplit(origin)
        if (parsed.scheme != "https" or not parsed.netloc or parsed.path not in ("", "/")
                or parsed.query or parsed.fragment or parsed.username or parsed.password
                or not isinstance(trusted_issuer, str) or not trusted_issuer.startswith("https://")
                or not isinstance(csrf_key, bytes) or len(csrf_key) < 32
                or any(x is None for x in (database_factory, verifier_factory, canonical_factory, inbox))):
            raise ConsoleBlocked("console_configuration_invalid", 503)
        self.origin = origin.rstrip("/")
        self.host = parsed.netloc
        self.trusted_issuer = trusted_issuer
        self._csrf_key = csrf_key
        self._db_factory = database_factory
        self._verifier_factory = verifier_factory
        self._canonical_factory = canonical_factory
        self._inbox = inbox
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def _csrf(
        self, token: str, action: str, key: tuple[str, str, str],
    ) -> str:
        subject = hashlib.sha256(token.encode("ascii")).hexdigest()
        msg = "\0".join(("sns-media-review-console-v1", subject, action, *key))
        return hmac.new(
            self._csrf_key, msg.encode("utf-8"), hashlib.sha256,
        ).hexdigest()

    def _authenticate(
        self, verifier: PinnedRS256SessionVerifier, token: str,
        account: str, now: datetime,
    ) -> None:
        slot = next((s for a, s in MEDIA_SLOTS if a == account), None)
        if slot is None:
            raise ConsoleBlocked("account_not_supported", 403)
        sentinel = ReviewRequest(
            account, slot, "review_console_auth", "reviewrevision0001",
            ZERO, ZERO, ZERO, True,
        )
        try:
            principal = verifier.verify(token, now=now)
            _check_principal(principal, sentinel, now, self.trusted_issuer)
        except Exception:
            raise ConsoleBlocked("reviewer_not_authorized", 403) from None

    def _inbox_keys(
        self, db: sqlite3.Connection, account: str,
    ) -> list[tuple[str, str, str]]:
        try:
            try:
                listed = self._inbox.list_candidate_keys(account, MAX_INBOX_ITEMS)
            except Exception:
                # No new approvals if the source is unavailable. Still allow
                # authenticated revocation of existing local ledger records.
                listed = []
            if not isinstance(listed, list) or len(listed) > MAX_INBOX_ITEMS:
                raise ValueError()
            results: set[tuple[str, str, str]] = set()
            for key in listed:
                if not isinstance(key, tuple) or len(key) != 3 or key[0] != account:
                    raise ValueError()
                _key(*key)
                if key in results:
                    raise ValueError()
                results.add(key)
            # Revocation must remain available if Sheets removes the queue row.
            active = db.execute(
                """SELECT account_id,slot_id,queue_id FROM sns_media_review_heads
                   WHERE account_id=? AND review_state='REVIEW_RECORDED_ONLY'
                   ORDER BY updated_at LIMIT ?""", (account, MAX_INBOX_ITEMS + 1),
            ).fetchall()
            if len(active) > MAX_INBOX_ITEMS:
                raise ValueError()
            for row in active:
                item = tuple(row)
                _key(*item)
                results.add(item)
            if len(results) > MAX_INBOX_ITEMS:
                raise ValueError()
            return sorted(results)
        except Exception:
            raise ConsoleBlocked("review_inbox_unavailable", 503) from None

    def _form(
        self, *, action: str, key: tuple[str, str, str],
        token: str, extras: dict[str, Any],
        caption: str,
    ) -> str:
        fields = {
            "account_id": key[0], "slot_id": key[1], "queue_id": key[2],
            "csrf": self._csrf(token, action, key),
            **extras,
        }
        content = "".join(_hidden(name, value) for name, value in fields.items())
        if action == "record":
            content += ('<label><input type="checkbox" name="confirm" value="yes" '
                        'required>権利原本と投稿内容を確認しました'
                        '（記録のみ、投稿許可にはなりません）</label>')
        elif action == "revoke":
            choices = "".join(
                f'<option value="{_escape(code)}">{_escape(code)}</option>'
                for code in sorted(REVOKE_REASONS)
            )
            content += (
                f'<label>取消理由<select name="reason_code">{choices}</select></label>'
                '<label><input type="checkbox" name="confirm" value="yes" required>'
                'レビュー記録を取り消す</label>'
            )
        return (f'<form method="post" action="/review/{_escape(action)}">'
                f'{content}<button type="submit">{_escape(caption)}</button></form>')

    def _page(
        self, *, db: sqlite3.Connection, canonical: CanonicalProtectedReviewReader,
        verifier: PinnedRS256SessionVerifier, token: str,
        account: str, now: datetime,
    ) -> ConsoleResult:
        keys = self._inbox_keys(db, account)
        guard = ReviewQueueReconciliation(db)
        cards: list[str] = []
        for key in keys:
            head = _ledger(db, key)
            barrier = guard.barrier(*key)
            safe_state = _escape(barrier["state"])
            block = [
                '<section><h2>候補 ' + _escape(key[1]) + ' / ' + _escape(key[2]) + '</h2>',
                '<p>レビュー状態: ' + _escape(head["state"]) +
                ' / 整合性: ' + safe_state + '</p>',
            ]
            if head["state"] == "REVIEW_RECORDED_ONLY":
                # Revocation is possible even if source rights were withdrawn.
                block.append(self._form(
                    action="revoke", key=key, token=token, extras={
                        "operation_id": "op_rev_" + secrets.token_hex(16),
                        "expected_ledger_version": head["version"],
                        "expected_ledger_head_sha256": head["hash"],
                    }, caption="レビュー記録を取消",
                ))
            try:
                context = canonical.load_current(*key)
                request = _candidate_request(context, key)
                block.append('<p>キュー revision: ' +
                             _escape(request.expected_queue_revision) + '</p>')
                block.append(self._form(
                    action="candidate", key=key, token=token,
                    extras={}, caption="投稿文を確認（保護されたテキスト）",
                ))
                proof_rows = sorted(context.evidence_by_id.values(), key=lambda v: v["kind"])
                if proof_rows:
                    block.append('<h3>権利・出典・品質証跡（原本を確認してください）</h3><ul>')
                    for proof in proof_rows:
                        eid = str(proof["evidence_id"])
                        block.append(
                            '<li>' + _escape(proof["kind"]) + ' / ' +
                            _escape(eid) + ' / ' +
                            _escape(proof["verification_status"]) +
                            ' / 期限 ' + _escape(proof["rights_expires_at"]) +
                            self._form(
                                action="original", key=key, token=token,
                                extras={"evidence_id": eid},
                                caption="証跡原本を取得",
                            ) + '</li>'
                        )
                    block.append('</ul>')
                if head["state"] != "REVIEW_RECORDED_ONLY" and barrier["state"] in {
                    "NO_BINDING", "REVOKED_BLOCKED",
                }:
                    try:
                        evaluate_precommit(
                            request, "Bearer " + token, verifier=verifier,
                            canonical=canonical, trusted_issuer=self.trusted_issuer,
                            as_of=now,
                        )
                    except Exception:
                        block.append("<p>レビュー記録不可：認証・権利・候補条件の確認が必要です。</p>")
                    else:
                        block.append(self._form(
                            action="record", key=key, token=token, extras={
                                "operation_id": "op_rec_" + secrets.token_hex(16),
                                "expected_ledger_version": head["version"],
                                "expected_ledger_head_sha256": head["hash"],
                                "expected_queue_revision": request.expected_queue_revision,
                                "expected_queue_sha256": request.expected_queue_sha256,
                                "expected_plan_sha256": request.expected_plan_sha256,
                                "expected_receipts_head_sha256": request.expected_receipts_head_sha256,
                                "draft_event_sha256": request.draft_event_sha256,
                            }, caption="確認したレビューを台帳に記録",
                        ))
            except Exception:
                block.append("<p>候補と証跡の取得に失敗。記録できません。</p>")
            block.append("</section><hr>")
            cards.append("".join(block))
        body = (
            '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>SNS Growth Engine | 保護されたレビュー</title>'
            '<link rel="stylesheet" href="/review/style.css"></head><body>'
            '<main><h1>メディアレビュー</h1>'
            '<p>対象アカウント: ' + _escape(account) + '</p>'
            '<p><strong>すべて記録専用です。正式承認・READY変更・投稿権限はありません。</strong></p>'
            + ("".join(cards) if cards else "<p>担当候補はありません。</p>")
            + '</main></body></html>'
        )
        return ConsoleResult(200, body.encode("utf-8"))

    def _record(
        self, *, db: sqlite3.Connection, verifier: PinnedRS256SessionVerifier,
        canonical: CanonicalProtectedReviewReader, token: str,
        key: tuple[str, str, str], form: dict[str, str], now: datetime,
    ) -> ConsoleResult:
        if form["confirm"] != "yes" or not OP_RE.fullmatch(form["operation_id"]):
            raise ConsoleBlocked("review_confirmation_invalid", 400)
        head = _ledger(db, key)
        version = form["expected_ledger_version"]
        if (not SAFE_VERSION.fullmatch(version) or int(version) != head["version"]
                or form["expected_ledger_head_sha256"] != head["hash"]):
            raise ConsoleBlocked("review_stale", 409)
        try:
            req = ReviewRequest(
                account_id=key[0], slot_id=key[1], queue_id=key[2],
                expected_queue_revision=form["expected_queue_revision"],
                expected_queue_sha256=form["expected_queue_sha256"],
                expected_plan_sha256=form["expected_plan_sha256"],
                expected_receipts_head_sha256=form["expected_receipts_head_sha256"],
                draft_event_sha256=form["draft_event_sha256"],
                confirm_human_review=True,
            )
            result = record_review(
                db, req, "Bearer " + token,
                verifier=verifier, canonical=canonical,
                trusted_issuer=self.trusted_issuer, operation_id=form["operation_id"],
                expected_ledger_version=int(version),
                queue_authority=ReviewQueueReconciliation(db), as_of=now,
            )
        except Exception:
            raise ConsoleBlocked("review_conflict_or_unavailable", 409) from None
        if (result.get("status") != "ISOLATED_REVIEW_LEDGER_RECORDED_NOT_AUTHORIZED"
                or result.get("authenticated_approval_integrated") is not False
                or result.get("external_queue_atomicity_guaranteed") is not False
                or result.get("effective_approval") is not False
                or result.get("publish_authorized") is not False
                or result.get("ready_transitions_performed") is not False):
            raise ConsoleBlocked("unexpected_authorization_state", 503)
        return self._result_page(
            "レビュー記録のみ保存しました。投稿許可はありません。", account=key[0],
        )

    def _revoke(
        self, *, db: sqlite3.Connection, verifier: PinnedRS256SessionVerifier,
        token: str, key: tuple[str, str, str],
        form: dict[str, str], now: datetime,
    ) -> ConsoleResult:
        if (form["confirm"] != "yes" or form["reason_code"] not in REVOKE_REASONS
                or not OP_RE.fullmatch(form["operation_id"])):
            raise ConsoleBlocked("revocation_confirmation_invalid", 400)
        head = _ledger(db, key)
        version = form["expected_ledger_version"]
        if (not SAFE_VERSION.fullmatch(version) or int(version) != head["version"]
                or form["expected_ledger_head_sha256"] != head["hash"]
                or head["state"] != "REVIEW_RECORDED_ONLY"):
            raise ConsoleBlocked("review_stale", 409)
        try:
            last = db.execute(
                """SELECT payload_json FROM sns_media_review_events
                   WHERE account_id=? AND slot_id=? AND queue_id=?
                     AND sequence=?""", (*key, head["version"]),
            ).fetchone()
            if last is None:
                raise ValueError()
            data = json.loads(last[0])
            request = ReviewRequest(
                account_id=key[0], slot_id=key[1], queue_id=key[2],
                expected_queue_revision=data["queue_revision"],
                expected_plan_sha256=data["source_plan_sha256"],
                expected_receipts_head_sha256=data["receipts_head_sha256"],
                draft_event_sha256=data["draft_event_sha256"],
                confirm_human_review=True,
            )
            result = revoke_review(
                db, request, "Bearer " + token,
                verifier=verifier, trusted_issuer=self.trusted_issuer,
                operation_id=form["operation_id"],
                expected_ledger_version=int(version),
                reason_code=form["reason_code"],
                queue_authority=ReviewQueueReconciliation(db), as_of=now,
            )
        except Exception:
            raise ConsoleBlocked("revocation_conflict_or_unavailable", 409) from None
        if (result.get("status") != "ISOLATED_REVIEW_LEDGER_RECORDED_NOT_AUTHORIZED"
                or result.get("effective_approval") is not False
                or result.get("ready_transitions_performed") is not False
                or result.get("publish_authorized") is not False):
            raise ConsoleBlocked("unexpected_authorization_state", 503)
        return self._result_page(
            "レビュー記録を取り消しました。投稿は引き続き禁止です。", account=key[0],
        )

    def _candidate_text(
        self, *, canonical: CanonicalProtectedReviewReader,
        key: tuple[str, str, str],
    ) -> ConsoleResult:
        """Only deliver exact bound draft text after authenticated CSRF POST.

        Text/plain prevents rendering arbitrary HTML as active content.
        No source URL, proof bytes, token, API credential or extra queue fields.
        """
        try:
            context = canonical.load_current(*key)
            _candidate_request(context, key)
            body = context.queue.get("public_post_text")
            if (not isinstance(body, str) or not body.strip()
                    or len(body.encode("utf-8")) > 16000):
                raise ValueError()
            return ConsoleResult(200, body.encode("utf-8"), "text/plain; charset=utf-8")
        except Exception:
            raise ConsoleBlocked("candidate_text_unavailable", 409) from None

    def _original(
        self, *, db: sqlite3.Connection, canonical: CanonicalProtectedReviewReader,
        verifier: PinnedRS256SessionVerifier, token: str,
        key: tuple[str, str, str], form: dict[str, str], now: datetime,
    ) -> ConsoleResult:
        eid = form["evidence_id"]
        try:
            context = canonical.load_current(*key)
            request = _candidate_request(context, key)
            proof = context.evidence_by_id.get(eid)
            if (proof is None or proof.get("evidence_id") != eid
                    or proof.get("account_id") != key[0]
                    or proof.get("slot_id") != key[1]
                    or proof.get("queue_id") != key[2]
                    or proof.get("media_asset_id") != context.queue.get("media_asset_id")
                    or proof.get("source_id") != context.queue.get("source_id")
                    or proof.get("usage_scope") != "THREADS_ORGANIC_ONLY"):
                raise ValueError()
            matching = [
                e for e in context.receipts["events"]
                if (e.get("account_id"), e.get("slot_id"), e.get("queue_id")) == key
            ]
            if (not matching or eid not in matching[-1].get("evidence_ids", {}).values()
                    or request.expected_queue_revision != context.queue.get("revision")):
                raise ValueError()
            content = ProtectedEvidenceVault(db).read_original_scoped(
                evidence_id=eid, account_id=key[0], slot_id=key[1],
                queue_id=key[2], bearer_token="Bearer " + token,
                verifier=verifier, trusted_issuer=self.trusted_issuer, as_of=now,
            )
        except Exception:
            raise ConsoleBlocked("original_unavailable", 409) from None
        return ConsoleResult(
            200, content, "application/octet-stream",
            (("Content-Disposition",
              f'attachment; filename="review-proof-{eid}.bin"'),),
        )

    @staticmethod
    def _result_page(message: str, account: str | None = None) -> ConsoleResult:
        back_link = (
            '<p><a href="/review?account=' + _escape(account) +
            '">レビュー画面へ戻る</a></p>'
            if account in {item[0] for item in MEDIA_SLOTS}
            else ''
        )
        body = (
            '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
            '<title>レビュー結果</title></head><body><main><h1>処理結果</h1><p>'
            + _escape(message) + '</p><p>正式承認・READY変更・投稿権限はすべて無効です。</p>'
            + back_link + '</main></body></html>'
        )
        return ConsoleResult(200, body.encode("utf-8"))

    def _handle(self, env: dict[str, Any]) -> ConsoleResult:
        if env.get("wsgi.url_scheme") != "https" or env.get("HTTP_HOST") != self.host:
            raise ConsoleBlocked("trusted_origin_required", 421)
        route = env.get("PATH_INFO", "")
        method = env.get("REQUEST_METHOD", "")
        if method == "GET" and route == "/review/style.css":
            return ConsoleResult(200, CSS, "text/css; charset=utf-8")
        if (method, route) not in {
            ("GET", "/review"), ("POST", "/review/record"),
            ("POST", "/review/revoke"), ("POST", "/review/original"),
            ("POST", "/review/candidate"),
        }:
            raise ConsoleBlocked("route_not_found", 404)
        token = _cookie(env)
        now = self._clock()
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise ConsoleBlocked("clock_unavailable", 503)
        if method == "GET":
            query = _exact_values(env.get("QUERY_STRING", ""), GET_FIELDS)
            account = query["account"]
            form: dict[str, str] = {}
        else:
            if env.get("HTTP_ORIGIN") != self.origin:
                raise ConsoleBlocked("origin_mismatch", 403)
            if env.get("HTTP_SEC_FETCH_SITE", "same-origin") not in ("same-origin", "none"):
                raise ConsoleBlocked("cross_site_request", 403)
            content_type = env.get("CONTENT_TYPE", "").lower()
            if content_type not in ("application/x-www-form-urlencoded",
                                    "application/x-www-form-urlencoded; charset=utf-8"):
                raise ConsoleBlocked("form_content_type_invalid", 400)
            length = env.get("CONTENT_LENGTH", "")
            if not isinstance(length, str) or not length.isascii() or not length.isdecimal():
                raise ConsoleBlocked("content_length_invalid", 400)
            if int(length) > MAX_FORM_BYTES:
                raise ConsoleBlocked("form_too_large", 413)
            stream = env.get("wsgi.input")
            if stream is None or not hasattr(stream, "read"):
                raise ConsoleBlocked("form_stream_missing", 400)
            raw = stream.read(int(length))
            if not isinstance(raw, bytes) or len(raw) != int(length):
                raise ConsoleBlocked("form_content_invalid", 400)
            try:
                body = raw.decode("utf-8", errors="strict")
            except UnicodeDecodeError:
                raise ConsoleBlocked("form_content_invalid", 400) from None
            action = route.rsplit("/", 1)[-1]
            expected = {
                "record": POST_RECORD, "revoke": POST_REVOKE,
                "original": POST_ORIGINAL, "candidate": POST_CANDIDATE,
            }[action]
            form = _exact_values(body, expected)
            account = form["account_id"]
        db: sqlite3.Connection | None = None
        try:
            db = self._db_factory()
            if (not isinstance(db, sqlite3.Connection) or db.in_transaction
                    or db.execute("PRAGMA foreign_keys").fetchone()[0] != 1):
                raise ConsoleBlocked("review_database_not_ready", 503)
            verifier = self._verifier_factory(db)
            canonical = self._canonical_factory(db)
            if (not isinstance(verifier, PinnedRS256SessionVerifier)
                    or not isinstance(canonical, CanonicalProtectedReviewReader)
                    or verifier._sessions.connection is not db
                    or canonical.vault.connection is not db):
                raise ConsoleBlocked("trusted_adapters_not_configured", 503)
            self._authenticate(verifier, token, account, now)
            if method == "GET":
                return self._page(
                    db=db, canonical=canonical, verifier=verifier,
                    token=token, account=account, now=now,
                )
            key = _key(form["account_id"], form["slot_id"], form["queue_id"])
            if not hmac.compare_digest(
                form["csrf"], self._csrf(token, action, key),
            ):
                raise ConsoleBlocked("csrf_invalid", 403)
            if action != "revoke" and key not in self._inbox_keys(db, account):
                raise ConsoleBlocked("candidate_not_in_inbox", 403)
            if action == "record":
                return self._record(
                    db=db, verifier=verifier, canonical=canonical,
                    token=token, key=key, form=form, now=now,
                )
            if action == "revoke":
                return self._revoke(
                    db=db, verifier=verifier, token=token,
                    key=key, form=form, now=now,
                )
            if action == "candidate":
                return self._candidate_text(canonical=canonical, key=key)
            return self._original(
                db=db, verifier=verifier, canonical=canonical,
                token=token, key=key, form=form, now=now,
            )
        finally:
            if isinstance(db, sqlite3.Connection):
                db.close()

    def __call__(
        self, environ: dict[str, Any],
        start_response: Callable[..., Any],
    ) -> list[bytes]:
        try:
            result = self._handle(environ)
        except ConsoleBlocked as exc:
            messages = {
                400: "送信内容を確認してください。",
                401: "認証されたセッションが必要です。",
                403: "操作権限またはリクエストの検証に失敗しました。",
                404: "画面が見つかりません。",
                409: "情報が更新されたか、証跡が不足しています。画面を再読み込みしてください。",
                413: "フォームが大きすぎます。",
                421: "許可されたHTTPS経由で接続してください。",
                503: "レビューサービスの準備ができていません。",
            }
            result = ConsoleResult(
                exc.status, self._result_page(messages.get(exc.status, messages[503])).data,
            )
        except Exception:
            result = ConsoleResult(
                503, self._result_page("レビューサービスを利用できません。").data,
            )
        headers = (
            ("Content-Type", result.content_type),
            ("Content-Length", str(len(result.data))),
            *SECURITY_HEADERS,
            *result.headers,
        )
        start_response(RESPONSES[result.status], list(headers))
        return [result.data]
