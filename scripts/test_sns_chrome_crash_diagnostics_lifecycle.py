#!/usr/bin/env python3
"""Synthetic-only safety checks for dedicated SNS Chrome diagnostics expiry."""
from __future__ import annotations
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import yaml

from cleanup_sns_chrome_crash_diagnostics import (
    Unsafe, candidate_files, MIN_AGE, MAX_COUNT, MAX_BYTES,
)

ROOT=Path(__file__).resolve().parents[1]
WORKFLOW=ROOT/".github/workflows/sns-chrome-crash-diagnostics-lifecycle.yml"
VALID="0ccc126c-0e8d-467e-8c67-a94721227fc2"

class CrashFileExpirySafety(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.target=Path(self.temp.name)/"completed"
        self.target.mkdir()
        self.uid=os.getuid()
        self.now=time.time()
    def make(self,name=VALID+".dmp",age_days=21,content=b"diagnostic"):
        p=self.target/name
        p.write_bytes(content)
        when=self.now-age_days*86400
        os.utime(p,(when,when))
        return p
    def test_old_regular_report_is_candidate(self):
        self.make()
        found,total=candidate_files(self.target,self.uid,self.now)
        self.assertEqual(len(found),1)
        self.assertEqual(total,len(b"diagnostic"))
    def test_fresh_report_is_preserved(self):
        self.make(age_days=2)
        found,total=candidate_files(self.target,self.uid,self.now)
        self.assertEqual(found,[])
        self.assertEqual(total,0)
    def test_unknown_extension_is_never_removed(self):
        self.make(name="important.db",age_days=30)
        with self.assertRaisesRegex(Unsafe,"UNKNOWN_CHILD_EXTENSION"):
            candidate_files(self.target,self.uid,self.now)
    def test_symlink_is_blocked(self):
        real=Path(self.temp.name)/"foreign.txt"
        real.write_text("private")
        (self.target/(VALID+".dmp")).symlink_to(real)
        with self.assertRaisesRegex(Unsafe,"UNTRUSTED_CHILD_FILE"):
            candidate_files(self.target,self.uid,self.now)
        self.assertTrue(real.exists())
    def test_hardlink_is_blocked(self):
        first=self.make()
        other=Path(self.temp.name)/"shared.bin"
        os.link(first,other)
        with self.assertRaisesRegex(Unsafe,"UNTRUSTED_CHILD_FILE"):
            candidate_files(self.target,self.uid,self.now)
        self.assertTrue(other.exists())
    def test_oversized_file_fails_closed(self):
        self.make(content=b"x"*250001)
        with self.assertRaisesRegex(Unsafe,"LARGE_CRASH_FILE_UNEXPECTED"):
            candidate_files(self.target,self.uid,self.now)
    def test_rules_limit_scope(self):
        self.assertLessEqual(MAX_BYTES,100_000_000)
        self.assertLessEqual(MAX_COUNT,3000)
        self.assertGreaterEqual(MIN_AGE,14*86400)
    def test_workflow_is_main_only_no_post(self):
        doc=yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        triggers=doc.get("on",doc.get(True))
        self.assertEqual(set(triggers),{"schedule","workflow_dispatch"})
        self.assertEqual(doc["permissions"],{"contents":"read"})
        job=doc["jobs"]["cleanup"]
        self.assertEqual(job["if"],"github.ref == 'refs/heads/main'")
        self.assertEqual(job["runs-on"],["self-hosted","Linux","X64"])
        for flag in ("PUBLISH_ENABLED","ALLOW_REAL_THREADS_POST","ALLOW_REAL_X_POST"):
            self.assertEqual(job["env"][flag],"false")
        code="\n".join(step.get("run","") for step in job["steps"])
        self.assertIn('test "$(id -un)" = "snsrunner"',code)
        self.assertIn('cleanup_sns_chrome_crash_diagnostics.py --apply',code)
        for forbidden in ("restic forget","restic prune","docker system prune",
                          "rm -rf","--confirm-real-post"):
            self.assertNotIn(forbidden,code)

if __name__=="__main__":
    unittest.main()
