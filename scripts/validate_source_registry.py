#!/usr/bin/env python3
"""Validate the local source registry without fetching or writing anything."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from reference.source_registry import load_registry, validate_registry


def main() -> int:
    issues = validate_registry(load_registry())
    for issue in issues:
        print(f"FAIL {issue.get('source_id', '')}: {', '.join(issue.get('errors', []))}")
    print(f"PASS: {0 if issues else 1} / FAIL: {len(issues)}")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
