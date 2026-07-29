#!/usr/bin/env python3
"""Threads account roots must discover posts, never become source posts."""
import importlib.util
from pathlib import Path

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("collector", root / "scripts/collect_source_posts.py")
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

checks = [
    ("account is not post", not mod.is_individual_post_url("https://www.threads.com/@me01_lsm", "threads")),
    ("post is individual", mod.is_individual_post_url("https://www.threads.com/@me01_lsm/post/AbC_123", "threads")),
    ("x profile is not post", not mod.is_individual_post_url("https://x.com/meg_lsm", "x")),
]
bad = [name for name, ok in checks if not ok]
for name, ok in checks: print(f"  {'PASS' if ok else 'FAIL'} {name}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
