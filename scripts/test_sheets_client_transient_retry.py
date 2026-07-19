#!/usr/bin/env python3
"""SheetsClient retries bounded transient failures without logging payloads."""
from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sheets_client import SheetsClient, _sheets_retry_reason


class _Response:
    def __init__(self, status_code: int):
        self.status_code = status_code


class _SheetsError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.response = _Response(status_code)


def main() -> int:
    checks: list[tuple[str, bool]] = []
    client = object.__new__(SheetsClient)

    attempts = 0

    def transient_then_ok():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise _SheetsError(500, "internal error secret-payload-must-not-log")
        return "ok"

    output = io.StringIO()
    with patch("sheets_client.time.sleep"), redirect_stdout(output):
        result = client._call_with_rate_limit_retry("read:test", transient_then_ok)
    checks.append(("HTTP 500 is retried", result == "ok" and attempts == 2))
    checks.append(("error payload is suppressed", "secret-payload-must-not-log" not in output.getvalue()))

    open_attempts = 0

    class _GC:
        def open_by_key(self, _sheet_id):
            nonlocal open_attempts
            open_attempts += 1
            if open_attempts == 1:
                raise _SheetsError(503, "service unavailable private-body")
            return "sheet"

    client._gc = _GC()
    output = io.StringIO()
    with patch("sheets_client.time.sleep"), redirect_stdout(output):
        opened = client._open_with_rate_limit_retry("sheet-id")
    checks.append(("open_by_key HTTP 503 is retried", opened == "sheet" and open_attempts == 2))
    checks.append(("open error payload is suppressed", "private-body" not in output.getvalue()))

    non_transient_attempts = 0

    def bad_request():
        nonlocal non_transient_attempts
        non_transient_attempts += 1
        raise _SheetsError(400, "bad request")

    raised = False
    with patch("sheets_client.time.sleep") as sleep_mock:
        try:
            client._call_with_rate_limit_retry("read:bad", bad_request)
        except _SheetsError:
            raised = True
    checks.append(("HTTP 400 is not retried", raised and non_transient_attempts == 1 and not sleep_mock.called))
    checks.append(("quota classifier remains retryable", _sheets_retry_reason(Exception("429 quota exceeded")) == "rate_limit"))

    payloads: list[list[dict]] = []

    class _MutatingWorksheet:
        def batch_update(self, ranges, **_kwargs):
            payloads.append([dict(item) for item in ranges])
            ranges[0]["range"] = f"'Sheet'!{ranges[0]['range']}"
            if len(payloads) == 1:
                raise _SheetsError(429, "quota")
            return {"ok": True}

    with patch("sheets_client.time.sleep"):
        client._batch_update_fields(
            _MutatingWorksheet(),
            ["status"],
            2,
            {"status": "READY"},
            label="mutation-test",
        )
    checks.append((
        "batch payload is rebuilt before retry",
        len(payloads) == 2 and payloads[0][0]["range"] == "A2" and payloads[1][0]["range"] == "A2",
    ))

    failed = [label for label, ok in checks if not ok]
    for label, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {label}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
