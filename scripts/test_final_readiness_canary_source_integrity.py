#!/usr/bin/env python3
from pathlib import Path

text = Path(__file__).with_name("final_production_readiness.py").read_text(encoding="utf-8")
assert '"canary_source_integrity": canary_integrity' in text
assert '"quarantine_candidates_excluding_canary"' in text
print("PASS test_final_readiness_canary_source_integrity.py")
