#!/usr/bin/env python3
from pathlib import Path

text = Path(__file__).with_name("final_production_readiness.py").read_text(encoding="utf-8")
assert '"evidence_source": "READ_OK"' in text
assert '"evidence_source": "SCHEMA_MISSING"' in text
print("PASS")
