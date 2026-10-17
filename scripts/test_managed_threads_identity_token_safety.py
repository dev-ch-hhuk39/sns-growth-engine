#!/usr/bin/env python3
"""No-network checks: Threads identity credentials never appear in URL/redirect."""
from __future__ import annotations

import io
import os
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from preflight_managed_threads_account import (
    _NoIdentityRedirects, _verify_live_identity,
)

ACCOUNT = "night_scout"
TOKEN = "SYNTHETIC_TOKEN_SHOULD_NEVER_APPEAR_IN_A_URL"
CREDS = {"access_token": TOKEN, "user_id": "123456"}
ENV = {"THREADS_HANDLE_NIGHT_SCOUT": "the_expected_handle"}


class FakeResponse:
    def __init__(self, payload: bytes):
        self.data = io.BytesIO(payload)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.data.close()

    def read(self, limit=-1):
        return self.data.read(limit)


class FakeOpener:
    def __init__(self, response: bytes | Exception, seen: list):
        self.response = response
        self.seen = seen

    def open(self, request, timeout):
        self.seen.append(request)
        assert timeout == 20
        if isinstance(self.response, Exception):
            raise self.response
        return FakeResponse(self.response)


class IdentitySecurityTests(unittest.TestCase):
    def test_exact_identity_and_no_query_token(self):
        requests_seen: list = []
        opener = FakeOpener(b'{"id":"123456","username":"the_expected_handle"}', requests_seen)
        with patch.dict(os.environ, ENV), patch(
            "preflight_managed_threads_account.urllib.request.build_opener",
            return_value=opener,
        ) as factory:
            result = _verify_live_identity(ACCOUNT, CREDS)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(len(requests_seen), 1)
        req = requests_seen[0]
        self.assertEqual(req.full_url, "https://graph.threads.net/v1.0/me?fields=id%2Cusername")
        self.assertNotIn(TOKEN, req.full_url)
        self.assertEqual(req.get_header("Authorization"), f"Bearer {TOKEN}")
        self.assertIsInstance(factory.call_args.args[0], _NoIdentityRedirects)
        self.assertTrue(result["resolved_user_id_matches"])
        self.assertTrue(result["resolved_handle_matches"])

    def test_redirect_is_rejected_without_new_request(self):
        requests_seen: list = []
        opener = FakeOpener(
            urllib.error.HTTPError(
                "https://graph.threads.net/v1.0/me", 302, "redirect blocked",
                {"Location": "https://example.org/steal"}, None,
            ),
            requests_seen,
        )
        with patch.dict(os.environ, ENV), patch(
            "preflight_managed_threads_account.urllib.request.build_opener",
            return_value=opener,
        ):
            result = _verify_live_identity(ACCOUNT, CREDS)
        self.assertEqual(result["status"], "CREDENTIAL_BLOCKED")
        self.assertEqual(result["reason"], "HTTPError")
        self.assertNotIn(TOKEN, str(result))
        self.assertEqual(len(requests_seen), 1)
        no_redirect = _NoIdentityRedirects()
        req = requests_seen[0]
        self.assertIsNone(no_redirect.redirect_request(
            req, None, 302, "redirect", {}, "https://example.org/steal"))

    def test_wrong_user_and_wrong_handle_both_block(self):
        opener = FakeOpener(b'{"id":"987654","username":"other"}', [])
        with patch.dict(os.environ, ENV), patch(
            "preflight_managed_threads_account.urllib.request.build_opener",
            return_value=opener,
        ):
            report = _verify_live_identity(ACCOUNT, CREDS)
        self.assertEqual(report["status"], "ACCOUNT_IDENTITY_BLOCKED")
        self.assertIn("threads_user_id_mismatch", report["reason"])
        self.assertIn("threads_handle_mismatch", report["reason"])

    def test_missing_expected_handle_fails_before_network(self):
        with patch.dict(os.environ, {}, clear=True), patch(
            "preflight_managed_threads_account.urllib.request.build_opener",
            side_effect=AssertionError("NETWORK_NOT_ALLOWED"),
        ):
            result = _verify_live_identity(ACCOUNT, CREDS)
        self.assertEqual(result["status"], "CREDENTIAL_BLOCKED")
        self.assertFalse(result["secret_values_exposed"])

    def test_provider_error_is_redacted(self):
        with patch.dict(os.environ, ENV), patch(
            "preflight_managed_threads_account.urllib.request.build_opener",
            return_value=FakeOpener(ValueError(TOKEN), []),
        ):
            report = _verify_live_identity(ACCOUNT, CREDS)
        self.assertEqual(report["status"], "CREDENTIAL_BLOCKED")
        self.assertEqual(report["reason"], "ValueError")
        self.assertNotIn(TOKEN, str(report))


if __name__ == "__main__":
    unittest.main()
