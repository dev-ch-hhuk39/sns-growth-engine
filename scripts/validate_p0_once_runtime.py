#!/usr/bin/env python3
"""Read-only, redacted P0 one-use runtime preflight before production Sheets I/O.

Checks all SQLite head/event HMAC chains and irreversible send-attempt records.
Never initializes/migrates a database, reads Google/SNS, writes or publishes.
Passing is not a production release or evidence of sole-writer custody.
"""
from __future__ import annotations

import argparse
import hmac
import json
import os
import sys
from typing import Any

from p0_real_delivery_once import (
    ACCOUNTS, DB_SCHEMA, P0OnceBlocked, P0OnceGuard, _audit, _db,
    _mac, _verify_schema,
)

SEND_KEYS = frozenset({
    "schema", "queue_id", "account_id", "source_sha256",
    "claim_event_mac", "operation_id", "started_at",
})


def inspect(ledger: P0OnceGuard, *, account_id: str) -> dict[str, Any]:
    if type(ledger) is not P0OnceGuard or account_id not in ACCOUNTS:
        raise P0OnceBlocked("P0_ONCE_RUNTIME_SCOPE_INVALID")
    with _db(ledger.db_path, allow_test_path=ledger.allow_test_path) as db:
        _verify_schema(db)
        heads = {
            row["queue_id"]: dict(row)
            for row in db.execute("SELECT * FROM sns_p0_once_heads")
        }
        if len(heads) != db.execute(
            "SELECT COUNT(*) FROM sns_p0_once_heads"
        ).fetchone()[0]:
            raise P0OnceBlocked("P0_ONCE_RUNTIME_DUPLICATE_HEAD")
        for queue_id, head in heads.items():
            _audit(db, queue_id, head, ledger.secret_key)
        # An event without a head must not be silently ignored by the loop.
        orphan_events = db.execute(
            "SELECT COUNT(*) FROM sns_p0_once_events e "
            "LEFT JOIN sns_p0_once_heads h ON e.queue_id=h.queue_id "
            "WHERE h.queue_id IS NULL"
        ).fetchone()[0]
        if orphan_events:
            raise P0OnceBlocked("P0_ONCE_RUNTIME_ORPHAN_EVENT")
        attempts = 0
        for row in db.execute("SELECT * FROM sns_p0_once_send_attempts"):
            attempts += 1
            queue_id = row["queue_id"]
            head = heads.get(queue_id)
            if head is None:
                raise P0OnceBlocked("P0_ONCE_RUNTIME_ORPHAN_SEND")
            try:
                payload = json.loads(row["payload_json"])
            except (TypeError, ValueError):
                raise P0OnceBlocked("P0_ONCE_RUNTIME_SEND_JOURNAL_INVALID") from None
            claim = db.execute(
                "SELECT event_mac,action FROM sns_p0_once_events "
                "WHERE queue_id=? AND revision=1", (queue_id,),
            ).fetchone()
            valid = (
                isinstance(payload, dict) and frozenset(payload) == SEND_KEYS
                and payload["schema"] == DB_SCHEMA
                and payload["queue_id"] == queue_id
                and payload["account_id"] == head["account_id"] == row["account_id"]
                and payload["source_sha256"] == head["source_sha256"] == row["source_sha256"]
                and payload["claim_event_mac"] == row["claim_event_mac"]
                and claim is not None and claim["action"] == "CLAIM"
                and claim["event_mac"] == row["claim_event_mac"]
                and isinstance(payload["started_at"], str) and bool(payload["started_at"])
                and isinstance(payload["operation_id"], str)
                and payload["operation_id"].startswith("p0_send_")
                and len(payload["operation_id"]) == len("p0_send_") + 32
                and hmac.compare_digest(row["send_mac"], _mac(ledger.secret_key, payload))
            )
            if not valid:
                raise P0OnceBlocked("P0_ONCE_RUNTIME_SEND_JOURNAL_INVALID")
        return {
            "status": "PASS",
            "scope": "night_liver_threads_text_only",
            "account_id": account_id,
            "verified_claims": len(heads),
            "verified_send_attempts": attempts,
            "would_write": False,
            "would_post": False,
        }


def preflight(*, account_id: str) -> dict[str, Any]:
    if account_id not in ACCOUNTS:
        raise P0OnceBlocked("P0_ONCE_RUNTIME_SCOPE_INVALID")
    if os.environ.get("SNS_P0_ONCE_GATE_ENABLED") != "true":
        raise P0OnceBlocked("P0_ONCE_RUNTIME_GATE_DISABLED")
    ledger = P0OnceGuard.from_env()
    return inspect(ledger, account_id=account_id)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", required=True)
    args = parser.parse_args()
    try:
        report = preflight(account_id=args.account_id)
    except P0OnceBlocked as err:
        # Fixed reason codes only. Never print DB path, private HMAC key,
        # source text, exception messages or account credentials.
        print(json.dumps({"status": "BLOCKED", "reason": str(err)}, sort_keys=True))
        return 2
    except Exception:
        print(json.dumps({"status": "BLOCKED",
                          "reason": "P0_ONCE_RUNTIME_PREFLIGHT_UNVERIFIED"}, sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
