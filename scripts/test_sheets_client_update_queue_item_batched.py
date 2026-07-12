#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
text = (ROOT / "src" / "sheets_client.py").read_text(encoding="utf-8")

start = text.index("    def update_queue_item(self, queue_id: str, **fields: Any) -> None:")
end = text.index("    def get_prompt_templates(", start)
body = text[start:end]

checks = [
    ("SheetsClient has rate limit retry helper", "def _call_with_rate_limit_retry" in text),
    ("SheetsClient has batch update helper", "def _batch_update_fields" in text),
    ("update_queue_item retries row_values", "row_values:queue" in body),
    ("update_queue_item retries find", "_call_with_rate_limit_retry(" in body and "find:queue" in body),
    ("update_queue_item uses batch update helper", "_batch_update_fields(" in body),
    ("update_queue_item does not use update_cell", "update_cell(" not in body),
]

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
