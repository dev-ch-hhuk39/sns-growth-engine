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
        with self.assertRaises(ValueError):
            write_candidate_env(self.env_path, self.root, self.env)

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
        for x in (current, previous, old):
            x.mkdir()
        (self.root / 'current').symlink_to(current)
        (self.root / 'previous').symlink_to(previous)
        (self.root / 'pending').symlink_to(self.candidate)
        os.utime(old, (time.time()-20*86400, time.time()-20*86400))
        state = candidate_state(self.root, current.name, [old.name])
        self.assertEqual(state['rollback'], previous.name)
        self.assertEqual(state['pending'], self.revision)
        for protected in (current.name, previous.name, self.revision):
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
