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
    ("all reads have bounded retry labels", all(label in text for label in labels)),
    ("mock-compatible read retry wrapper remains", "def sheets_call(" in text),
    ("non-idempotent writes have no automatic retry", 'sheets_write_once(' in text
        and 'value_input_option="RAW"' in text),
    ("no accidental worksheet creation during plan/apply", "._ensure_tab(" not in text),
    ("read-after-write compares exact contents", 'plan["read_after_write"] = True' in text
        and "review_sync_readback_mismatch_manual_reconciliation" in text),
]
failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
