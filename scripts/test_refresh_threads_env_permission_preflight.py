#!/usr/bin/env python3
"""Token refresh must explain required environment permission before any write."""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "refresh-threads-tokens.yml"


class RefreshEnvironmentPermissionPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.content = WORKFLOW.read_text(encoding="utf-8")

    def test_correct_fine_grained_environment_permission_is_documented(self) -> None:
        self.assertIn("Repository Environments = Read and write", self.content)
        self.assertNotIn('echo "  必要なスコープ: secrets:write"', self.content)

    def test_provider_permission_probe_precedes_secret_write(self) -> None:
        c = self.content
        probe = 'gh api "repos/$GH_REPO/environments/production/secrets/public-key"'
        write = 'gh secret set "$probe_name" --env production --repo "$GH_REPO"'
        self.assertIn(probe, c)
        self.assertLess(c.index(probe), c.index(write))
        self.assertIn("ENVIRONMENT_SECRETS_PERMISSION_DENIED", c)
        self.assertIn("exit 1", c[c.index(probe):c.index(write)])

    def test_probe_never_echos_credential_or_performs_external_publish(self) -> None:
        c = self.content
        probe = c[c.index("# Environment secrets use"):c.index('probe_name="SNS_GH_SECRET_WRITE_PREFLIGHT_')]
        self.assertIn(">/dev/null 2>&1", probe)
        self.assertNotIn('echo "$GH_TOKEN"', probe)
        self.assertNotIn("graph.threads.net", probe)
        self.assertNotIn("curl -X POST", probe)


if __name__ == "__main__":
    unittest.main()
