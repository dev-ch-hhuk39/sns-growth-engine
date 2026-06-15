#!/usr/bin/env python3
"""check_source_fetcher_tools.py - Source Fetcher ツール導入確認 CLI"""
from __future__ import annotations
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from src.reference.fetchers.tool_doctor import run_all_checks, print_report


def main() -> int:
    results = run_all_checks()
    return print_report(results)


if __name__ == "__main__":
    sys.exit(main())
