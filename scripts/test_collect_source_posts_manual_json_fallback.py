#!/usr/bin/env python3
"""Manual/browser fallback accepts only individual posts and preserves order."""
from __future__ import annotations
import importlib.util
import json
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; path=ROOT/"scripts/collect_source_posts.py"
spec=importlib.util.spec_from_file_location("collect", path); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
with tempfile.TemporaryDirectory() as directory:
    fixture=Path(directory)/"export.json"
    fixture.write_text(json.dumps({"posts":[
        {"post_url":"https://x.com/meg_lsm/status/1?ref=x","post_id":"1","text":"one","published_at":"2026-07-29T00:00:00Z","media_urls":["https://cdn.example/1.jpg","https://cdn.example/2.jpg"]},
        {"post_url":"https://x.com/meg_lsm","post_id":"profile","text":"ignore"},
    ]}),encoding="utf-8")
    rows,reason=mod.load_manual_export(str(fixture),platform="x")
checks=[("valid export",not reason), ("profile excluded",len(rows)==1), ("canonical url",rows and rows[0]["post_url"]=="https://x.com/meg_lsm/status/1"), ("media order",rows and rows[0]["media_urls"][1]=="https://cdn.example/2.jpg")]
bad=[n for n,o in checks if not o]
for n,o in checks: print(f"  {'PASS' if o else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
