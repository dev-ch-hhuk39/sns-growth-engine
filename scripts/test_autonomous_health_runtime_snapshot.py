#!/usr/bin/env python3
"""Health diagnostics must inspect runtime counts without Sheets setup/write calls."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "scripts" / "check_autonomous_health.py").read_text(encoding="utf-8")

checks = [
    ("read-only Sheets runtime option exists", '"--use-sheets"' in SOURCE),
    ("runtime snapshot function exists", "def _sheets_runtime_snapshot" in SOURCE),
    ("queue and PDCA tabs are diagnosed", '"queue"' in SOURCE and '"pdca_runs"' in SOURCE and '"media_assets"' in SOURCE),
    ("runtime snapshot does not initialize Sheets", "client.setup_all()" not in SOURCE),
    ("runtime snapshot does not append rows", "append_row(" not in SOURCE),
]
failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(f"{'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(1 if failed else 0)
