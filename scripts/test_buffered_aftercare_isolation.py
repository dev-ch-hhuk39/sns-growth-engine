#!/usr/bin/env python3
"""Execute aftercare against private offline runtimes; never live evidence."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import shlex
import tempfile
import unittest

from test_buffered_auto_ready_host import FakeRuntime, NO_POST_FLAGS, PROVIDER_KEYS, REVISION

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / 'scripts/run_buffered_metrics_aftercare_host.sh'
APPLY = ('--apply', '--confirm-metrics')


class AftercareIsolationTests(unittest.TestCase):
    def runtime(self, directory: str) -> FakeRuntime:
        fixture = FakeRuntime(directory)
        source = HOST.read_text()
        needle = 'shared_deploy_lock="/run/lock/chadult-production-deploy.lock"'
        self.assertEqual(source.count(needle), 1)
        fixture.wrapper.write_text(source.replace(needle, 'shared_deploy_lock=' + shlex.quote(str(fixture.deploy_lock))))
        for name in ('process_threads_metric_jobs.py', 'run_growth_attribution_cycle.py'):
            (fixture.release / 'scripts' / name).write_text('# offline child placeholder\n')
        fixture.write_config(
            AFTERCARE_METRICS_WRITE_APPROVED='true',
            AFTERCARE_ACTIONS_DISABLED_ATTESTED='true',
            AFTERCARE_STRATEGY_WRITE_APPROVED='true',
            AFTERCARE_READY_BANK_REUSE_APPROVED='true',
            AFTERCARE_BEAUTY_METRICS_APPROVED='true',
            BEAUTY_ACTIVATION_APPROVED='true',
            SPREADSHEET_ID='protected-workbook', SNS_MASTER_SHEET_ID=None,
            SA_JSON_BASE64=None,
            GCP_SA_JSON=json.dumps({'fixture_id': 'protected-service-account'}),
            MOCK_LLM='true', MOCK_SHEETS='true', DRY_RUN='true',
        )
        child=fixture.release/'.venv/bin/python'
        body=child.read_text()
        anchor="with open(os.environ['TEST_CAPTURE'], 'a') as out:"
        body=body.replace(anchor, "record['beauty_enabled'] = os.environ.get('BEAUTY_PRODUCTION_ENABLED')\nrecord['caller_threads_present'] = any(os.environ.get(key) for key in ['THREADS_ACCESS_TOKEN_NIGHT_SCOUT','THREADS_USER_ID_NIGHT_SCOUT','THREADS_TOKEN_STORE_DIR'])\n" + anchor, 1)
        child.write_text(body)
        return fixture

    def test_three_accounts_use_protected_real_loader_and_continuous_locks(self):
        for account in ('night_scout', 'liver_manager', 'beauty_account'):
            with self.subTest(account=account), tempfile.TemporaryDirectory() as temporary:
                fixture = self.runtime(temporary)
                result = fixture.execute(*APPLY, '--with-feedback-preview', account=account,
                    SNS_MASTER_SHEET_ID='forged-workbook', NOTE_MASTER_SHEET_ID='forged-legacy',
                    SA_JSON_BASE64=base64.b64encode(json.dumps({'fixture_id': 'forged'}).encode()).decode(),
                    MOCK_LLM='true', MOCK_SHEETS='true', DRY_RUN='true',
                    PYTHONPATH='/nonexistent/caller-imports', THREADS_ACCESS_TOKEN_NIGHT_SCOUT='forged',
                    THREADS_USER_ID_NIGHT_SCOUT='forged', THREADS_TOKEN_STORE_DIR='/nonexistent/forged', TEST_CONFIG_LOADER=str(ROOT/'src/config_loader.py'))
                self.assertEqual(result.returncode, 0, result.stderr)
                children = fixture.children()
                self.assertEqual(len(children), 4)
                self.assertEqual([row['script'] for row in children], [
                    'process_threads_metric_jobs.py', 'process_threads_metric_jobs.py',
                    'run_growth_attribution_cycle.py', 'maintain_text_ready_inventory.py'])
                for row in children:
                    self.assertEqual(row['args'][row['args'].index('--account-id')+1], account)
                    self.assertEqual(row['resolved_sheet_id'], 'protected-workbook')
                    self.assertEqual(row['resolved_sa_fixture'], 'protected-service-account')
                    self.assertEqual(row['locks_held'], [True, True, True])
                    self.assertEqual(row['cwd'], str(fixture.release))
                    self.assertEqual(row['revision'], REVISION)
                    self.assertFalse(row['provider_keys_present'])
                    self.assertFalse(row['caller_threads_present'])
                    self.assertEqual(row['beauty_enabled'], 'true' if account == 'beauty_account' else 'false')
                    self.assertTrue(all(value == 'false' for value in row['flags'].values()))
                self.assertIn('hosted_workflow_equivalent=false', result.stdout)
                self.assertNotIn('PRIVATE_UNPUBLISHED', result.stdout + result.stderr)
                self.assertEqual(list(fixture.shared.glob('aftercare.*')), [])

    def test_alternative_env_file_and_caller_grants_cannot_authorize(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.runtime(temporary)
            forged = fixture.base/'forged.env'
            forged.write_text(fixture.config.read_text())
            forged.chmod(0o600)
            text = fixture.config.read_text().replace('AFTERCARE_METRICS_WRITE_APPROVED=true', 'AFTERCARE_METRICS_WRITE_APPROVED=false')
            fixture.config.write_text(text)
            result = fixture.execute(*APPLY, BUFFERED_RUNTIME_ENV_FILE=str(forged),
                AFTERCARE_METRICS_WRITE_APPROVED='true', AFTERCARE_ACTIONS_DISABLED_ATTESTED='true')
            self.assertEqual(result.returncode, 77, result.stderr)
            self.assertEqual(fixture.children(), [])

    def test_caller_sheets_credentials_cannot_fill_missing_protected_values(self):
        for missing in ('SPREADSHEET_ID', 'GCP_SA_JSON'):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as temporary:
                fixture = self.runtime(temporary)
                fixture.config.write_text('\n'.join(line for line in fixture.config.read_text().splitlines()
                    if not line.startswith(missing+'='))+'\n')
                result = fixture.execute(*APPLY, SNS_MASTER_SHEET_ID='forged',
                    SA_JSON_BASE64='forged', GOOGLE_APPLICATION_CREDENTIALS='/nonexistent/forged.json')
                self.assertEqual(result.returncode, 78, result.stderr)
                self.assertEqual(fixture.children(), [])

    def test_beauty_requires_both_protected_approvals_in_readonly_and_apply(self):
        for missing in ('BEAUTY_ACTIVATION_APPROVED', 'AFTERCARE_BEAUTY_METRICS_APPROVED'):
            for args in (APPLY, ('--dry-run', '--confirm-readonly')):
                with self.subTest(missing=missing,args=args), tempfile.TemporaryDirectory() as temporary:
                    fixture = self.runtime(temporary)
                    fixture.config.write_text('\n'.join(line for line in fixture.config.read_text().splitlines()
                        if not line.startswith(missing+'='))+'\n')
                    result = fixture.execute(*args, account='beauty_account',
                        BEAUTY_ACTIVATION_APPROVED='true', AFTERCARE_BEAUTY_METRICS_APPROVED='true',
                        BEAUTY_PRODUCTION_ENABLED='true')
                    self.assertEqual(result.returncode, 77, result.stderr)
                    self.assertEqual(fixture.children(), [])

    def test_linked_worker_is_refused_before_configuration_or_child_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.runtime(temporary)
            worker = fixture.release/'scripts/process_threads_metric_jobs.py'
            worker.unlink()
            worker.symlink_to(fixture.release/'scripts/run_growth_attribution_cycle.py')
            result = fixture.execute(*APPLY)
            self.assertEqual(result.returncode, 78, result.stderr)
            self.assertEqual(fixture.children(), [])

    def test_metrics_failure_stops_feedback_and_never_leaks_child_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.runtime(temporary)
            result = fixture.execute(*APPLY, '--with-feedback-preview', '--with-strategy-apply',
                TEST_FAIL_STAGE='process_threads_metric_jobs.py')
            self.assertEqual(result.returncode, 23, result.stderr)
            self.assertEqual(len(fixture.children()), 1)
            self.assertIn('no automatic retry', result.stderr)
            self.assertNotIn('PRIVATE_UNPUBLISHED', result.stdout + result.stderr)
            self.assertEqual(list(fixture.shared.glob('aftercare.*')), [])

    def test_moving_current_after_resolution_cannot_change_executed_release(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.runtime(temporary)
            other = fixture.root/'releases'/('b'*40)
            other.mkdir()
            result = fixture.execute(*APPLY, TEST_MOVE_CURRENT=str(other))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(os.path.realpath(fixture.root/'current'), str(other))
            self.assertEqual(len(fixture.children()), 2)
            self.assertTrue(all(row['path'].startswith(str(fixture.release)+'/') for row in fixture.children()))
            self.assertTrue(all(row['locks_held'] == [True,True,True] for row in fixture.children()))


if __name__ == '__main__':
    unittest.main()
