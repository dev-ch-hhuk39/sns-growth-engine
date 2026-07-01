#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
runbook = (ROOT / "docs/production-pilot-runbook.md").read_text(encoding="utf-8")
workflow = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / ".github/workflows").glob("*.yml"))
checks = [
    ("runbook says off", "AUTOPOST remains OFF" in runbook or "AUTOPOST must stay OFF" in runbook),
    ("workflow publish false", 'PUBLISH_ENABLED: "false"' in workflow),
    ("real threads false", 'ALLOW_REAL_THREADS_POST: "false"' in workflow),
]
bad = [n for n, ok in checks if not ok]
for n, ok in checks: print(f"  {'PASS' if ok else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
