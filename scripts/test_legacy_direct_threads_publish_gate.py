#!/usr/bin/env python3
"""Reject legacy direct Threads outbound even when all old env flags are true."""
from __future__ import annotations
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class LegacyDirectPublisherTests(unittest.TestCase):
    def test_direct_cli_must_block_before_publisher_import(self):
        # No credential or network access is needed; an injected path in PYTHONPATH
        # should never be reached because the CLI refuses real mode first.
        env = {**os.environ, "PUBLISH_ENABLED": "true",
               "ALLOW_REAL_THREADS_POST": "true", "SNS_P0_ONCE_GATE_ENABLED": "true"}
        r = subprocess.run([sys.executable, "-B", "scripts/publish_threads_post.py",
                            "--account-id", "night_scout",
                            "--text", "Synthetic never publish", "--confirm-post",
                            "--no-dry-run"], cwd=ROOT, env=env,
                           text=True, capture_output=True, timeout=15)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("THREADS_DIRECT_REAL_POST_UNSUPPORTED_USE_CANONICAL_QUEUE", r.stdout)

    def test_dry_run_remains_available(self):
        env={**os.environ, "PUBLISH_ENABLED": "false", "ALLOW_REAL_THREADS_POST": "false"}
        r=subprocess.run([sys.executable, "-B", "scripts/publish_threads_post.py",
                          "--account-id", "night_scout", "--mock", "--dry-run"],
                         cwd=ROOT, env=env, text=True, capture_output=True, timeout=15)
        self.assertEqual(r.returncode, 0, r.stdout+r.stderr)
        self.assertIn("DRY_RUN", r.stdout)

    def test_workflow_has_no_real_direct_send(self):
        import yaml
        path=ROOT/".github/workflows/content-pilot-publish.yml"
        data=yaml.safe_load(path.read_text())
        steps=data["jobs"]["pilot-publish"]["steps"]
        offending=[step.get("name","") for step in steps
                   if "--no-dry-run" in str(step.get("run",""))
                   or "PUBLISH_ENABLED: true" in str(step.get("run",""))]
        self.assertEqual(offending, [])
        self.assertTrue(any("THREADS_DIRECT_REAL_POST_UNSUPPORTED_USE_CANONICAL_QUEUE" in
                            str(step.get("run","")) for step in steps))

    def test_other_real_threads_calls_are_only_canonical_worker(self):
        # A future developer cannot silently register a new direct CLI sender.
        legacy=(ROOT/"scripts/publish_threads_post.py").read_text()
        canonical=(ROOT/"scripts/process_threads_queue.py").read_text()
        self.assertIn('if not dry_run:', legacy)
        self.assertIn("THREADS_DIRECT_REAL_POST_UNSUPPORTED_USE_CANONICAL_QUEUE",legacy)
        self.assertIn("p0_once.claim(",canonical)
        self.assertIn("    result = publisher.publish(",canonical)

if __name__=="__main__":
    unittest.main(verbosity=2)
