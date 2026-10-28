#!/usr/bin/env python3
"""Isolated integration simulation of deploy, failed health and rollback.

The test copies the transaction into a private temp directory and rewrites
ONLY its global lock path in the test copy. Production code never allows a
caller-supplied lock bypass.
"""
from __future__ import annotations
import fcntl
import os
import shutil
import subprocess
import tempfile
import time
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
        self._exe('flock', '''#!/usr/bin/env python3
import fcntl, os, sys
from pathlib import Path
if os.environ.get('TEST_GLOBAL_LOCK_BUSY_RC'):
    raise SystemExit(int(os.environ['TEST_GLOBAL_LOCK_BUSY_RC']))
fd = int(sys.argv[-1])
if '-u' in sys.argv:
    fcntl.flock(fd, fcntl.LOCK_UN)
else:
    waiting = os.environ.get('TEST_LOCK_WAITING')
    if waiting:
        Path(waiting).touch()
    fcntl.flock(fd, fcntl.LOCK_EX)
''')
        self._exe('ffmpeg', '#!/bin/sh\nexit 0\n')
        self._exe('xvfb-run', '#!/bin/sh\nexit 0\n')
        self._exe('mv', '#!/bin/sh\nif [ "$1" = "-Tf" ]; then shift; [ ! -L "$2" ] || /bin/rm -f "$2"; fi\nexec /bin/mv -f "$@"\n')
        self._exe('readlink', '#!/bin/sh\nif [ "$1" = "-f" ]; then shift; exec /usr/bin/python3 -c "import os,sys;print(os.path.realpath(sys.argv[1]))" "$1"; fi\nexec /usr/bin/readlink "$@"\n')
        self._exe('stat', '#!/bin/sh\nif [ "$1" = "-c" ]; then shift 2; exec /usr/bin/python3 -c "import os,stat,sys;print(format(stat.S_IMODE(os.stat(sys.argv[1]).st_mode),chr(111)))" "$1"; fi\nexec /usr/bin/stat "$@"\n')
        self._exe('crontab', '#!/bin/sh\nprintf "%s\\n" crontab >> "$TEST_STAGE_TRACE"\nif [ "$1" = "-l" ]; then cat "$TEST_CRON_FILE"; else cp "$1" "$TEST_CRON_FILE"; fi\n')
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
        self.stage_trace = self.top / 'stage-trace'
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
                        TEST_STAGE_TRACE=str(self.stage_trace),
                        GCP_SA_JSON_BASE64='not_real', SPREADSHEET_ID='test',
                        CLOUDINARY_CLOUD_NAME='test', CLOUDINARY_API_KEY='test',
                        CLOUDINARY_API_SECRET='test', GEMINI_API_KEY='test',
                        BUFFERED_POSTING_ENABLED='false')

    def _exe(self, name, source):
        p = self.bin / name; p.write_text(source); p.chmod(0o755)

    def _source_exe(self, name, source):
        first, rest = source.split('\n', 1)
        source = first + '\nprintf "%s\\n" ' + name + ' >> "$TEST_STAGE_TRACE"\n' + rest
        p = self.source / 'scripts' / name; p.write_text(source); p.chmod(0o755)

    def transaction_command(self, *args):
        return [str(self.transaction), '--source-root', str(self.source),
                '--revision', NEW, '--confirm-deploy', '--enable-scheduler', *args]

    def run_transaction(self, *args, **flags):
        return subprocess.run(self.transaction_command(*args),
                              env={**self.env, **flags}, capture_output=True, text=True,
                              timeout=30, check=False)

    def current(self):
        return (self.runtime / 'current').resolve()

    def saved_state(self):
        state = {}
        for path in [self.runtime, *self.runtime.rglob('*')]:
            meta = path.lstat()
            value = ('link', os.readlink(path)) if path.is_symlink() else (
                ('file', path.read_bytes()) if path.is_file() else ('directory',))
            state[str(path.relative_to(self.runtime))] = (
                value, meta.st_mode, meta.st_mtime_ns, meta.st_ino)
        return state, self.cron.read_bytes()

    def assert_refused_before_children(self, result, before, code=78):
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(self.saved_state(), before)
        self.assertFalse(self.stage_trace.exists(), result.stdout + result.stderr)
        self.assertFalse(self.counter.exists())

    def test_matching_expected_current_revision_deploys_normally(self):
        result = self.run_transaction('--expected-current-revision', OLD)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.current(), self.releases / NEW)
        self.assertEqual((self.runtime / 'previous').resolve(), self.old)
        self.assertEqual(self.counter.read_text().strip(), '2')

    def test_mismatched_expected_current_preserves_runtime_and_runs_no_child(self):
        # A rejected stale approval must preserve pre-existing operational
        # state too, rather than cleaning or replacing somebody else's work.
        (self.runtime / 'previous').symlink_to(self.old)
        (self.runtime / 'pending').symlink_to(self.old)
        cli = self.shared / 'threads-cli'
        cli.mkdir()
        (cli / 'th').write_bytes(b'existing shared CLI\n')
        before = self.saved_state()
        result = self.run_transaction('--expected-current-revision', 'c' * 40)
        self.assertIn('expected current release changed or is unverified', result.stderr)
        self.assert_refused_before_children(result, before)

    def test_matching_expected_revision_keeps_failed_promotion_rollback(self):
        result = self.run_transaction('--expected-current-revision', OLD,
                                      TEST_HEALTH_FAIL_AT='2')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.current(), self.old)
        self.assertEqual(self.counter.read_text().strip(), '3')
        self.assertEqual(self.cron.read_text(), '# previous cron\n')
        self.assertIn('restoring previous runtime', result.stderr)

    def test_invalid_missing_or_duplicate_expected_current_is_argument_error(self):
        invalid = (
            ('--expected-current-revision',),
            ('--expected-current-revision', ''),
            ('--expected-current-revision', 'a' * 39),
            ('--expected-current-revision', 'A' * 40),
            ('--expected-current-revision', '--confirm-deploy'),
            ('--expected-current-revision', OLD, '--expected-current-revision', OLD),
            ('--expected-current-revision', OLD, '--expected-current-revision', NEW),
        )
        for args in invalid:
            with self.subTest(args=args):
                before = self.saved_state()
                self.assert_refused_before_children(self.run_transaction(*args), before, code=64)

    def test_expected_current_requires_exact_unlinked_marker(self):
        marker = self.old / '.production-release'
        for mutation in ('wrong-sha', 'missing', 'linked'):
            with self.subTest(mutation=mutation):
                marker.unlink(missing_ok=True)
                if mutation == 'wrong-sha':
                    marker.write_text('c' * 40 + '\n')
                elif mutation == 'linked':
                    other = self.top / 'linked-marker'
                    other.write_text(OLD + '\n')
                    marker.symlink_to(other)
                before = self.saved_state()
                result = self.run_transaction('--expected-current-revision', OLD)
                self.assert_refused_before_children(result, before)

    def test_expected_current_marker_comparison_rejects_noncanonical_bytes(self):
        marker = self.old / '.production-release'
        invalid = (
            OLD.encode() + b'\x00\n',
            OLD.encode() + b'\n\n',
            OLD.encode() + b'\r\n',
            OLD.encode() + b'\xff\n',
            OLD.encode() + b'\n' + b'x' * 100_000,
        )
        for contents in invalid:
            with self.subTest(suffix=contents[40:44]):
                marker.write_bytes(contents)
                before = self.saved_state()
                result = self.run_transaction('--expected-current-revision', OLD)
                self.assert_refused_before_children(result, before)

    def test_expected_current_accepts_legacy_bare_sha_marker(self):
        (self.old / '.production-release').write_bytes(OLD.encode())
        result = self.run_transaction('--expected-current-revision', OLD)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.current(), self.releases / NEW)
        self.assertEqual(self.counter.read_text().strip(), '2')

    def test_expected_current_requires_canonical_release_path(self):
        other = self.releases / ('c' * 40)
        other.mkdir()
        (other / '.production-release').write_text(OLD + '\n')
        pointer = self.runtime / 'current'
        pointer.unlink()
        pointer.symlink_to(other)
        before = self.saved_state()
        result = self.run_transaction('--expected-current-revision', OLD)
        self.assert_refused_before_children(result, before)

    def test_current_changed_while_waiting_for_real_lock_is_refused(self):
        waiting = self.top / 'waiting-for-lock'
        with self.lock.open('r+') as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            process = subprocess.Popen(
                self.transaction_command('--expected-current-revision', OLD),
                env={**self.env, 'TEST_LOCK_WAITING': str(waiting)},
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                deadline = time.monotonic() + 8
                while not waiting.exists() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(waiting.exists(), 'transaction did not reach its real lock wait')
                self.assertIsNone(process.poll(), 'transaction did not wait for the held lock')
                self.assertFalse(self.stage_trace.exists())
                changed = self.releases / ('c' * 40)
                changed.mkdir()
                (changed / '.production-release').write_text('c' * 40 + '\n')
                pointer = self.runtime / 'current'
                pointer.unlink()
                pointer.symlink_to(changed)
                before = self.saved_state()
                fcntl.flock(held, fcntl.LOCK_UN)
                stdout, stderr = process.communicate(timeout=15)
                result = subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)
                self.assert_refused_before_children(result, before)
                self.assertEqual(self.current(), changed)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()

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
        # A transaction-created pending link is removed after a failed stage;
        # the immutable candidate directory remains for inspection.
        self.assertFalse((self.runtime / 'pending').exists())
        self.assertTrue((self.releases / NEW).is_dir())
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
