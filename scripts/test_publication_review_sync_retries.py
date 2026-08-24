#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
text = (ROOT / "scripts" / "sync_publication_review.py").read_text(encoding="utf-8")

labels = {
    "get_all_records:queue:publication_review_sync",
    "get_all_records:publication_review:sync_existing",
    "row_values:publication_review:sync",
    "append_rows:publication_review:sync",
    "batch_update:publication_review:sync",
    "get_all_records:publication_review:sync_verify",
}
checks = [
    ("all production reads and writes use bounded retry", all(label in text for label in labels)),
    ("mock-compatible retry wrapper remains available", "def sheets_call(" in text),
    ("read-after-write remains mandatory", 'plan["read_after_write"]' in text),
]
failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
