#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("run_autonomous_loop", ROOT / "scripts/run_autonomous_loop.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def main() -> int:
    analysis = mod.build_autonomous_plan("all")["video_reference_analysis"]
    ok = all(not r["can_download"] and not r["can_cut"] and not r["can_upload"] for r in analysis["rows"]) and analysis["safety"]["download"] is False
    print(f"  {'PASS' if ok else 'FAIL'} autonomous video no download")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
