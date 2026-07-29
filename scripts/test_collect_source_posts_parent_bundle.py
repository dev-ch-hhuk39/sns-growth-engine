#!/usr/bin/env python3
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; path=ROOT/"scripts/collect_source_posts.py"
spec=importlib.util.spec_from_file_location("collect", path); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
parent,children=mod.source_post_bundle({"post_id":"42","external_post_id":"42","source_id":"src","account_id":"liver_manager","source_platform":"threads","source_handle":"@me01_lsm","post_url":"https://www.threads.com/@me01_lsm/post/abc","post_text":"text","published_at":"2026-07-29T00:00:00Z","media_urls":"[\"https://cdn.example/1.jpg\", \"https://cdn.example/2.jpg\"]","collected_at":"2026-07-29T01:00:00Z"})
checks=[("parent is individual",parent["canonical_post_url"].endswith("/post/abc")),("external id retained",parent["external_post_id"]=="42"),("two ordered children",[item["media_index"] for item in children]==["0","1"]),("same parent",all(item["source_post_id"]==parent["source_post_id"] for item in children))]
bad=[n for n,o in checks if not o]
for n,o in checks: print(f"  {'PASS' if o else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
