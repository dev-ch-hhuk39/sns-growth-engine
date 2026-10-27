#!/usr/bin/env python3
"""No-network evergreen-bank CLI and paid-provider circuit regression tests.

The bank-only CLI must never report NO_REQUIRED_TEXT_SLOTS, while an actual
shortfall must remain a failure. All tests use synthetic accounts and never
create real Sheets clients, publish posts, or invoke paid providers.
"""
from __future__ import annotations

from contextlib import ExitStack, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]
import maintain_text_ready_inventory as m  # noqa: E402


class EvergreenBankModeContracts(unittest.TestCase):
    def _text_offline_cli(self, initial=0, target=1, *, exhausted=False, slots=1):
        client=Mock()
        out=StringIO()
        state={'filled':False}
        slot={'slot_id':'offline-fixture','business_date_jst':'2026-10-30','post_type':'original_text'}
        commands=[]
        def generate(account, selected, **kwargs):
            selected_commands=m._generation_commands(account,selected,offline_only=kwargs['offline_only'])
            commands.extend(selected_commands)
            state['filled']=not exhausted
            return {'status':'QUALITY_EXHAUSTED' if exhausted else 'READY_REPLENISHED',
                    'failure_category':'OFFLINE_CATALOG_EXHAUSTED' if exhausted else '',
                    'queue_ids':[] if exhausted else ['offline-fixture-q'],'attempts':[]}
        def ready(*_args):
            count=target if state['filled'] else initial
            return [{'queue_id':'validated-fixture-'+str(i)} for i in range(count)]
        argv=['maintain','--account-id','night_scout','--apply','--confirm-ready-maintenance',
              '--use-sheets','--horizon-hours','24','--max-bank-allocations','0','--offline-original-only']
        with ExitStack() as stack:
            for context in (
                patch.object(sys,'argv',argv),patch.object(m,'get_config',return_value={'sheet_id':'fixture','sa_dict':{}}),
                patch.object(m,'SheetsClient',return_value=client),patch.object(m,'read_records_safely',return_value=[]),
                patch.object(m,'prime_readonly_record_cache'),patch.object(m,'policy',return_value={'text_horizon_hours':24,'text_candidates_per_slot':target}),
                patch.object(m,'_required_text_slots',return_value=[{**slot,'slot_id':'offline-'+str(i)} for i in range(slots)]),
                patch.object(m,'_publishable_ready_rows',side_effect=ready),
                patch.object(m,'_primary_generation_commands',side_effect=AssertionError('Paid route must not be planned')),
            ):stack.enter_context(context)
            replenish=stack.enter_context(patch.object(m,'replenish',side_effect=generate))
            with redirect_stdout(out):code=m.main()
        return code,json.loads(out.getvalue()),replenish,commands,client

    def test_text_cli_forces_existing_offline_router_for_delivery_and_reserve(self):
        for initial,target in ((0,1),(1,2)):
            with self.subTest(initial=initial,target=target):
                code,report,replenish,commands,client=self._text_offline_cli(initial,target)
                self.assertEqual(code,0)
                self.assertEqual(report['status'],'PASS')
                self.assertFalse(report['would_post'])
                self.assertEqual(replenish.call_count,1)
                self.assertTrue(replenish.call_args.kwargs['offline_only'])
                self.assertEqual([route for route,_ in commands],['offline_original_bank'])
                self.assertIn('--offline-original',commands[0][1])
                client._ensure_tab.assert_not_called()

    def test_text_catalogue_exhaustion_stays_failed_and_stops_further_generation(self):
        code,report,replenish,commands,client=self._text_offline_cli(exhausted=True,slots=2)
        self.assertEqual(code,1)
        self.assertEqual(report['status'],'FAILED')
        self.assertEqual(len(report['hard_delivery_failures']),2)
        self.assertEqual(replenish.call_count,1)
        self.assertEqual(len(commands),1)
        self.assertFalse(report['would_post'])
        client._ensure_tab.assert_not_called()

    def test_text_offline_profile_requires_confirmed_single_account_non_bank_mode(self):
        for flags in (['--dry-run'],['--apply','--use-sheets'],
                      ['--apply','--confirm-ready-maintenance','--use-sheets','--reuse-only'],
                      ['--apply','--confirm-ready-maintenance','--use-sheets','--evergreen-bank']):
            with self.subTest(flags=flags),patch.object(sys,'argv',['maintain','--account-id','night_scout','--offline-original-only',*flags]), \
                    patch.object(m,'get_config') as cfg,patch.object(m,'SheetsClient') as client,redirect_stdout(StringIO()):
                self.assertEqual(m.main(),1)
            cfg.assert_not_called();client.assert_not_called()

    def test_explicit_offline_bank_flag_preserves_shortfall_and_paid_route_exclusion(self):
        client = Mock()
        output = StringIO()
        argv = ['bank', '--account-id','night_scout','--evergreen-bank','--bank-offline-only',
                '--apply','--confirm-ready-maintenance','--use-sheets']
        with patch.object(sys, 'argv', argv), patch.object(m,'SheetsClient',return_value=client), \
                patch.object(m,'get_config',return_value={'sheet_id':'fixture','sa_dict':{}}), \
                patch.object(m,'replenish_bank',return_value={'account_id':'night_scout',
                    'status':'QUALITY_EXHAUSTED','usable_evergreen':12,'minimum':30}) as bank, redirect_stdout(output):
            self.assertEqual(m.main(), 1)
        bank.assert_called_once_with(client, 'night_scout', apply=True, offline_only=True)
        self.assertEqual(json.loads(output.getvalue())['status'], 'FAILED')
        slot = {'slot_id':'fixture_slot','business_date_jst':'2026-10-30'}
        with patch.object(m,'_primary_generation_commands',side_effect=AssertionError('No paid route')):
            commands = m._generation_commands('night_scout', slot, offline_only=True)
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0][0], 'offline_original_bank')
        self.assertIn('--offline-original', commands[0][1])

    def test_offline_bank_flag_rejects_unconfirmed_or_conflicting_modes_before_client(self):
        cases = [
            ['--bank-offline-only','--dry-run'],
            ['--bank-offline-only','--apply','--use-sheets','--evergreen-bank'],
            ['--bank-offline-only','--bank-reuse-only','--apply','--confirm-ready-maintenance','--use-sheets','--evergreen-bank'],
            ['--bank-offline-only','--apply','--confirm-ready-maintenance','--use-sheets'],
        ]
        for flags in cases:
            with self.subTest(flags=flags), patch.object(sys,'argv',['bank','--account-id','night_scout',*flags]), \
                    patch.object(m,'get_config') as config, patch.object(m,'SheetsClient') as client, redirect_stdout(StringIO()):
                self.assertEqual(m.main(), 1)
            config.assert_not_called()
            client.assert_not_called()

    def test_successful_applied_bank_is_pass_not_no_required_text_slots(self):
        rows = [
            {"account_id": "night_scout", "status": "READY_INVENTORY_OK",
             "usable_evergreen": 12, "minimum": 10, "would_post": False}
        ]
        x = m.evergreen_bank_mode_result(rows, ["night_scout"], apply=True)
        self.assertEqual(x["status"], "PASS")
        self.assertEqual(x["mode"], "EVERGREEN_BANK")
        self.assertEqual(x["bank_failure_reason"], "")
        self.assertNotIn("text_delivery_coverage_72h_percent", x)
        self.assertFalse(x["would_post"])

    def test_actual_bank_shortfall_fails_instead_of_returning_false_pass(self):
        x = m.evergreen_bank_mode_result([
            {"account_id": "night_scout", "status": "QUALITY_EXHAUSTED",
             "usable_evergreen": 2, "minimum": 10}
        ], ["night_scout"], apply=True)
        self.assertEqual(x["status"], "FAILED")
        self.assertEqual(x["bank_failure_reason"], "EVERGREEN_BANK_NOT_READY")
        self.assertEqual(x["evergreen_bank_by_account"]["night_scout"]["usable_evergreen"], 2)

    def test_status_cannot_claim_pass_below_numeric_minimum(self):
        result = [{
            "account_id": "night_scout", "status": "READY_INVENTORY_OK",
            "usable_evergreen": 9, "minimum": 10,
        }]
        self.assertEqual(
            m.evergreen_bank_mode_result(result, ["night_scout"], apply=True)["status"],
            "FAILED",
        )
        for invalid in (None, "10", True):
            result[0]["usable_evergreen"] = invalid
            self.assertEqual(
                m.evergreen_bank_mode_result(result, ["night_scout"], apply=True)["status"],
                "FAILED",
            )

    def test_planning_mode_is_not_claimed_as_applied(self):
        result = [{"account_id": "night_scout", "status": "PLAN_ONLY"}]
        x = m.evergreen_bank_mode_result(result, ["night_scout"], apply=False)
        self.assertEqual(x["status"], "PLAN_ONLY")
        self.assertEqual(m.evergreen_bank_mode_result(result, ["night_scout"], apply=True)["status"], "FAILED")

    def test_missing_duplicate_or_wrong_account_fails_closed(self):
        good = {"account_id": "night_scout", "status": "READY_INVENTORY_OK"}
        for rows, accounts in (
            ([], ["night_scout"]),
            ([good, good], ["night_scout", "liver_manager"]),
            ([good], ["beauty_account"]),
            ([good], ["night_scout", "liver_manager"]),
        ):
            self.assertEqual(
                m.evergreen_bank_mode_result(rows, accounts, apply=True)["status"], "FAILED"
            )

    def test_normal_delivery_zero_required_slots_remains_failure(self):
        self.assertEqual(m._coverage_result(0, 0),
                         ("FAILED", 0.0, "NO_REQUIRED_TEXT_SLOTS"))

    @staticmethod
    def _run_cli(bank_status: str, *, apply: bool, account: str = "night_scout"):
        output = StringIO()
        args = [
            "maintain_text_ready_inventory.py", "--account-id", account,
            "--evergreen-bank", "--apply" if apply else "--dry-run",
        ]
        if apply:
            args += ["--confirm-ready-maintenance", "--use-sheets"]
        def synthetic_bank(client, account_id, *, apply):
            return {
                "status": bank_status, "account_id": account_id,
                "usable_evergreen": 10 if bank_status == "READY_INVENTORY_OK" else 1,
                "minimum": 10, "attempts": [], "would_post": False,
            }
        client = Mock()
        with patch.object(sys, "argv", args), \
             patch.object(m, "replenish_bank", side_effect=synthetic_bank) as called, \
             patch.object(m, "SheetsClient", return_value=client), \
             patch.object(m, "get_config",
                          return_value={"sheet_id": "synthetic", "sa_dict": {}}), \
             patch.object(m, "read_records_safely", return_value=[]), \
             redirect_stdout(output):
            rc = m.main()
        return rc, json.loads(output.getvalue()), called, client

    def test_apply_success_returns_zero_without_invoking_publisher(self):
        rc, doc, bank, client = self._run_cli("READY_INVENTORY_OK", apply=True)
        self.assertEqual(rc, 0)
        self.assertEqual(doc["status"], "PASS")
        self.assertEqual(doc["mode"], "EVERGREEN_BANK")
        bank.assert_called_once()
        self.assertTrue(bank.call_args.kwargs["apply"])
        # Only the real replenisher performs this one-time schema check.
        # A CLI wrapper must not repeat it beforehand.
        client._ensure_tab.assert_not_called()
        self.assertFalse(doc["would_post"])

    def test_bank_only_apply_has_no_redundant_main_sheet_reads(self):
        client = Mock()
        out = StringIO()
        args = ["maintain_text_ready_inventory.py", "--account-id", "night_scout",
                "--evergreen-bank", "--apply", "--confirm-ready-maintenance",
                "--use-sheets"]
        with (
            patch.object(sys, "argv", args),
            patch.object(m, "SheetsClient", return_value=client),
            patch.object(m, "get_config",
                         return_value={"sheet_id": "synthetic", "sa_dict": {}}),
            patch.object(m, "read_records_safely",
                         side_effect=AssertionError("CLI duplicate queue read")) as read,
            patch.object(m, "replenish_bank", return_value={
                "account_id": "night_scout", "status": "QUALITY_EXHAUSTED",
                "usable_evergreen": 0, "minimum": 30, "would_post": False,
            }) as bank,
            redirect_stdout(out),
        ):
            rc = m.main()
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(out.getvalue())["status"], "FAILED")
        read.assert_not_called()
        client._ensure_tab.assert_not_called()
        bank.assert_called_once_with(client, "night_scout", apply=True)

    def test_explicit_bank_reuse_only_invokes_no_ai_bank_path(self):
        client = Mock()
        output = StringIO()
        argv = [
            "maintain_text_ready_inventory.py", "--account-id", "beauty_account",
            "--evergreen-bank", "--bank-reuse-only", "--apply",
            "--confirm-ready-maintenance", "--use-sheets",
        ]
        with (
            patch.object(sys, "argv", argv),
            patch.object(m, "SheetsClient", return_value=client),
            patch.object(m, "get_config", return_value={
                "sheet_id": "synthetic", "sa_dict": {},
            }),
            patch.object(m, "replenish_bank", return_value={
                "status": "QUALITY_EXHAUSTED", "account_id": "beauty_account",
                "usable_evergreen": 25, "minimum": 30, "reuse_only": True,
                "failure_category": "NO_VALIDATED_BANK_CANDIDATE",
                "would_post": False, "attempts": [],
            }) as bank,
            redirect_stdout(output),
        ):
            code = m.main()
        doc = json.loads(output.getvalue())
        self.assertEqual(code, 1)
        self.assertEqual(doc["status"], "FAILED")
        self.assertEqual(doc["mode"], "EVERGREEN_BANK")
        self.assertFalse(doc["would_post"])
        bank.assert_called_once_with(
            client, "beauty_account", apply=True, reuse_only=True,
        )

    def test_bank_reuse_only_requires_confirmed_bank_apply(self):
        invalid = (
            ["--bank-reuse-only", "--evergreen-bank", "--dry-run"],
            ["--bank-reuse-only", "--apply", "--confirm-ready-maintenance",
             "--use-sheets"],
            ["--bank-reuse-only", "--evergreen-bank", "--apply",
             "--confirm-ready-maintenance"],
            ["--bank-reuse-only", "--evergreen-bank", "--apply",
             "--confirm-ready-maintenance", "--use-sheets",
             "--reuse-only"],
        )
        for tail in invalid:
            with self.subTest(tail=tail):
                out = StringIO()
                with (
                    patch.object(sys, "argv", [
                        "maintain_text_ready_inventory.py",
                        "--account-id", "beauty_account", *tail,
                    ]),
                    patch.object(m, "get_config",
                                 side_effect=AssertionError("No credentials")) as cfg,
                    redirect_stdout(out),
                ):
                    code = m.main()
                self.assertEqual(code, 1)
                self.assertEqual(json.loads(out.getvalue())["status"], "BLOCKED")
                cfg.assert_not_called()

    def test_bank_plan_does_not_create_sheets_client_or_read_credentials(self):
        out = StringIO()
        with (
            patch.object(sys, "argv", [
                "maintain_text_ready_inventory.py", "--account-id", "night_scout",
                "--evergreen-bank", "--dry-run", "--use-sheets",
            ]),
            patch.object(m, "SheetsClient",
                         side_effect=AssertionError("Plan needs no Sheets")) as client,
            patch.object(m, "get_config",
                         side_effect=AssertionError("Plan needs no secrets")) as config,
            patch.object(m, "replenish_bank", return_value={
                "account_id": "night_scout", "status": "PLAN_ONLY",
                "minimum": 30, "would_post": False,
            }) as bank,
            redirect_stdout(out),
        ):
            rc = m.main()
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out.getvalue())["status"], "PLAN_ONLY")
        client.assert_not_called()
        config.assert_not_called()
        bank.assert_called_once_with(None, "night_scout", apply=False)

    def test_apply_bank_quality_exhaustion_returns_nonzero(self):
        rc, doc, bank, _ = self._run_cli("QUALITY_EXHAUSTED", apply=True)
        self.assertEqual(rc, 1)
        self.assertEqual(doc["status"], "FAILED")
        self.assertEqual(doc["bank_failure_reason"], "EVERGREEN_BANK_NOT_READY")
        self.assertNotIn("NO_REQUIRED_TEXT_SLOTS", json.dumps(doc))
        bank.assert_called_once()

    def test_dry_run_bank_plan_succeeds_but_does_not_apply(self):
        rc, doc, called, _ = self._run_cli("PLAN_ONLY", apply=False)
        self.assertEqual(rc, 0)
        self.assertEqual(doc["status"], "PLAN_ONLY")
        self.assertFalse(called.call_args.kwargs["apply"])
        self.assertFalse(doc["would_post"])

    def test_dry_run_all_accounts_requires_all_three_plans(self):
        rc, doc, called, _ = self._run_cli("PLAN_ONLY", apply=False, account="all")
        self.assertEqual(rc, 0)
        self.assertEqual(doc["status"], "PLAN_ONLY")
        self.assertEqual(called.call_count, 3)
        self.assertEqual(set(doc["evergreen_bank_by_account"]),
                         set(m.PREPARED_ACCOUNTS))

    def test_apply_all_accounts_remains_blocked(self):
        out = StringIO()
        with patch.object(sys, "argv", ["maintain_text_ready_inventory.py",
             "--account-id", "all", "--evergreen-bank", "--apply",
             "--confirm-ready-maintenance", "--use-sheets"]), \
             patch.object(m, "SheetsClient",
                          side_effect=AssertionError("No client allowed")), \
             redirect_stdout(out):
            rc = m.main()
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(out.getvalue())["reason"],
                         "apply_requires_one_account")

    def test_provider_timeout_pause_classification(self):
        self.assertTrue(m.paid_generation_pause_required({
            "status": "QUALITY_EXHAUSTED",
            "attempts": [{"reason": "PROVIDER_TIMEOUT"}]
        }))
        self.assertTrue(m.paid_generation_pause_required({
            "failure_category": "AI_APPROVAL_BUDGET_EXHAUSTED"
        }))
        self.assertFalse(m.paid_generation_pause_required({
            "status": "QUALITY_EXHAUSTED",
            "attempts": [{"reason": "QUALITY_EXHAUSTED"}]
        }))

    def test_exact_no_post_and_owner_gates_unmodified(self):
        source = (ROOT / "scripts/maintain_text_ready_inventory.py").read_text()
        self.assertIn("confirm_real_post=False", source)
        self.assertIn("PUBLISH_ENABLED", source)
        self.assertIn("OWNER_REVIEW_REQUIRED", source)
        self.assertIn("paid_generation_pause_required(result):", source)
        self.assertIn("--reuse-only", source)


if __name__ == "__main__":
    unittest.main()
