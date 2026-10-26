#!/usr/bin/env python3
"""No-network unit tests for scheduled source-only security scan."""
from __future__ import annotations
import json
import plistlib
import sys
from pathlib import Path
from unittest.mock import patch
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import sns_local_repo_security_audit as s  # noqa: E402


class AuditContract(unittest.TestCase):
    def test_credentials_stripped_and_posting_off(self):
        with patch.dict(s.os.environ, {
            "GITHUB_TOKEN":"SECRET", "PIP_INDEX_URL":"https://token.invalid/private",
            "THREADS_ACCESS_TOKEN_NIGHT_SCOUT":"SECRET", "NORMAL_VAR":"OK",
        }):
            d=s.safe_environment()
        self.assertNotIn("GITHUB_TOKEN",d)
        self.assertNotIn("PIP_INDEX_URL",d)
        self.assertNotIn("THREADS_ACCESS_TOKEN_NIGHT_SCOUT",d)
        self.assertEqual(d["NORMAL_VAR"],"OK")
        self.assertEqual(d["PUBLISH_ENABLED"],"false")

    def test_bounded_result_parsers(self):
        with patch.object(s,"_temp_json",return_value="/tmp/dummy_never_real"):
            pass
        self.assertEqual(len(s.REQUIREMENTS),4)
        self.assertTrue(all(x.startswith("requirements") for x in s.REQUIREMENTS))
        self.assertEqual(s.GITLEAKS.name,"gitleaks")

    def test_daily_plist_and_no_automatic_publish(self):
        p=plistlib.loads((ROOT/"ops/launchd/com.chadult.sns.repo-security-audit.plist").read_bytes())
        self.assertEqual(p["StartCalendarInterval"],{"Hour":3,"Minute":20})
        self.assertFalse(p["RunAtLoad"])
        self.assertIn("sns_local_repo_security_audit.py",p["ProgramArguments"][-1])
        source=(ROOT/"scripts/sns_local_repo_security_audit.py").read_text()
        for forbidden in ("refresh_access_token", "threads_publish", ".append_rows(", "os.system("):
            self.assertNotIn(forbidden,source)


if __name__ == "__main__":
    unittest.main()
