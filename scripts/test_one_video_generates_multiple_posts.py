#!/usr/bin/env python3
from __future__ import annotations
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("generate_video_reference_posts", ROOT/"scripts/generate_video_reference_posts.py")
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
rows=mod.build_video_posts({"title":"sample"},"liver_manager",5)
ok=len(rows)==5 and len({r["text"] for r in rows})==5
print(f"  {'PASS' if ok else 'FAIL'} one video multiple posts"); print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
raise SystemExit(0 if ok else 1)
