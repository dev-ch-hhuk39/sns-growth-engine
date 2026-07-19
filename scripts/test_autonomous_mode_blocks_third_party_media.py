#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("run_autonomous_loop", ROOT / "scripts/run_autonomous_loop.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def main() -> int:
    cfg = json.loads((ROOT / "config/autonomous_mode.json").read_text(encoding="utf-8"))
    plan = mod.build_autonomous_plan("all", cfg)
    selected = [row for rows in plan["selected_pilot_sources"].values() for row in rows]
    unauthorized = [
        row for row in selected
        if row.get("media_pipeline_eligible_after_apply")
        and row.get("rights_status") not in {"owned", "licensed", "approved_creator_clip"}
    ]
    ok = cfg.get("allow_third_party_media") is False and not unauthorized and plan["safety"]["third_party_media"] is False
    print(f"  {'PASS' if ok else 'FAIL'} third-party media blocked")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
