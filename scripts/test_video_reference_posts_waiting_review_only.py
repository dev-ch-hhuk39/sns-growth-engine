#!/usr/bin/env python3
from __future__ import annotations
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("generate_video_reference_posts", ROOT/"scripts/generate_video_reference_posts.py")
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
rows=mod.build_video_posts({"title":"sample","video_url":"u"},"night_scout",3)
ok=all(r["status"]=="WAITING_REVIEW" for r in rows)
print(f"  {'PASS' if ok else 'FAIL'} video waiting review only"); print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
raise SystemExit(0 if ok else 1)
