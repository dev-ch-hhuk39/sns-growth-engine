#!/usr/bin/env python3
from pathlib import Path

text = Path(__file__).with_name("ensure_activation_evidence_schema.py").read_text(encoding="utf-8")
schema = (Path(__file__).resolve().parents[1] / "src/sheets_client.py").read_text(encoding="utf-8")
assert '"metrics_collection_jobs": [' in schema
assert '"posted_results": [' in schema
assert "--confirm-schema" in text
assert "_ensure_tab" in text
assert "read_after_write" in text
assert "would_delete" in text
print("PASS")
