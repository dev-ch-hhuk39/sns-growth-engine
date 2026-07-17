#!/usr/bin/env python3
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
from run_media_growth_engine import build_media_growth_plan

plan = build_media_growth_plan("liver_manager", existing_source_videos=[], existing_transcripts=[])
checks = {"no synthetic source videos": plan["source_video_count"] == 0,
          "no synthetic clip candidates": plan["clip_candidate_count"] == 0,
          "discovery required": plan["source_videos_source"] == "none_discover_first"}
for name, ok in checks.items(): print(f"{'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(checks.values()) else 1)
