#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    sources = json.loads((ROOT / "config/source_accounts/default_sources.json").read_text(encoding="utf-8"))["sources"]
    beauty = [s for s in sources if "beauty_account" in (s.get("target_account_ids") or [])]
    checks = [
        ("beauty sourceあり", len(beauty) > 0),
        ("beauty activeなし", all(s.get("active") is False for s in beauty)),
        ("beauty fetch_enabledなし", all(s.get("fetch_enabled") is False for s in beauty)),
        ("beauty_future targetなし", all("beauty_future" not in (s.get("target_account_ids") or []) for s in sources)),
    ]
    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {n}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
