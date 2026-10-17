#!/usr/bin/env python3
"""Offline regression for prepromotion disk and protected rollback controls."""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRANSACTION = ROOT / "scripts/deploy_buffered_runtime_transaction.sh"
WORKFLOW = ROOT / ".github/workflows/resolve-sns-abandoned-pending.yml"


class DeploymentSafetyContract(unittest.TestCase):
    def test_resource_guard_before_stage_and_before_pointer_flip(self):
        s = TRANSACTION.read_text()
        self.assertLess(s.index('--min-free-gib 9'),
                        s.index(' --stage-only'))
        self.assertLess(s.index(' --stage-only'),
                        s.index('--min-free-gib 8'))
        self.assertLess(s.index('--min-free-gib 8'),
                        s.index('promoted=true'))
        self.assertIn('pending_created=true', s)
        self.assertIn('"$pending_created" == true', s)
        self.assertIn('"$completed" != true', s)

    def test_cron_restore_uses_file_descriptor_only_after_change(self):
        s = TRANSACTION.read_text()
        self.assertIn('exec 8< "$backup_cron"', s)
        self.assertIn('crontab - <&8', s)
        self.assertIn('if [[ "$cron_changed" == true ]]', s)
        self.assertIn('cron_changed=true', s)
        self.assertNotIn('crontab "$backup_cron"', s)

    def test_open_file_descriptor_survives_unlink(self):
        with tempfile.TemporaryDirectory(prefix='sns-cron-fd-test-') as td:
            backup = Path(td) / 'sns-cron'
            backup.write_text('SYNTHETIC_CRON_ONLY\n')
            r = subprocess.run(
                ['bash', '-c', 'exec 8< "$1"; rm -- "$1"; '
                 'copied="$(cat <&8)"; '
                 'test "$copied" = SYNTHETIC_CRON_ONLY', 'bash', str(backup)],
                capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(r.returncode, 0)
            self.assertFalse(backup.exists())

    def test_workflow_is_main_only_and_cannot_post_or_delete_release(self):
        text = WORKFLOW.read_text()
        self.assertIn("github.ref == 'refs/heads/main'", text)
        self.assertIn('PUBLISH_ENABLED: "false"', text)
        self.assertIn('ALLOW_REAL_THREADS_POST: "false"', text)
        self.assertIn('CLEAR_EXACT_PENDING_POINTER_ONLY', text)
        self.assertIn('resolve_abandoned_sns_pending.py', text)
        self.assertNotIn('rm -rf', text)
        self.assertNotIn('POSTING_ENABLED: "true"', text)


if __name__ == '__main__':
    unittest.main()
