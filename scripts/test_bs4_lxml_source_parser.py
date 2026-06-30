#!/usr/bin/env python3
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("s", ROOT / "scripts/collect_source_posts.py")
s = importlib.util.module_from_spec(spec); spec.loader.exec_module(s)
html = '<html><head><meta property="og:title" content="Title"><meta property="og:description" content="Desc"><meta property="og:image" content="https://example.com/a.jpg"></head></html>'
meta = s.parse_og_metadata(html, "https://www.threads.com/@handle/post/id")
checks = [
    ("title parsed", meta["og_title"] == "Title"),
    ("description parsed", meta["og_description"] == "Desc"),
    ("image parsed", meta["og_image"].endswith("a.jpg")),
    ("handle parsed", meta["author_handle"] == "handle"),
    ("adapter status", s.adapter_status()["threads_public_og"] == "wired"),
]
bad = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
