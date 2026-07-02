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
    for rows in plan["selected_pilot_sources"].values():
        for row in rows:
            if row["source_platform"] == "youtube":
                row["source_url"] = "not-a-real-url"
    analysis = mod.build_video_reference_analysis(plan, mod.load_autonomous_config(), fetch_metadata=True)
    ok = analysis["text_only_post_idea_count"] == 0 and any(s["reason"] == "metadata_unavailable" for s in analysis["skipped"])
    print(f"  {'PASS' if ok else 'FAIL'} unavailable metadata blocks video idea")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
