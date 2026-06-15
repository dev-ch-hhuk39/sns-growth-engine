#!/usr/bin/env python3
"""Compatibility wrapper for source lifecycle CLI tests."""
from __future__ import annotations

import os
import subprocess
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    result = subprocess.run(
        [sys.executable, "scripts/test_phase13_source_lifecycle_cli.py"],
        cwd=_ROOT,
        text=True,
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
