#!/usr/bin/env python3
"""Daily Mac security audit replaces hosted schedule; PR controls remain enforced."""
from pathlib import Path
import unittest

CI = Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml"


class SecurityScheduleContract(unittest.TestCase):
    def test_nightly_moved_to_mac_and_pr_security_stays_on_hosted_ci(self):
        text = CI.read_text(encoding="utf-8")
        self.assertNotIn("  schedule:", text)
        self.assertEqual(text.count(
            "if: github.event_name == 'pull_request' || github.event_name == 'workflow_dispatch'"
        ), 3)
        plist = (CI.parents[2] / "ops/launchd/com.chadult.sns.repo-security-audit.plist").read_text()
        self.assertIn("com.chadult.sns.repo-security-audit", plist)
        self.assertIn("<key>Hour</key><integer>3</integer>", plist)
        self.assertIn("<key>Minute</key><integer>20</integer>", plist)
        self.assertIn("  dependency-audit:", text)
        self.assertIn("  secret-history-scan:", text)
        self.assertIn("if: github.event_name == 'pull_request'\n", text)
        self.assertIn("github.event_name == 'pull_request' || github.event_name == 'workflow_dispatch'", text)
        self.assertIn("pypa/gh-action-pip-audit@1220774d901786e6f652ae159f7b6bc8fea6d266", text)
        self.assertIn("gitleaks/gitleaks-action@e0c47f4f8be36e29cdc102c57e68cb5cbf0e8d1e", text)
        self.assertIn("permissions:\n  contents: read", text)
        self.assertNotIn("contents: write", text)


if __name__ == "__main__":
    unittest.main()
