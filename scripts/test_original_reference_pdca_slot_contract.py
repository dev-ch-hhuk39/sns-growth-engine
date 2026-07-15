#!/usr/bin/env python3
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
text = (ROOT / "scripts/generate_threads_ideas_from_references.py").read_text()
assert 'post_type == "original_text"' in text
assert 'post_type == "pdca_text" and not measured' in text
assert '"measured_metric_count"' in text
print("PASS test_original_reference_pdca_slot_contract.py")
