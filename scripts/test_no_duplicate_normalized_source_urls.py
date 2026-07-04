#!/usr/bin/env python3
import json
from pathlib import Path

from source_url_utils import normalize_source_url

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    sources = json.loads((ROOT / "config/source_accounts/default_sources.json").read_text(encoding="utf-8"))["sources"]
    urls = [normalize_source_url(s.get("source_url", "")) for s in sources if str(s.get("source_url", "")).strip()]
    duplicates = sorted({u for u in urls if urls.count(u) > 1})
    ok = not duplicates
    print(f"  {'PASS' if ok else 'FAIL'} no duplicate normalized source URLs")
    if duplicates:
        print("duplicates:", duplicates[:20])
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
