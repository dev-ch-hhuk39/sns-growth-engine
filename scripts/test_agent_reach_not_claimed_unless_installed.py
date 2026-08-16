#!/usr/bin/env python3
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
doc = (ROOT / "docs/dependency-inventory.md").read_text(encoding="utf-8")
installed = shutil.which("agent-reach") is not None or (
    Path.home() / ".agent-reach-venv" / "bin" / "agent-reach"
).is_file()
installation_claim_is_scoped = (
    "Installation is environment-local evidence, not a portable repository guarantee." in doc
)
checks = [
    ("agent reach documented", "Agent Reach Clarification" in doc),
    ("not in requirements", "agent-reach" not in (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()),
    ("installation claim has binary evidence or environment scope", installed or installation_claim_is_scoped),
    ("not direct generation", "must not directly generate SNS post body copy" in doc),
]
bad = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
