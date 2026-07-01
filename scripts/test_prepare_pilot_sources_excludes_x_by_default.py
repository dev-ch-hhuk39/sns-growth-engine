#!/usr/bin/env python3
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pilot", ROOT / "scripts/prepare_pilot_sources.py")
pilot = importlib.util.module_from_spec(spec); spec.loader.exec_module(pilot)
plan = pilot.select_pilot_sources(pilot.load_sources()["sources"], account_id="all", max_per_account=2, platform="all")
platforms = {row["source_platform"] for rows in plan["selected"].values() for row in rows}
checks = [("x excluded", "x" not in platforms), ("safety x false", plan["safety"]["x_fetch"] is False)]
bad = [n for n, ok in checks if not ok]
for n, ok in checks: print(f"  {'PASS' if ok else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
