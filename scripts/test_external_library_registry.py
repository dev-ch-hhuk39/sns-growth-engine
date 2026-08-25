#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
data = json.loads((ROOT / "config/external_libraries.json").read_text(encoding="utf-8"))
rows = {row["id"]: row for row in data["libraries"]}
required = {
    "agent_reach", "last30days_skill", "yt_dlp", "bgutil_ytdlp_pot_provider", "tiktok_to_ytdlp",
    "youtube_transcript_api", "youtube_comment_downloader", "faster_whisper",
    "ffmpeg", "threads_scraper_vdite", "threads_scraper_zeeshan",
    "threads_comment_scraper_galihkjaya", "hasdata_tiktok", "firecrawl",
    "moneyprinterturbo", "vimax", "voxcpm", "liveportrait",
}
checks = [
    ("all requested libraries are inventoried", required.issubset(rows)),
    ("every Git repository has an exact revision", all(row.get("revision") for row in rows.values())),
    ("no library adds a mandatory paid service", data["policy"]["mandatory_paid_service_allowed"] is False),
    ("unlicensed HasData code is not installed", rows["hasdata_tiktok"]["install"] == "not_installed"),
    (
        "YouTube PO provider is revision and dependency pinned",
        rows["bgutil_ytdlp_pot_provider"]["revision"] == "7511309af023b09788dc8f2efc96cc3671291e6c"
        and rows["bgutil_ytdlp_pot_provider"]["license"] == "GPL-3.0-or-later",
    ),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
failed = [name for name, ok in checks if not ok]
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
