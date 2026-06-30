#!/usr/bin/env python3
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("m", ROOT / "scripts/collect_threads_metrics.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
src = (ROOT / "scripts/collect_threads_metrics.py").read_text(encoding="utf-8")
checks = [
    ("browser engine arg", "--browser-engine" in src),
    ("storage state arg", "--storage-state" in src),
    ("playwright function", hasattr(m, "collect_playwright_threads_metrics")),
    ("unknowns null on missing url", all(v is None for v in m.collect_playwright_threads_metrics({"post_url": ""})[0].values())),
    ("no cookie print", "print(cookie" not in src.lower() and "print(token" not in src.lower()),
]
bad = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
