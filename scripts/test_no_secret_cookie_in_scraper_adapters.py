#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
files = ["scripts/collect_threads_metrics.py", "scripts/collect_source_posts.py", "scripts/collect_video_references.py"]
combined = "\n".join((ROOT / f).read_text(encoding="utf-8") for f in files)
checks = [
    ("redaction exists", "REDACTED" in combined),
    ("no token print", "print(token" not in combined.lower()),
    ("no cookie print", "print(cookie" not in combined.lower()),
    ("storage state contents not read", ".read_text" not in (ROOT / "scripts/collect_threads_metrics.py").read_text(encoding="utf-8")),
]
bad = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
