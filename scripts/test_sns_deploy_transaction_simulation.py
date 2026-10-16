#!/usr/bin/env python3
"""Isolated integration simulation of deploy, failed health and rollback.

The test copies the transaction into a private temp directory and rewrites
ONLY its global lock path in the test copy. Production code never allows a
caller-supplied lock bypass.
"""
from __future__ import annotations
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = 'a' * 40
NEW = 'b' * 40


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='sns-transaction-')
        self.addCleanup(self.temp.cleanup)
        self.top = Path(self.temp.name).resolve()
        self.runtime = self.top / '.buffered-runtime'
        self.shared = self.runtime / 'shared'
        self.releases = self.runtime / 'releases'
        self.shared.mkdir(parents=True)
        self.releases.mkdir()
        self.old = self.releases / OLD
        self.old.mkdir()
        (self.old / '.production-release').write_text(OLD + '\n')
        (self.runtime / 'current').symlink_to(self.old)
        (self.shared / 'runtime.env').write_text('BUFFERED_POSTING_ENABLED=false\n')
        (self.shared / 'runtime.env').chmod(0o600)
        self.lock = self.top / 'global-deploy.lock'
        self.lock.touch()
        self.lock.chmod(0o600)
        self.bin = self.top / 'bin'
        self.bin.mkdir()
        self._exe('flock', '#!/bin/sh\nexit \"${TEST_GLOBAL_LOCK_BUSY_RC:-0}\"\n')
        self._exe('ffmpeg', '#!/bin/sh\nexit 0\n')
        self._exe('xvfb-run', '#!/bin/sh\nexit 0\n')
        self._exe('mv', '#!/bin/sh\nif [ "$1" = "-Tf" ]; then shift; [ ! -L "$2" ] || /bin/rm -f "$2"; fi\nexec /bin/mv -f "$@"\n')
        self._exe('readlink', '#!/bin/sh\nif [ "$1" = "-f" ]; then shift; exec /usr/bin/python3 -c "import os,sys;print(os.path.realpath(sys.argv[1]))" "$1"; fi\nexec /usr/bin/readlink "$@"\n')
        self._exe('stat', '#!/bin/sh\nif [ "$1" = "-c" ]; then shift 2; exec /usr/bin/python3 -c "import os,stat,sys;print(format(stat.S_IMODE(os.stat(sys.argv[1]).st_mode),chr(111)))" "$1"; fi\nexec /usr/bin/stat "$@"\n')
        self._exe('crontab', '#!/bin/sh\nif [ "$1" = "-l" ]; then cat "$TEST_CRON_FILE"; else cp "$1" "$TEST_CRON_FILE"; fi\n')
        self.cron = self.top / 'cron.txt'; self.cron.write_text('# previous cron\n')
        self.source = self.top / 'source'
        (self.source / 'scripts').mkdir(parents=True)
        for name in ('reconcile_due_production_slots.py',):
            (self.source / 'scripts' / name).write_text('# fixture\n')
        (self.source / 'scripts/write_buffered_runtime_env.py').write_text(
            (ROOT / 'scripts/write_buffered_runtime_env.py').read_text())
        self._source_exe('check_chadult_vps_deploy_preflight.sh',
                         '#!/bin/sh\nexit "${TEST_PREFLIGHT_RC:-0}"\n')
        self._source_exe('install_buffered_production_runtime.sh', '''#!/bin/bash
set -e
mode=""; rev=""
while [ "$#" -gt 0 ]; do
  case "$1" in --revision) rev="$2"; shift 2 ;; --stage-only) mode=stage; shift ;;
  --scheduler-only) mode=scheduler; shift ;; *) shift ;; esac
done
if [ "$mode" = stage ]; then
  target="$BUFFERED_RUNTIME_ROOT/releases/$rev"
  mkdir -p "$target/.venv/bin"
  echo "$rev" > "$target/.production-release"
  printf '#!/bin/sh\\nexit 0\\n' > "$target/.venv/bin/python"
  chmod +x "$target/.venv/bin/python"
  exit 0
fi
[ "$mode" = scheduler ] || exit 81
[ "$(readlink -f "$BUFFERED_RUNTIME_ROOT/current")" = "$BUFFERED_RUNTIME_ROOT/releases/$rev" ] || exit 82
exit "${TEST_SCHEDULER_RC:-0}"
''')
        self.counter = self.top / 'health-count'
        self._source_exe('verify_buffered_runtime_health.py', '''#!/bin/bash
set -e
count=0
[ ! -f "$TEST_HEALTH_COUNT" ] || count="$(cat "$TEST_HEALTH_COUNT")"
count=$((count + 1))
echo "$count" > "$TEST_HEALTH_COUNT"
case ",${TEST_HEALTH_FAIL_AT:-0}," in *",$count,"*) exit 78 ;; esac
exit 0
''')
        self._source_exe('install_threads_cli.sh', '#!/bin/sh\nexit 0\n')
        transaction = (ROOT / 'scripts/deploy_buffered_runtime_transaction.sh').read_text()
        transaction = transaction.replace('/run/lock/chadult-production-deploy.lock', str(self.lock))
        self.transaction = self.top / 'transaction-test-only.sh'
        self.transaction.write_text(transaction)
        self.transaction.chmod(0o700)
        self.env = dict(os.environ, PATH=f'{self.bin}:{os.environ["PATH"]}',
                        BUFFERED_RUNTIME_ROOT=str(self.runtime), TEST_CRON_FILE=str(self.cron),
                        TEST_HEALTH_COUNT=str(self.counter),
                        GCP_SA_JSON_BASE64='not_real', SPREADSHEET_ID='test',
                        CLOUDINARY_CLOUD_NAME='test', CLOUDINARY_API_KEY='test',
                        CLOUDINARY_API_SECRET='test', GEMINI_API_KEY='test',
                        BUFFERED_POSTING_ENABLED='false')

    def _exe(self, name, source):
        p = self.bin / name; p.write_text(source); p.chmod(0o755)

    def _source_exe(self, name, source):
        p = self.source / 'scripts' / name; p.write_text(source); p.chmod(0o755)

    def run_transaction(self, **flags):
        return subprocess.run([str(self.transaction), '--source-root', str(self.source),
                               '--revision', NEW, '--confirm-deploy', '--enable-scheduler'],
                              env={**self.env, **flags}, capture_output=True, text=True,
                              timeout=30, check=False)

    def current(self):
        return (self.runtime / 'current').resolve()

    def test_success_protects_previous_and_starts_candidate(self):
        res = self.run_transaction()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(self.current(), self.releases / NEW)
        self.assertEqual((self.runtime / 'previous').resolve(), self.old)
        self.assertFalse((self.runtime / 'pending').exists())
        self.assertEqual(self.counter.read_text().strip(), '2')
        self.assertEqual((self.shared / 'runtime.env').stat().st_mode & 0o777, 0o600)

    def add_only_local_p0_fixture(self):
        # Synthetic activation metadata; this test only verifies secret
        # transport/rollback, never the real provider or actual DB readiness.
        with (self.shared / 'runtime.env').open('a') as out:
            out.write('SNS_P0_ONCE_GATE_ENABLED=true\n')
            out.write('SNS_P0_ONCE_DB_PATH=/private/sns-fixture.sqlite3\n')
            out.write('SNS_P0_ONCE_HMAC_KEY_HEX=' + 'ab' * 32 + '\n')

    def test_missing_local_authority_never_activates_posting(self):
        res = self.run_transaction(BUFFERED_POSTING_ENABLED='true')
        self.assertNotEqual(res.returncode, 0)
        self.assertEqual(self.current(), self.old)
        self.assertIn('BUFFERED_POSTING_ENABLED=false',
                      (self.shared / 'runtime.env').read_text())

    def test_posting_mode_activates_only_after_healthy_promotion(self):
        self.add_only_local_p0_fixture()
        res = self.run_transaction(BUFFERED_POSTING_ENABLED='true')
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(self.counter.read_text().strip(), '2')
        self.assertIn('BUFFERED_POSTING_ENABLED=true', (self.shared / 'runtime.env').read_text())

    def test_posting_mode_never_activates_after_failed_health(self):
        res = self.run_transaction(BUFFERED_POSTING_ENABLED='true', TEST_HEALTH_FAIL_AT='2')
        self.assertNotEqual(res.returncode, 0)
        self.assertEqual(self.current(), self.old)
        self.assertIn('BUFFERED_POSTING_ENABLED=false', (self.shared / 'runtime.env').read_text())

    def test_failed_pre_activation_health_preserves_current(self):
        res = self.run_transaction(TEST_HEALTH_FAIL_AT='1')
        self.assertNotEqual(res.returncode, 0)
        self.assertEqual(self.current(), self.old)
        self.assertTrue((self.runtime / 'pending').is_symlink())
        self.assertFalse((self.runtime / 'previous').exists())
        self.assertEqual(self.counter.read_text().strip(), '1')

    def test_failed_post_activation_health_rolls_back_and_reverifies(self):
        res = self.run_transaction(TEST_HEALTH_FAIL_AT='2')
        self.assertNotEqual(res.returncode, 0)
        self.assertEqual(self.current(), self.old)
        self.assertEqual(self.counter.read_text().strip(), '3')
        self.assertEqual(self.cron.read_text(), '# previous cron\n')
        self.assertIn('restoring previous runtime', res.stderr)

    def test_scheduler_failure_restores_previous(self):
        res = self.run_transaction(TEST_SCHEDULER_RC='55')
        self.assertNotEqual(res.returncode, 0)
        self.assertEqual(self.current(), self.old)
        self.assertEqual(self.counter.read_text().strip(), '3')

    def test_busy_shared_lock_fails_before_staging(self):
        res = self.run_transaction(TEST_GLOBAL_LOCK_BUSY_RC='75')
        self.assertEqual(res.returncode, 75)
        self.assertEqual(self.current(), self.old)
        self.assertFalse((self.releases / NEW).exists())

    def test_failed_rollback_health_escalates_critical_error(self):
        res = self.run_transaction(TEST_HEALTH_FAIL_AT='2,3')
        self.assertEqual(res.returncode, 90)
        self.assertEqual(self.current(), self.old)
        self.assertIn('rollback health re-verification failed', res.stderr)

    def test_unavailable_global_lock_has_no_mutation(self):
        self.lock.unlink()
        res = self.run_transaction()
        self.assertEqual(res.returncode, 78)
        self.assertEqual(self.current(), self.old)
        self.assertFalse((self.releases / NEW).exists())
        self.assertFalse((self.shared / 'runtime.env').stat().st_mode & 0o077)


if __name__ == '__main__':
    unittest.main()
