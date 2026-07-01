#!/usr/bin/env python3
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("collect", ROOT / "scripts/collect_source_posts.py")
collect = importlib.util.module_from_spec(spec); spec.loader.exec_module(collect)
src = {"source_id": "s", "source_platform": "threads", "target_account_ids": ["night_scout"], "url": "https://threads.com/@u/post/x"}
row = collect.normalize_source(src, {"ok": True, "thumbnail_url": "https://cdn.example/img.jpg", "text": "sample"})
checks = [("rights", row["rights_status"] == "third_party_reference_only"), ("no reuse", row["can_reuse_media"] == "false"), ("no body save", row["media_body_saved"] == "false")]
bad = [n for n, ok in checks if not ok]
for n, ok in checks: print(f"  {'PASS' if ok else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
