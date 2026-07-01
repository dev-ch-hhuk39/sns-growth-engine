#!/usr/bin/env python3
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("video", ROOT / "scripts/collect_video_references.py")
video = importlib.util.module_from_spec(spec); spec.loader.exec_module(video)
yt = video.build_video_reference("https://www.youtube.com/watch?v=x", "night_scout", {})
tt = video.build_video_reference("https://www.tiktok.com/@u/video/123", "night_scout", {})
checks = [
    ("yt ref only", yt["rights_status"] == "third_party_reference_only" and yt["can_download"] is False),
    ("tt ref only", tt["rights_status"] == "third_party_reference_only" and tt["can_cut"] is False),
    ("analysis ok", yt["reference_analysis_allowed"] is True),
]
bad = [n for n, ok in checks if not ok]
for n, ok in checks: print(f"  {'PASS' if ok else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
