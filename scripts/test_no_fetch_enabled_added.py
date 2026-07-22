#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    sources = json.loads((ROOT / "config/source_accounts/default_sources.json").read_text(encoding="utf-8"))["sources"]
    enabled = [s for s in sources if s.get("fetch_enabled") is True]
    checks = [
        ("source registry is populated", len(sources) >= 63),
        ("fetch-enabled set is bounded", 1 <= len(enabled) <= 8),
        ("fetch-enabled sources are active", all(s.get("active") is True for s in enabled)),
        ("X/beauty are never fetch-enabled", all(s.get("source_platform") != "x" and "beauty_account" not in (s.get("target_account_ids") or []) for s in enabled)),
        ("network fetch is explicit", all(s.get("allow_network_fetch") is True for s in enabled)),
    ]
    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {n}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
