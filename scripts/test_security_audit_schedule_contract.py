#!/usr/bin/env python3
"""Static fail-closed contract for hosted read-only nightly and PR security CI."""
from pathlib import Path
import unittest

CI = Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml"


class SecurityScheduleContract(unittest.TestCase):
    def test_nightly_and_pull_request_security_audits_are_hosted_and_readonly(self):
        text = CI.read_text(encoding="utf-8")
        self.assertIn('  schedule:\n    - cron: "20 18 * * *"', text)
        self.assertEqual(text.count(
            "if: github.event_name == 'pull_request' || github.event_name == 'workflow_dispatch' || github.event_name == 'schedule'"
        ), 2)
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
