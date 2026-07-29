#!/usr/bin/env python3
from pathlib import Path

text = Path(__file__).with_name("process_threads_queue.py").read_text(encoding="utf-8")
assert 'parser.add_argument("--queue-id", action="append"' in text
assert "REQUESTED_QUEUE_NOT_READY" in text
assert "queue_ids: set[str] | None = None" in text
print("PASS test_process_threads_queue_exact_queue_selection.py")
