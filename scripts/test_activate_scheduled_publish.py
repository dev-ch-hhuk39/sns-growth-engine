#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

root=Path(__file__).resolve().parents[1]
result=subprocess.run([sys.executable, "scripts/activate_scheduled_publish.py", "--apply", "--confirm-scheduled-activation", "--use-sheets"], cwd=root, text=True, stdout=subprocess.PIPE, check=False)
assert result.returncode == 1
assert "BLOCKED" in result.stdout
print("PASS test_activate_scheduled_publish.py")
