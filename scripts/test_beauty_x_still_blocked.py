#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main() -> int:
    sources = json.loads((ROOT / "config/source_accounts/default_sources.json").read_text())["sources"]
    beauty_ok = all(not s.get("active") and not s.get("fetch_enabled") for s in sources if "beauty_account" in (s.get("target_account_ids") or [s.get("target_account_id")]))
    x_ok = all(not s.get("fetch_enabled") for s in sources if s.get("source_platform") == "x")
    ok = beauty_ok and x_ok
    print(f"  {'PASS' if ok else 'FAIL'} beauty/x still blocked")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
