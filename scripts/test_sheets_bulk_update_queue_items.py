#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
text = (ROOT / "src" / "sheets_client.py").read_text(encoding="utf-8")
start = text.index("    def bulk_update_queue_items(")
end = text.index("    def get_prompt_templates(", start)
body = text[start:end]

checks = [
    ("bulk queue update method exists", "def bulk_update_queue_items" in body),
    ("reads queue grid once", "get_all_values:queue" in body),
    ("does not find each queue id", "ws.find(" not in body),
    ("uses Sheets batch update", "ws.batch_update" in body),
    ("bounds batch payload size", "range(0, len(ranges), 400)" in body),
    ("uses rate-limit retry", "_call_with_rate_limit_retry" in body),
]

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
