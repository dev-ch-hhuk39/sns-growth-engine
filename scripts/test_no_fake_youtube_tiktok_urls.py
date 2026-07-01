#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sources = json.loads((ROOT / "config/source_accounts/default_sources.json").read_text(encoding="utf-8"))["sources"]
bad_urls = []
for s in sources:
    platform = str(s.get("source_platform") or s.get("platform") or "").lower()
    if platform not in {"youtube", "tiktok"}:
        continue
    url = str(s.get("source_url", "")).strip()
    if not url:
        continue
    if "example.com" in url or "youtube.com/@example" in url or "tiktok.com/@example" in url:
        bad_urls.append(url)
    if platform == "youtube" and "youtube.com" not in url and "youtu.be" not in url:
        bad_urls.append(url)
    if platform == "tiktok" and "tiktok.com" not in url:
        bad_urls.append(url)
checks = [("no fake/non-platform urls", not bad_urls)]
bad = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {n}")
if bad_urls:
    print("bad_urls:", bad_urls[:10])
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
