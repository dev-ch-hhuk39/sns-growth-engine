#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "https://youtube.com/channel/UCzFzty7aEd4tw3NqCW6pkLQ",
    "https://www.tiktok.com/@user5597696107300",
    "https://www.tiktok.com/@me02_lsm",
    "https://www.tiktok.com/@uare.inc",
}


def main() -> int:
    sources = json.loads((ROOT / "config/source_accounts/default_sources.json").read_text(encoding="utf-8"))["sources"]
    rows = [s for s in sources if "liver_manager" in (s.get("target_account_ids") or []) and s.get("source_url") in EXPECTED]
    ok = {r["source_url"] for r in rows} == EXPECTED
    print(f"  {'PASS' if ok else 'FAIL'} liver_manager new YouTube/TikTok sources registered")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
