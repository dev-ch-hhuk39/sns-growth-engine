#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    sources = json.loads((ROOT / "config/source_accounts/default_sources.json").read_text(encoding="utf-8"))["sources"]
    checks = [
        ("source 63件", len(sources) == 63),
        ("fetch_enabled true 0件", sum(1 for s in sources if s.get("fetch_enabled") is True) == 0),
        ("allow_network_fetchは実fetchを意味しない", all(s.get("fetch_enabled") is not True for s in sources)),
    ]
    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {n}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
