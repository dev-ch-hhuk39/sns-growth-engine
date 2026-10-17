#!/usr/bin/env python3
"""Contract: manual VPS audit surfaces capacity/pointers without mutation."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / ".github/workflows/production-storage-readonly-audit.yml"


class SnsReadOnlyCapacitySnapshotTests(unittest.TestCase):
    def setUp(self):
        source = AUDIT.read_text(encoding="utf-8")
        first = source.index("SNS_RELEASE_CAPACITY_READONLY_V1_BEGIN")
        last = source.index("SNS_RELEASE_CAPACITY_READONLY_V1_END", first)
        self.source = source
        self.block = source[first:last]

    def test_bounded_capacity_gate_uses_9_gib_not_old_8_gib(self):
        self.assertIn("SNS_NEW_STAGE_9GIB_GATE=PASS", self.block)
        self.assertIn("SNS_NEW_STAGE_9GIB_GATE=BLOCKED", self.block)
        self.assertIn("9 * 1024 * 1024 * 1024", self.block)
        self.assertIn("df -B1 --output=avail /", self.block)

    def test_current_previous_pending_pointers_are_all_inspected(self):
        self.assertIn("for role in current previous pending; do", self.block)
        self.assertIn('if [ ! -L "$pointer" ]; then', self.block)
        self.assertIn('readlink -f "$pointer"', self.block)
        self.assertIn('"$parent" = "$releases_real"', self.block)
        self.assertIn('^' + '[0-9a-f]{40}' + '$', self.block)
        self.assertIn("SNS_RELEASE_POINTERS=UNVERIFIABLE_RUNTIME_SCOPE", self.block)

    def test_read_only_contract_does_not_create_or_delete_anything(self):
        # The new exact section is a pure inspection and stdout report.
        forbidden = (
            r"\brm\b", r"\brmdir\b", r"\bmv\b", r"\bln\s+-s",
            r"\bmkdir\b", r"\bunlink\b", r"\btruncate\b",
            r"\bchmod\b", r"\bchown\b", r"\bdocker\b",
            r"\bgit\s+push\b", r"\bcurl\b", r"\bwget\b",
        )
        for pattern in forbidden:
            self.assertIsNone(re.search(pattern, self.block), pattern)
        self.assertNotIn("PUBLISH_ENABLED=true", self.block)
        self.assertNotIn("SNS_P0_ONCE_GATE_ENABLED=true", self.block)

    def test_audit_remains_manual_and_without_additional_permissions(self):
        self.assertIn("  workflow_dispatch:", self.source)
        self.assertNotIn("  pull_request:", self.source)
        self.assertNotIn("  schedule:", self.source)
        self.assertIn("  contents: read", self.source)
        self.assertNotIn("  actions: write", self.source)


if __name__ == "__main__":
    unittest.main()
