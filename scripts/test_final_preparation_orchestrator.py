#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

root=Path(__file__).resolve().parents[1]
text=(root/"scripts/run_final_production_preparation.py").read_text()
assert '"--platform", "x"' in text
assert "--confirm-production-preparation" in text
assert "would_download\": False" in text and "would_post\": False" in text
assert (root/"docs/manual-source-import-template.json").exists()
completed = subprocess.run(
    [sys.executable, str(root / "scripts/run_final_production_preparation.py"), "--help"],
    cwd=root,
    capture_output=True,
    text=True,
    check=False,
)
assert completed.returncode == 0, completed.stderr
print("PASS test_final_preparation_orchestrator.py")
