#!/usr/bin/env python3
"""GitHub App ID reuse never refreshes or bypasses the official preflight."""
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import verify_github_liver_app_pin as pin

PREVIEW = {'status': 'DRY_RUN', 'accounts': {'liver_manager': 'DUE'},
           'refresh_due': 1, 'posts': 0}


class GithubAppPinTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.shared = self.root / 'shared'
        self.shared.mkdir(mode=0o700)
        (self.shared / 'threads_tokens').mkdir(mode=0o700)
        self.env = self.shared / 'runtime.env'
        self.env.write_text('BUFFERED_POSTING_ENABLED=false\n')
        self.env.chmod(0o600)
        self.target = self.shared / pin.PIN_NAME
        self.candidate = '123456789012345'

    def run_pin(self, apply=True):
        return pin.run(self.candidate, apply_pin=apply, runtime=self.root)

    def test_valid_pin_is_private_idempotent_and_does_not_modify_host_env(self):
        before = self.env.read_bytes()
        with patch.object(pin, 'preflight', return_value=PREVIEW) as check:
            first = self.run_pin()
            second = self.run_pin()
        self.assertEqual(check.call_count, 2)
        self.assertEqual(first['configuration_writes'], 1)
        self.assertEqual(second['configuration_writes'], 0)
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.target.read_text(), pin.PIN_KEY+'='+self.candidate+'\n')
        self.assertEqual(self.env.read_bytes(), before)
        self.assertNotIn(self.candidate, json.dumps(first))
        for field in ('token_refreshes', 'posts', 'sheets_writes'):
            self.assertEqual(first[field], 0)

    def test_preview_verifies_without_persisting(self):
        with patch.object(pin, 'preflight', return_value=PREVIEW):
            report = self.run_pin(False)
        self.assertEqual(report['status'], 'VERIFIED_PREVIEW')
        self.assertFalse(self.target.exists())

    def test_failed_provider_preflight_cannot_pin(self):
        with patch.object(pin, 'preflight', side_effect=pin.PinBlocked('APP_PIN_PREFLIGHT_BLOCKED')):
            with self.assertRaises(pin.PinBlocked):
                self.run_pin()
        self.assertFalse(self.target.exists())

    def test_existing_different_pin_is_preserved_without_calling_provider(self):
        self.target.write_text(pin.PIN_KEY+'=999999999\n')
        self.target.chmod(0o600)
        before = self.target.read_bytes()
        with patch.object(pin, 'preflight') as check, self.assertRaisesRegex(pin.PinBlocked, 'RECONCILIATION'):
            self.run_pin()
        check.assert_not_called()
        self.assertEqual(self.target.read_bytes(), before)

    def test_unsafe_paths_or_invalid_candidate_do_not_call_provider(self):
        with patch.object(pin, 'preflight') as check:
            for candidate in ('', '1234', '123456\nOTHER=1'):
                with self.assertRaises(pin.PinBlocked):
                    pin.run(candidate, apply_pin=True, runtime=self.root)
            self.env.chmod(0o644)
            with self.assertRaises(pin.PinBlocked):
                self.run_pin()
            check.assert_not_called()

    def test_runtime_change_during_provider_check_cannot_pin(self):
        def mutate(*_args):
            self.env.write_text('BUFFERED_POSTING_ENABLED=true\n')
            return PREVIEW
        with patch.object(pin, 'preflight', side_effect=mutate):
            with self.assertRaisesRegex(pin.PinBlocked, 'HOST_ENVIRONMENT_CHANGED'):
                self.run_pin()
        self.assertFalse(self.target.exists())

    def test_foreign_account_apply_output_or_provider_failure_is_not_preflight(self):
        valid = 'SNS_LOCAL_THREADS_TOKENS='+json.dumps(PREVIEW)
        self.assertEqual(pin.validated_preflight(0, valid), PREVIEW)
        for data in ({**PREVIEW, 'status': 'PASS'},
                     {**PREVIEW, 'accounts': {'night_scout': 'DUE'}},
                     {**PREVIEW, 'posts': 1}, {**PREVIEW, 'refresh_due': True}):
            with self.assertRaises(pin.PinBlocked):
                pin.validated_preflight(0, 'SNS_LOCAL_THREADS_TOKENS='+json.dumps(data))
        with self.assertRaises(pin.PinBlocked):
            pin.validated_preflight(1, valid)

    def test_cli_never_echoes_private_runtime_error(self):
        output = io.StringIO()
        with patch.object(pin, 'run', side_effect=RuntimeError('PRIVATE_DO_NOT_PRINT')), \
             patch.dict(os.environ, {'CANDIDATE_LIVER_THREADS_APP_ID': self.candidate}), \
             patch('sys.argv', ['pin', '--confirm', pin.CONFIRM, '--apply-pin']), redirect_stdout(output):
            self.assertEqual(pin.main(), 1)
        self.assertNotIn('PRIVATE_DO_NOT_PRINT', output.getvalue())
        self.assertNotIn(self.candidate, output.getvalue())

    def test_workflow_uses_only_existing_liver_id_no_token_or_app_secret(self):
        workflow = (Path(__file__).resolve().parents[1] / '.github/workflows/verify-liver-threads-app-pin.yml').read_text()
        self.assertEqual(workflow.count('secrets.'), 1)
        self.assertIn('secrets.THREADS_APP_ID_LIVER_MANAGER', workflow)
        self.assertNotIn('schedule:', workflow)
        self.assertIn("github.ref == 'refs/heads/main'", workflow)
        self.assertIn('persist-credentials: false', workflow)
        self.assertNotIn('ACCESS_TOKEN', workflow)
        self.assertNotIn('APP_SECRET', workflow)


if __name__ == '__main__':
    unittest.main()
