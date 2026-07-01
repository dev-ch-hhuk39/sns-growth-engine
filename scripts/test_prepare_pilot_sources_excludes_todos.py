#!/usr/bin/env python3
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pilot", ROOT / "scripts/prepare_pilot_sources.py")
pilot = importlib.util.module_from_spec(spec); spec.loader.exec_module(pilot)
sources = pilot.load_sources()["sources"]
plan = pilot.select_pilot_sources(sources, account_id="all", max_per_account=2, platform="all")
ids = {row["source_id"] for rows in plan["selected"].values() for row in rows}
checks = [("no todo selected", not any(i.endswith("_todo") or i == "owned_media_assets_todo" for i in ids))]
bad = [n for n, ok in checks if not ok]
for n, ok in checks: print(f"  {'PASS' if ok else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
