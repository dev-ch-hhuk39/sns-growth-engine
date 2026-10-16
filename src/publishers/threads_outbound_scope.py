"""Fail-closed Threads HTTP send scope backed by an existing SQLite CLAIM.

This is a defense against accidental alternate senders in a cooperating
single-host codebase, not a distributed authority or an external process ACL.
No bearer tokens, captions, URLs or HMAC keys are stored in process globals.
"""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator


_DENIED = "P0_ONCE_OUTBOUND_SCOPE_REQUIRED"


@dataclass
class _Scope:
    account_id: str
    queue_id: str
    content_hash: str
    stage: str = "NEW"
    user_id: str = ""
    ledger: object = None
    receipt_mac: str = ""
    source_sha256: str = ""
    source_text: str = ""


_ACTIVE: ContextVar[_Scope | None] = ContextVar("threads_p0_once_scope", default=None)


@contextmanager
def claimed_text_delivery(
    *, ledger: object, receipt: dict,
    account_id: str, queue_id: str, text: str, source_sha256: str,
) -> Iterator[None]:
    """Bind a previously durable one-use CLAIM to one HTTP creation/publish.

    Caller owns Sheets persistence and ACK/verification after this scope ends.
    Network exceptions do not release the claim or permit a second attempt.
    """
    # Duck-typed fakes must never grant a production HTTP send.
    from p0_real_delivery_once import P0OnceGuard
    if (type(ledger) is not P0OnceGuard
            or _ACTIVE.get() is not None
            or not isinstance(receipt, dict)):
        raise PermissionError(_DENIED)
    event_mac = receipt.get("event_mac")
    if (receipt.get("status") != "CLAIMED_UNCERTAIN"
            or type(event_mac) is not str
            or type(account_id) is not str or type(queue_id) is not str
            or type(text) is not str or not text
            or type(source_sha256) is not str):
        raise PermissionError(_DENIED)
    # The ledger independently checks HMAC event integrity, account, source,
    # state and revision; no env flag or caller-provided string authorizes it.
    ledger.validate_claim_receipt(
        account_id=account_id, queue_id=queue_id,
        source_sha256=source_sha256, event_mac=event_mac, text=text,
    )
    scope = _Scope(account_id, queue_id, hashlib.sha256(text.encode()).hexdigest(),
                   ledger=ledger, receipt_mac=event_mac,
                   source_sha256=source_sha256, source_text=text)
    reset = _ACTIVE.set(scope)
    try:
        yield
    finally:
        scope.stage = "CLOSED"
        _ACTIVE.reset(reset)


def before_container_create(*, account_id: str, queue_id: str,
                            user_id: str, text: str) -> None:
    """Consume the one permitted container creation before HTTP is attempted."""
    scope = _ACTIVE.get()
    if (scope is None or scope.stage != "NEW"
            or not user_id or not text
            or scope.account_id != account_id or scope.queue_id != queue_id
            or scope.content_hash != hashlib.sha256(text.encode()).hexdigest()):
        raise PermissionError(_DENIED)
    scope.stage = "CREATE_ATTEMPTED"
    # The ledger INSERT is committed and checked before the first HTTP request.
    # A lost response or crashed process can never reuse this receipt.
    scope.ledger.consume_send_receipt(
        account_id=account_id, queue_id=queue_id,
        text=text, source_sha256=scope.source_sha256,
        event_mac=scope.receipt_mac,
    )
    scope.user_id = user_id


def before_container_publish(*, account_id: str, queue_id: str,
                             user_id: str) -> None:
    """Consume the one publish attempt after a creation attempt."""
    scope = _ACTIVE.get()
    if (scope is None or scope.stage != "CREATE_ATTEMPTED"
            or scope.account_id != account_id or scope.queue_id != queue_id
            or scope.user_id != user_id):
        raise PermissionError(_DENIED)
    scope.stage = "PUBLISH_ATTEMPTED"
