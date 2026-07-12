#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
text = (ROOT / "scripts" / "run_autonomous_loop.py").read_text(encoding="utf-8")

checks = [
    ("optional failures marked non_blocking", 'results[-1]["non_blocking"] = True' in text),
    ("optional failures get WARN status", 'results[-1]["status"] = "WARN_NON_BLOCKING"' in text),
    (
        "failed_results excludes non_blocking",
        'and not r.get("non_blocking")' in text and "failed_results = [" in text,
    ),
    (
        "health save excludes non_blocking errors",
        'if r.get("returncode") not in {0, None} and not r.get("non_blocking")' in text,
    ),
]

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
