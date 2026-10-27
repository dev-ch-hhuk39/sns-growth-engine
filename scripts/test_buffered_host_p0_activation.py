#!/usr/bin/env python3
"""Offline publisher gates and immutable-release pinning under a mocked lock."""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / "scripts/run_buffered_production_host.sh"


class ActivationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sns-host-p0-")
        self.addCleanup(self.temp.cleanup)
        self.runtime = Path(self.temp.name).resolve() / ".buffered-runtime"
        self.current = self.runtime / "current"
        self.revision = "a" * 40
        self.release = self.runtime / "releases" / self.revision
        (self.release / "scripts").mkdir(parents=True)
        (self.release / "scripts/reconcile_due_production_slots.py").write_text(
            "raise AssertionError('MUST_NOT_START_RECONCILER')\n")
        (self.release / ".production-release").write_text(self.revision + "\n")
        self.current.symlink_to(self.release)
        self.shared = self.runtime / "shared"
        self.shared.mkdir(exist_ok=True)
        self.env_file = self.shared / "runtime.env"
        self.common_lock = Path(self.temp.name) / "deploy.lock"
        self.common_lock.touch(mode=0o600)
        self.lock_acquired = Path(self.temp.name) / "lock-acquired"
        self.calls = Path(self.temp.name) / "calls.jsonl"
        self.bin = Path(self.temp.name) / "bin"
        self.bin.mkdir()
        self.host = Path(self.temp.name) / "host.sh"
        # Only the isolated test copy may replace the Ops-owned lock path.
        self.host.write_text(HOST.read_text().replace(
            "/run/lock/chadult-production-deploy.lock", str(self.common_lock)))
        self.host.chmod(0o700)
        self._executable("flock", '''import os
import subprocess
import sys
from pathlib import Path
args = sys.argv[1:]
if args[:3] == ['-s', '-w', '120']:
    if os.environ.get('TEST_LOCK_BUSY') == 'true':
        raise SystemExit(1)
    Path(os.environ['TEST_LOCK_ACQUIRED']).touch()
    replacement = os.environ.get('TEST_SWITCH_ON_LOCK')
    if replacement:
        current = Path(os.environ['BUFFERED_RUNTIME_ROOT']) / 'current'
        staged = current.with_name('current.test-next')
        staged.symlink_to(replacement)
        staged.replace(current)
    if 'TEST_ENV_ON_LOCK' in os.environ:
        Path(os.environ['BUFFERED_RUNTIME_ENV_FILE']).write_text(os.environ['TEST_ENV_ON_LOCK'])
    raise SystemExit(0)
if args[:2] == ['-w', '240']:
    args = args[3:]
elif args[:3] == ['-n', '-E', '75']:
    args = args[4:]
else:
    raise SystemExit('unexpected mock flock invocation')
raise SystemExit(subprocess.run(args, check=False).returncode)
''')
        self._executable("readlink", '''import os
import sys
assert sys.argv[1] == '-f'
print(os.path.realpath(sys.argv[2]))
''')
        self._executable("awk", "print('1048576')\n")

    def _executable(self, name, source):
        path = self.bin / name
        path.write_text("#!" + sys.executable + "\n" + source)
        path.chmod(0o700)

    def record_release(self, revision):
        release = self.runtime / "releases" / revision
        (release / "scripts").mkdir(parents=True, exist_ok=True)
        (release / ".production-release").write_text(revision + "\n")
        (release / ".venv/bin").mkdir(parents=True)
        python = release / ".venv/bin/python"
        python.write_text("#!/bin/sh\nexec " + shlex.quote(sys.executable) + ' "$@"\n')
        python.chmod(0o700)
        for script in ("p0_release_mode_authority.py", "validate_p0_once_runtime.py",
                       "reconcile_due_production_slots.py"):
            (release / "scripts" / script).write_text('''import json
import os
import sys
from pathlib import Path
path = Path(__file__)
assert Path(os.environ['TEST_LOCK_ACQUIRED']).is_file(), 'authority before lock'
with Path(os.environ['TEST_CALLS']).open('a') as handle:
    handle.write(json.dumps({'script': path.name, 'release': str(path.parents[1]),
                             'revision': os.environ['CODE_REVISION'],
                             'runtime_release': os.environ['PRODUCTION_RUNTIME_RELEASE'],
                             'argv': sys.argv[1:]}) + '\\n')
replacement = os.environ.get('TEST_SWITCH_AFTER_AUTHORITY')
if path.name == 'p0_release_mode_authority.py' and replacement:
    current = Path(os.environ['BUFFERED_RUNTIME_ROOT']) / 'current'
    staged = current.with_name('current.test-next')
    staged.symlink_to(replacement)
    staged.replace(current)
''')
        return release

    def run_host(self, *, account="night_scout", posting="true",
                 once="false", dry=False, extra_env=None, extra_runtime="", shell_trace=False):
        self.env_file.write_text(
            "BUFFERED_POSTING_ENABLED=" + posting + "\n" +
            "SNS_P0_ONCE_GATE_ENABLED=" + once + "\n" + extra_runtime)
        self.env_file.chmod(0o600)
        cmd = ["bash", *(["-x"] if shell_trace else []), str(self.host), "--account-id", account]
        cmd += ["--dry-run"] if dry else ["--apply", "--confirm-reconcile"]
        return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True,
                              env={**os.environ, "BUFFERED_RUNTIME_ROOT": str(self.runtime),
                                   "BUFFERED_RUNTIME_ENV_FILE": str(self.env_file),
                                   "PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
                                   "TEST_LOCK_ACQUIRED": str(self.lock_acquired),
                                   "TEST_CALLS": str(self.calls), **(extra_env or {})},
                              timeout=12, check=False)

    def test_runtime_defaults_no_post_without_explicit_approval(self):
        out = self.run_host(posting="false")
        self.assertEqual(out.returncode, 0)
        self.assertIn("disabled by runtime configuration", out.stdout)

    def test_shell_tracing_never_exposes_protected_runtime_values(self):
        sentinel = "PROTECTED_RUNTIME_OFFLINE_SENTINEL_MUST_STAY_PRIVATE"
        for shell_trace, extra_env in ((True, {}), (False, {"SHELLOPTS": "xtrace"})):
            with self.subTest(shell_trace=shell_trace, extra_env=extra_env):
                out = self.run_host(posting="false", shell_trace=shell_trace,
                                    extra_env=extra_env,
                                    extra_runtime="PRIVATE_FIXTURE=" + sentinel + "\n")
                self.assertEqual(out.returncode, 0, out.stderr)
                self.assertIn("set +x", out.stderr)
                self.assertNotIn(sentinel, out.stdout + out.stderr)
                self.assertFalse(self.calls.exists())

    def test_explicit_posting_without_one_use_gate_is_blocked_early(self):
        out = self.run_host(posting="true", once="false")
        self.assertEqual(out.returncode, 78)
        self.assertIn("P0_ONCE_RUNTIME_GATE_DISABLED", out.stderr)
        self.assertNotIn("MUST_NOT_START_RECONCILER", out.stderr)

    def test_beauty_and_all_accounts_cannot_enter_text_only_apply(self):
        for account in ("beauty_account", "all"):
            out = self.run_host(account=account, posting="true", once="true")
            with self.subTest(account=account):
                self.assertEqual(out.returncode, 78)
                self.assertIn("P0_ONCE_TEXT_ONLY_ACCOUNT_SCOPE", out.stderr)

    def test_flags_both_on_still_require_exact_owner_approval(self):
        out = self.run_host(posting="true", once="true")
        self.assertEqual(out.returncode, 78)
        self.assertIn("P0_RELEASE_OWNER_CONSENT_OR_HOST_PROOF_MISSING", out.stderr)
        self.assertNotIn("MUST_NOT_START_RECONCILER", out.stderr)

    def assert_release_calls(self, release, *, dry=False):
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        expected = ["reconcile_due_production_slots.py"] if dry else [
            "p0_release_mode_authority.py", "validate_p0_once_runtime.py",
            "reconcile_due_production_slots.py"]
        self.assertEqual([call["script"] for call in calls], expected)
        for call in calls:
            self.assertEqual(call["release"], str(release))
            self.assertEqual(call["runtime_release"], str(release))
            self.assertEqual(call["revision"], release.name)
        if not dry:
            self.assertEqual(calls[0]["argv"], ["--account-id", "night_scout",
                                               "--release-sha", release.name])
            self.assertIn("--apply", calls[-1]["argv"])

    def test_deployment_while_waiting_for_lock_checks_and_executes_new_release(self):
        self.record_release(self.revision)
        next_release = self.record_release("b" * 40)
        out = self.run_host(once="false", extra_env={
            "TEST_SWITCH_ON_LOCK": str(next_release),
            "TEST_ENV_ON_LOCK": "BUFFERED_POSTING_ENABLED=true\nSNS_P0_ONCE_GATE_ENABLED=true\n"})
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(self.current.resolve(), next_release)
        self.assert_release_calls(next_release)

    def test_current_change_after_authority_does_not_change_executed_release(self):
        self.record_release(self.revision)
        next_release = self.record_release("b" * 40)
        out = self.run_host(once="true", extra_env={
            "TEST_SWITCH_AFTER_AUTHORITY": str(next_release)})
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(self.current.resolve(), next_release)
        self.assert_release_calls(self.release)

    def test_dry_run_also_uses_release_resolved_after_lock(self):
        self.record_release(self.revision)
        next_release = self.record_release("b" * 40)
        out = self.run_host(dry=True, extra_env={"TEST_SWITCH_ON_LOCK": str(next_release)})
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assert_release_calls(next_release, dry=True)

    def test_deployment_lock_failure_never_runs_authority_or_reconciler(self):
        self.record_release(self.revision)
        out = self.run_host(once="true", extra_env={"TEST_LOCK_BUSY": "true"})
        self.assertEqual(out.returncode, 75, out.stderr)
        self.assertFalse(self.calls.exists())

    def test_release_marker_must_match_exact_sha_directory(self):
        self.record_release(self.revision)
        for marker in ("synthetic", "b" * 40):
            with self.subTest(marker=marker):
                (self.release / ".production-release").write_text(marker + "\n")
                out = self.run_host(once="true")
                self.assertEqual(out.returncode, 78, out.stderr)
                self.assertFalse(self.calls.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
