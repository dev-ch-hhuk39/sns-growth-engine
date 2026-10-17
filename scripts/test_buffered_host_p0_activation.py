#!/usr/bin/env python3
"""Before global/VPS locks and Google Sheets, a disabled P0 gate stays NO-POST."""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / "scripts/run_buffered_production_host.sh"


class ActivationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sns-host-p0-")
        self.addCleanup(self.temp.cleanup)
        self.runtime = Path(self.temp.name) / ".buffered-runtime"
        self.current = self.runtime / "current"
        (self.current / "scripts").mkdir(parents=True)
        (self.current / "scripts/reconcile_due_production_slots.py").write_text(
            "raise AssertionError('MUST_NOT_START_RECONCILER')\n")
        (self.current / ".production-release").write_text("synthetic\n")
        self.shared = self.runtime / "shared"
        self.shared.mkdir(exist_ok=True)
        self.env_file = self.shared / "runtime.env"

    def run_host(self, *, account="night_scout", posting="true",
                 once="false", dry=False):
        self.env_file.write_text(
            "BUFFERED_POSTING_ENABLED=" + posting + "\n" +
            "SNS_P0_ONCE_GATE_ENABLED=" + once + "\n")
        self.env_file.chmod(0o600)
        cmd = [str(HOST), "--account-id", account]
        cmd += ["--dry-run"] if dry else ["--apply", "--confirm-reconcile"]
        return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True,
                              env={**os.environ, "BUFFERED_RUNTIME_ROOT": str(self.runtime)},
                              timeout=12, check=False)

    def test_runtime_defaults_no_post_without_explicit_approval(self):
        out = self.run_host(posting="false")
        self.assertEqual(out.returncode, 0)
        self.assertIn("disabled by runtime configuration", out.stdout)

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
