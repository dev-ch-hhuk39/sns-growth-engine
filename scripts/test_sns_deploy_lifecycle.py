#!/usr/bin/env python3
"""Offline lifecycle, quota/health, retention and deployment-lock contracts."""
from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unittest.mock import Mock, patch

from scripts.write_buffered_runtime_env import write_candidate_env
from scripts.verify_buffered_runtime_health import health_probe
from scripts.prune_obsolete_runtime_releases import candidate_state


class DeploymentLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / '.buffered-runtime'
        self.shared = self.root / 'shared'
        self.shared.mkdir(parents=True)
        self.releases = self.root / 'releases'
        self.releases.mkdir()
        self.revision = 'b' * 40
        self.candidate = self.releases / self.revision
        (self.candidate / '.venv/bin').mkdir(parents=True)
        (self.candidate / '.venv/bin/python').write_text('dummy')
        (self.candidate / '.venv/bin/python').chmod(0o755)
        (self.candidate / '.production-release').write_text(self.revision+'\n')
        self.env = {
            'GCP_SA_JSON_BASE64': 'fake_secret_not_real',
            'SPREADSHEET_ID': 'fixture',
            'CLOUDINARY_CLOUD_NAME': 'fixture',
            'CLOUDINARY_API_KEY': 'fixture',
            'CLOUDINARY_API_SECRET': 'fixture',
            'GEMINI_API_KEY': 'fixture',
            'BUFFERED_POSTING_ENABLED': 'false',
        }
        self.env_path = self.shared / '.next-runtime-env.' + Path('invalid') if False else self.shared / '.next-runtime-env.mock'

    def test_candidate_env_mode_and_secret_sanitization(self):
        write_candidate_env(self.env_path, self.root, self.env)
        self.assertEqual(stat.S_IMODE(self.env_path.stat().st_mode), 0o600)
        self.assertIn('fake_secret_not_real', self.env_path.read_text())
        self.assertEqual(self.env_path.read_text().count('BUFFERED_POSTING_ENABLED='), 1)
        self.assertIn('SNS_P0_AUTONOMY_MODE=canary', self.env_path.read_text())
        with self.assertRaises(ValueError):
            write_candidate_env(self.env_path, self.root, self.env)

    def test_account_specific_app_ids_survive_candidate_environment(self):
        ids = {'THREADS_APP_ID_NIGHT_SCOUT': '123456789',
               'THREADS_APP_ID_LIVER_MANAGER': '234567890',
               'THREADS_APP_ID_BEAUTY_ACCOUNT': '345678901'}
        write_candidate_env(self.env_path, self.root, {
            **self.env, **ids, 'THREADS_APP_SECRET_LIVER_MANAGER': 'not-for-renewal-copy'})
        content = self.env_path.read_text()
        for key, value in ids.items():
            self.assertIn(key + '=' + value + '\n', content)
        self.assertNotIn('not-for-renewal-copy', content)

    def test_invalid_app_id_cannot_enter_runtime_environment(self):
        for value in ('not-an-id', '12345\nOTHER=1', ' 123456', '1234'):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'threads_app_id'):
                write_candidate_env(self.env_path, self.root, {
                    **self.env, 'THREADS_APP_ID_LIVER_MANAGER': value})
            self.assertFalse(self.env_path.exists())

    def test_host_hmac_remains_local_and_survives_env_candidate_rewrite(self):
        live = self.shared / 'runtime.env'
        live.write_text(
            'BUFFERED_POSTING_ENABLED=false\n'
            'SNS_P0_ONCE_GATE_ENABLED=true\n'
            'SNS_P0_ONCE_DB_PATH=/opt/sns-private/ledger.sqlite3\n'
            'SNS_P0_ONCE_HMAC_KEY_HEX=' + 'ab' * 32 + '\n')
        live.chmod(0o600)
        supplied = {
            **self.env,
            'SNS_P0_ONCE_DB_PATH': '/malicious/github/path.sqlite3',
            'SNS_P0_ONCE_HMAC_KEY_HEX': 'ee' * 32,
            'SNS_P0_ONCE_GATE_ENABLED': 'false',
        }
        write_candidate_env(self.env_path, self.root, supplied,
                            inherit_local_p0=live)
        content = self.env_path.read_text()
        self.assertIn('SNS_P0_ONCE_DB_PATH=/opt/sns-private/ledger.sqlite3', content)
        self.assertIn('SNS_P0_ONCE_HMAC_KEY_HEX=' + 'ab'*32, content)
        self.assertNotIn('/malicious/github', content)
        self.assertNotIn('ee'*32, content)
        self.assertIn('SNS_P0_ONCE_GATE_ENABLED=true', content)
        self.assertIn('BUFFERED_POSTING_ENABLED=false', content)

    def test_github_input_never_enables_continuous_or_overrides_local_mode(self):
        supplied = {**self.env, 'SNS_P0_AUTONOMY_MODE': 'continuous'}
        write_candidate_env(self.env_path, self.root, supplied)
        self.assertIn('SNS_P0_AUTONOMY_MODE=canary', self.env_path.read_text())
        self.env_path.unlink()
        live = self.shared / 'runtime.env'
        live.write_text('SNS_P0_AUTONOMY_MODE=continuous\n'
                        'SNS_P0_ONCE_GATE_ENABLED=false\n')
        live.chmod(0o600)
        write_candidate_env(self.env_path, self.root, self.env,
                            inherit_local_p0=live)
        self.assertIn('SNS_P0_AUTONOMY_MODE=continuous', self.env_path.read_text())
        self.env_path.unlink()
        live.write_text('SNS_P0_AUTONOMY_MODE=invalid\n')
        with self.assertRaisesRegex(ValueError, 'autonomy_mode_invalid'):
            write_candidate_env(self.env_path, self.root, self.env,
                                inherit_local_p0=live)
        self.assertFalse(self.env_path.exists())

    def test_posting_enable_requires_preexisting_local_authority(self):
        attempted = {**self.env, 'BUFFERED_POSTING_ENABLED': 'true',
                     'SNS_P0_ONCE_GATE_ENABLED': 'true',
                     'SNS_P0_ONCE_DB_PATH': '/fake/not/trusted.sqlite3',
                     'SNS_P0_ONCE_HMAC_KEY_HEX': 'ff'*32}
        with self.assertRaisesRegex(ValueError, 'host_p0_authority_not_configured'):
            write_candidate_env(self.env_path, self.root, attempted)
        self.assertFalse(self.env_path.exists())

    def test_local_inheritance_must_be_owner_private_and_not_symlink(self):
        live = self.shared / 'runtime.env'
        live.write_text('SNS_P0_ONCE_GATE_ENABLED=false\n')
        live.chmod(0o644)
        with self.assertRaisesRegex(ValueError, 'permissions'):
            write_candidate_env(self.env_path, self.root, self.env,
                                inherit_local_p0=live)
        live.chmod(0o600)
        symlink = self.shared / '.copied-env'
        symlink.symlink_to(live)
        with self.assertRaisesRegex(ValueError, 'untrusted_host_env_source'):
            write_candidate_env(self.env_path, self.root, self.env,
                                inherit_local_p0=symlink)
        self.assertFalse(self.env_path.exists())

    def test_duplicate_or_shell_expression_host_env_is_rejected(self):
        live = self.shared / 'runtime.env'
        for text in (
            'SNS_P0_ONCE_GATE_ENABLED=true\nSNS_P0_ONCE_GATE_ENABLED=false\n',
            'SNS_P0_ONCE_GATE_ENABLED=true; printf BAD\n',
        ):
            live.write_text(text)
            live.chmod(0o600)
            with self.assertRaises(ValueError):
                write_candidate_env(self.env_path, self.root, self.env,
                                    inherit_local_p0=live)
            self.assertFalse(self.env_path.exists())

    def test_missing_secrets_block_without_files(self):
        with self.assertRaises(ValueError):
            write_candidate_env(self.env_path, self.root, {'BUFFERED_POSTING_ENABLED': 'false'})
        self.assertFalse(self.env_path.exists())

    def test_health_passes_local_and_sheets_readiness_checks(self):
        write_candidate_env(self.env_path, self.root, self.env)
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, '', ''))
        self.assertTrue(health_probe(self.candidate, self.revision, self.env_path,
                                    runner=runner, retry_delay=0))
        self.assertIn('client._sh.worksheets()', runner.call_args.args[0][-1])
        self.assertIn("child_env", health_probe.__code__.co_varnames)
        env = runner.call_args.kwargs['env']
        self.assertEqual(env['ALLOW_REAL_THREADS_POST'], 'false')
        self.assertEqual(env['ALLOW_CLOUDINARY_UPLOAD'], 'false')
        self.assertEqual(env['ALLOW_REAL_X_POST'], 'false')

    def test_health_retries_without_creating_any_post(self):
        write_candidate_env(self.env_path, self.root, self.env)
        runner = Mock(side_effect=[subprocess.CompletedProcess([], 1, '', 'secret'),
                                   subprocess.CompletedProcess([], 0, '', '')])
        with patch('scripts.verify_buffered_runtime_health.time.sleep'):
            self.assertTrue(health_probe(self.candidate, self.revision, self.env_path, runner=runner))
        self.assertEqual(runner.call_count, 2)

    def test_health_deadline_exceeded_does_not_skip_retry_or_mark_success(self):
        import subprocess
        write_candidate_env(self.env_path, self.root, self.env)
        runner = Mock(side_effect=subprocess.TimeoutExpired(cmd=['python'], timeout=85))
        with patch('scripts.verify_buffered_runtime_health.time.sleep'):
            self.assertFalse(health_probe(self.candidate, self.revision, self.env_path, runner=runner))
        self.assertEqual(runner.call_count, 2)

    def test_health_fails_on_wrong_revision_or_env_mode(self):
        write_candidate_env(self.env_path, self.root, self.env)
        with self.assertRaises(ValueError):
            health_probe(self.candidate, 'c'*40, self.env_path, runner=Mock())
        self.env_path.chmod(0o644)
        with self.assertRaises(ValueError):
            health_probe(self.candidate, self.revision, self.env_path, runner=Mock())

    def test_retention_protects_explicit_previous_and_pending(self):
        current = self.releases / ('a'*40)
        previous = self.releases / ('c'*40)
        old = self.releases / ('d'*40)
        emergency = self.releases / ('e'*40)
        for x in (current, previous, old, emergency):
            x.mkdir()
            (x / '.production-release').write_text(x.name)
            (x / '.venv' / 'bin').mkdir(parents=True)
            (x / '.venv' / 'bin' / 'python').symlink_to(sys.executable)
        (self.root / 'current').symlink_to(current)
        (self.root / 'previous').symlink_to(previous)
        (self.root / 'pending').symlink_to(self.candidate)
        os.utime(old, (time.time()-20*86400, time.time()-20*86400))
        state = candidate_state(self.root, current.name, [old.name])
        self.assertEqual(state['rollback'], previous.name)
        self.assertEqual(state['pending'], self.revision)
        self.assertEqual(state['emergency'], emergency.name)
        for protected in (current.name, previous.name, self.revision, emergency.name):
            with self.subTest(sha=protected):
                with self.assertRaisesRegex(RuntimeError, 'protected_release_target'):
                    candidate_state(self.root, current.name, [protected])

    def test_retention_does_not_guess_previous_from_mtime(self):
        current = self.releases / ('a'*40)
        old = self.releases / ('d'*40)
        current.mkdir(); old.mkdir()
        (self.root / 'current').symlink_to(current)
        with self.assertRaisesRegex(RuntimeError, 'explicit_previous_release_pointer_required'):
            candidate_state(self.root, current.name, [old.name])

    def test_contract_shared_lock_and_atomic_rollback(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        transaction = (root/'scripts/deploy_buffered_runtime_transaction.sh').read_text()
        media = (root/'scripts/run_buffered_media_preparation_host.sh').read_text()
        account = (root/'scripts/run_buffered_production_host.sh').read_text()
        installer = (root/'scripts/install_buffered_production_runtime.sh').read_text()
        for token in ('chadult-production-deploy.lock', 'flock -x -w 600',
                      'atomic_pointer "$current" "$old_release"',
                      'rollback health re-verification failed',
                      '--stage-only', '--scheduler-only'):
            self.assertIn(token, transaction)
        self.assertIn('flock -s -w 120', media)
        self.assertIn('flock -s -w 120', account)
        self.assertIn('requires >=4 GiB RAM', media)
        self.assertIn('size 20M', installer)
        self.assertIn('command -v logrotate', installer)
        self.assertIn('rotate 5', installer)


if __name__ == '__main__':
    unittest.main()
