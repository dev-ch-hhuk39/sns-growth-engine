#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from sheets_client import TAB_DEFINITIONS

text = Path(__file__).with_name("ensure_activation_evidence_schema.py").read_text(encoding="utf-8")
assert "metrics_collection_jobs" in TAB_DEFINITIONS
assert "posted_results" in TAB_DEFINITIONS
assert "--confirm-schema" in text
assert "_ensure_tab" in text
assert "read_after_write" in text
assert "would_delete" in text
print("PASS")
