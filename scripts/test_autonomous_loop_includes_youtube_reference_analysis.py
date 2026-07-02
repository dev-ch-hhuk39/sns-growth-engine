#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("run_autonomous_loop", ROOT / "scripts/run_autonomous_loop.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def main() -> int:
    plan = mod.build_autonomous_plan("all")
    analysis = plan["video_reference_analysis"]
    rows = analysis["rows"]
    ok = analysis["status"] == "CONNECTED" and any(r["platform"] == "youtube" and r["source_id"] == "src_lm_yt_cand_001" for r in rows)
    print(f"  {'PASS' if ok else 'FAIL'} youtube reference analysis connected")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
