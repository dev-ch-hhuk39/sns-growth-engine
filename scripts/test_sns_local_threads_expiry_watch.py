#!/usr/bin/env python3
"""Fake-provider tests of the read-only three-account expiry watchdog."""
from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

import sns_local_threads_expiry_watch as audit  # noqa: E402


class FakeResponse:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self, count):
        return json.dumps(self.payload).encode()


class ExpiryWatchTests(unittest.TestCase):
    def test_fixed_endpoint_and_no_secret_output(self):
        now = datetime(2026, 10, 25, tzinfo=timezone.utc)
        captured = []
        class Opener:
            def open(self, req, timeout):
                captured.append(req)
                return FakeResponse({"data": {
                    "is_valid": True, "user_id": "123456",
                    "scopes": ["threads_basic"],
                    "expires_at": int(now.timestamp()) + 20 * 86400,
                }})
        with patch.object(audit.urllib.request, "build_opener", return_value=Opener()):
            r = audit.check_one(
                "night_scout",
                {"access_token": "PRIVATE_NOT_REAL", "user_id": "123456"}, clock=now,
            )
        self.assertEqual(r["state"], "CURRENT")
        self.assertEqual(r["expires_in_days"], 20.0)
        parsed = urlsplit(captured[0].full_url)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "graph.threads.net")
        self.assertEqual(parsed.path, "/debug_token")
        self.assertEqual(parse_qs(parsed.query), {"input_token": ["PRIVATE_NOT_REAL"]})
        self.assertEqual(captured[0].get_header("Authorization"), "Bearer PRIVATE_NOT_REAL")
        self.assertNotIn("PRIVATE_NOT_REAL", json.dumps(r))

    def test_warning_at_fourteen_days(self):
        now = datetime(2026, 10, 25, tzinfo=timezone.utc)
        class Opener:
            def open(self, req, timeout):
                return FakeResponse({"data": {
                    "is_valid": True, "user_id": "id1",
                    "scopes": ["threads_basic"],
                    "expires_at": int(now.timestamp()) + 13 * 86400,
                }})
        with patch.object(audit.urllib.request, "build_opener", return_value=Opener()):
            r = audit.check_one(
                "liver_manager",
                {"access_token": "not-a-token", "user_id": "id1"}, clock=now)
        self.assertEqual(r["state"], "RENEWAL_REQUIRED")

    def test_invalid_identity_is_not_accepted(self):
        now = datetime(2026, 10, 25, tzinfo=timezone.utc)
        class Opener:
            def open(self, req, timeout):
                return FakeResponse({"data": {
                    "is_valid": True, "user_id": "wrong_id",
                    "scopes": ["threads_basic"],
                    "expires_at": int(now.timestamp()) + 30 * 86400,
                }})
        with patch.object(audit.urllib.request, "build_opener", return_value=Opener()):
            with self.assertRaises(ValueError):
                audit.check_one(
                    "beauty_account",
                    {"access_token": "not-a-token", "user_id": "expected"}, clock=now)

    def test_lifecycle_requires_live_issue_time_app_and_future_expiry(self):
        now = datetime(2026, 10, 26, tzinfo=timezone.utc)
        valid = {"is_valid": True, "user_id": "id1", "app_id": "app1",
                 "scopes": ["threads_basic"], "issued_at": int(now.timestamp())-86401,
                 "expires_at": int(now.timestamp())+20*86400}
        credentials = {"access_token": "SYNTHETIC", "user_id": "id1", "app_id": "app1"}
        class Opener:
            def __init__(self, data): self.data = data
            def open(self, req, timeout): return FakeResponse({"data": self.data})
        cases = [dict(valid, issued_at=None), dict(valid, issued_at=True),
                 dict(valid, issued_at=int(now.timestamp())+300),
                 dict(valid, app_id="wrong"), dict(valid, expires_at=int(now.timestamp())-1)]
        for data in cases:
            with self.subTest(data=data), patch.object(audit.urllib.request, "build_opener", return_value=Opener(data)):
                with self.assertRaises(ValueError):
                    audit.check_one("liver_manager", credentials, clock=now, include_lifecycle=True)
        with patch.object(audit.urllib.request, "build_opener", return_value=Opener(valid)):
            result = audit.check_one("liver_manager", credentials, clock=now, include_lifecycle=True)
        self.assertEqual(result["issued_at"], valid["issued_at"])
        self.assertEqual(result["expires_at"], valid["expires_at"])
        self.assertNotIn("SYNTHETIC", json.dumps(result))

    def test_redirect_denied(self):
        with self.assertRaises(ValueError):
            audit.NoRedirect().redirect_request(None, None, 302, "Found", {}, "https://unknown.invalid/")


if __name__ == "__main__":
    unittest.main()
