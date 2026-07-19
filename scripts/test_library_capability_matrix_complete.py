#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
matrix = json.loads((ROOT / "docs/library-capability-matrix.json").read_text(encoding="utf-8"))
text = json.dumps(matrix, ensure_ascii=False)
rows = {row["id"]: row for row in matrix["libraries"]}
required = {
    "agent_reach",
    "last30days_skill",
    "yt_dlp",
    "youtube_transcript_api",
    "youtube_comment_downloader",
    "faster_whisper",
    "ffmpeg",
    "threads_public_playwright",
    "threads_public_http",
    "tiktok_public_playwright",
    "firecrawl",
}
checks = [
    ("no unresolved audit placeholders", "AUDIT_PENDING" not in text and "UNVERIFIED" not in text),
    ("required capability rows", required <= set(rows)),
    ("Agent-Reach exact SHA", rows["agent_reach"]["pinned_revision"] == "1494c2ab239e7355a77e7cceaf3271453a1f34b5"),
    ("last30days exact SHA", rows["last30days_skill"]["pinned_revision"] == "249c7a4c040558a903d6838dee31012980d4946d"),
    ("yt-dlp exact package pin", rows["yt_dlp"]["pinned_version"] == "2026.7.4"),
    ("automatic upgrades disabled", matrix["policy"]["automatic_dependency_upgrade"] is False),
    ("standard hosted runner", matrix["policy"]["production_runner"] == "ubuntu-latest"),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(ok for _, ok in checks) else 1)
