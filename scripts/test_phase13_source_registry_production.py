#!/usr/bin/env python3
"""Compatibility wrapper for production source registry tests."""
from __future__ import annotations

import os
import subprocess
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


if __name__ == "__main__":
    r = subprocess.run([sys.executable, "scripts/test_phase13_production_sources.py"], cwd=_ROOT)
    sys.exit(r.returncode)
