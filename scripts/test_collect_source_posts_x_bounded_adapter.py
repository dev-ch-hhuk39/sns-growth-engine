#!/usr/bin/env python3
"""Exercise the bounded X gallery-dl adapter shape without network access."""
from __future__ import annotations
import importlib.util, json, types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "scripts/collect_source_posts.py"
spec = importlib.util.spec_from_file_location("collect", path)
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
import acquisition.x_gallerydl as x_adapter
from acquisition.factory import build_router

class Completed:
    returncode = 0
    stderr = ""
    stdout = "\n".join(json.dumps(item) for item in [
        {"tweet_id": "123", "tweet_content": "reference text", "post_url": "https://x.com/meg_lsm/status/123", "url": "https://cdn.example/1.jpg"},
        {"tweet_id": "123", "tweet_content": "reference text", "post_url": "https://x.com/meg_lsm/status/123", "url": "https://cdn.example/2.jpg"},
    ])

old_which = x_adapter.shutil.which
old_run = x_adapter.subprocess.run
x_adapter.shutil.which = lambda _: "/usr/bin/gallery-dl"
x_adapter.subprocess.run = lambda *args, **kwargs: Completed()
try:
    result = mod.fetch_x_account_posts({"x_read_only": True, "source_handle": "@meg_lsm"}, limit=10)
finally:
    x_adapter.shutil.which = old_which
    x_adapter.subprocess.run = old_run

row = result["rows"][0]
router = build_router()
checks = [
    ("fetched", result["status"] == "FETCHED"),
    ("individual status url", row["post_url"] == "https://x.com/meg_lsm/status/123"),
    ("external id", row["external_post_id"] == "123"),
    ("media order retained", row["media_urls"] == ["https://cdn.example/1.jpg", "https://cdn.example/2.jpg"]),
    ("shared router registered", router.routes["x.profile_posts"].primary == "x_gallery_dl"),
]
bad = [name for name, ok in checks if not ok]
for name, ok in checks: print(f"  {'PASS' if ok else 'FAIL'} {name}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
