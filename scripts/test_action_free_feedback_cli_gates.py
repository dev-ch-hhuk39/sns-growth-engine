#!/usr/bin/env python3
"""Action-free feedback CLI safety: authorization before Sheets I/O.

Offline tests use fake Sheets clients and synthetic rows only.
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import maintain_text_ready_inventory as ready  # noqa: E402
import run_growth_attribution_cycle as attribution  # noqa: E402


def call_main(module, *args: str):
    buffer = io.StringIO()
    with patch.object(module.sys, "argv", ["program", *args]), redirect_stdout(buffer):
        code = module.main()
    return code, json.loads(buffer.getvalue())


class IndependentFeedbackCliTests(unittest.TestCase):
    def test_attribution_rejects_unconfirmed_live_writes_before_credentials(self):
        with patch("config_loader.get_config", side_effect=AssertionError(
            "no Google configuration can be read before approval",
        )) as cfg:
            code, result = call_main(
                attribution, "--apply", "--use-sheets",
                "--account-id", "night_scout",
            )
        self.assertEqual(code, 1)
        self.assertEqual(result["reason"], "apply_requires_confirm_attribution")
        self.assertFalse(result["would_write"])
        cfg.assert_not_called()

    def test_attribution_rejects_all_accounts_before_credentials(self):
        with patch("config_loader.get_config", side_effect=AssertionError(
            "Google configuration must not be read",
        )) as cfg:
            code, result = call_main(
                attribution, "--apply", "--confirm-attribution",
                "--use-sheets", "--account-id", "all",
            )
        self.assertEqual(code, 1)
        self.assertEqual(result["reason"], "apply_requires_one_account")
        cfg.assert_not_called()

    def test_attribution_rejects_conflicting_apply_preview_modes(self):
        with patch("config_loader.get_config", side_effect=AssertionError):
            code, result = call_main(
                attribution, "--apply", "--dry-run",
                "--confirm-attribution", "--use-sheets",
                "--account-id", "liver_manager",
            )
        self.assertEqual(code, 1)
        self.assertEqual(result["reason"], "dry_run_and_apply_are_mutually_exclusive")

    def test_attribution_rejects_offline_input_as_live_write_source(self):
        for argv in (
            ("--input-json", "/tmp/missing-synthetic-input", "--apply",
             "--confirm-attribution", "--account-id", "night_scout"),
            ("--input-json", "/tmp/missing-synthetic-input", "--use-sheets",
             "--account-id", "night_scout"),
        ):
            with self.subTest(argv=argv), patch(
                "config_loader.get_config",
                side_effect=AssertionError("must not use Google credentials"),
            ) as cfg:
                code, result = call_main(attribution, *argv)
                self.assertEqual(code, 1)
                self.assertEqual(result["status"], "BLOCKED")
                cfg.assert_not_called()

    def test_offline_measured_attribution_without_provider_client(self):
        with tempfile.TemporaryDirectory(prefix="sns-metrics-feedback-") as directory:
            fixture = Path(directory) / "read-only-evidence.json"
            fixture.write_text(
                json.dumps({"posted_results": [], "metric_snapshots": []}),
                encoding="utf-8",
            )
            with patch("config_loader.get_config", side_effect=AssertionError(
                "offline analysis must not read Google credentials",
            )) as cfg:
                code, payload = call_main(
                    attribution, "--input-json", str(fixture),
                    "--account-id", "night_scout", "--dry-run",
                )
            self.assertEqual(code, 0)
            self.assertEqual(payload["status"], "PLAN_ONLY")
            self.assertFalse(payload["would_write"])
            self.assertFalse(payload["would_post"])
            cfg.assert_not_called()

    def test_attribution_live_readonly_preview_uses_dry_run_client(self):
        created = []
        class FakeSheetsClient:
            def __init__(self, *args, **kwargs):
                created.append(kwargs)
        fake_sheets = types.SimpleNamespace(SheetsClient=FakeSheetsClient)
        with patch.dict(sys.modules, {"sheets_client": fake_sheets}), patch(
            "config_loader.get_config",
            return_value={"sheet_id": "test-reporting", "sa_dict": {}},
        ), patch.object(attribution, "_read_tab", return_value=([], "")):
            code, payload = call_main(
                attribution, "--account-id", "night_scout",
                "--use-sheets", "--dry-run",
            )
        self.assertEqual(code, 0)
        self.assertEqual(payload["status"], "PLAN_ONLY")
        self.assertFalse(payload["would_write"])
        self.assertEqual(created, [{"dry_run": True}])

    def test_ready_bulk_apply_denied_before_google_config(self):
        with patch.object(ready, "get_config", side_effect=AssertionError(
            "no credentials before rejecting all-account write",
        )) as cfg:
            code, payload = call_main(
                ready, "--apply", "--confirm-ready-maintenance",
                "--use-sheets", "--account-id", "all",
            )
        self.assertEqual(code, 1)
        self.assertEqual(payload["reason"], "apply_requires_one_account")
        cfg.assert_not_called()

    def test_ready_horizon_invalid_before_google_config(self):
        for value in ("0", "-2", "169"):
            with self.subTest(value=value), patch.object(
                ready, "get_config", side_effect=AssertionError(
                    "no credentials on malformed horizon",
                ),
            ) as cfg:
                code, payload = call_main(
                    ready, "--dry-run", "--use-sheets",
                    "--account-id", "night_scout", "--horizon-hours", value,
                )
                self.assertEqual(code, 1)
                self.assertEqual(
                    payload["reason"], "inventory_horizon_must_be_1_to_168_hours",
                )
                cfg.assert_not_called()

    def test_ready_readonly_uses_nonmutating_client_and_never_generates(self):
        created = []
        class FakeClient:
            def __init__(self, *args, **kwargs):
                created.append(kwargs)
        slot = {
            "slot_id": "ns_1400_reference",
            "post_type": "reference_text",
            "business_date_jst": "2026-10-13",
        }
        with patch.object(ready, "SheetsClient", FakeClient), patch.object(
            ready, "get_config", return_value={
                "sheet_id": "test-reporting", "sa_dict": {},
            },
        ), patch.object(ready, "read_records_safely", return_value=[]), patch.object(
            ready, "_required_text_slots", return_value=[slot],
        ), patch.object(
            ready, "replenish", return_value={"status": "PLAN_ONLY"},
        ) as generate:
            code, payload = call_main(
                ready, "--account-id", "night_scout",
                "--dry-run", "--use-sheets",
            )
        # An empty synthetic queue accurately fails coverage; it does not
        # trigger generation, READY promotion, or any provider mutation.
        self.assertEqual(code, 1)
        self.assertEqual(payload["status"], "FAILED")
        self.assertFalse(payload["would_post"])
        self.assertEqual(created, [{"dry_run": True}])
        self.assertTrue(generate.called)
        self.assertTrue(all(
            call.kwargs.get("apply") is False for call in generate.call_args_list
        ))

    def test_ready_apply_without_explicit_confirmation_denied_before_io(self):
        with patch.object(ready, "get_config", side_effect=AssertionError):
            code, payload = call_main(
                ready, "--account-id", "liver_manager",
                "--apply", "--use-sheets",
            )
        self.assertEqual(code, 1)
        self.assertEqual(payload["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
