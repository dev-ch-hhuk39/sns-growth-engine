#!/usr/bin/env python3
"""Keep acquisition failure imports compatible with the VPS Python runtime."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acquisition.failures import FailureCategory, classify_failure


assert isinstance(FailureCategory.RATE_LIMITED, str)
assert str(FailureCategory.RATE_LIMITED) == "RATE_LIMITED"
assert classify_failure("threads", "429 rate_limit") == FailureCategory.RATE_LIMITED
print("acquisition StrEnum compatibility: PASS")
