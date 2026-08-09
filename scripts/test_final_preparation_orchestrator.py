#!/usr/bin/env python3
from pathlib import Path

root=Path(__file__).resolve().parents[1]
text=(root/"scripts/run_final_production_preparation.py").read_text()
assert '"--platform", "x"' in text
assert "--confirm-production-preparation" in text
assert "would_download\": False" in text and "would_post\": False" in text
assert (root/"docs/manual-source-import-template.json").exists()
print("PASS test_final_preparation_orchestrator.py")
