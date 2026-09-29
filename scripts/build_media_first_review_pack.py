#!/usr/bin/env python3
"""Read-only historical preview sampling. Never import Sheets or a publisher."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from media.direct_content_understanding import representative_frames, vision_summary  # noqa: E402


def selected_previews(document: str) -> list[dict[str, str]]:
    selected = []
    account = ""
    counts: dict[str, int] = {}
    for line in document.splitlines():
        match = re.match(r"## (night_scout|liver_manager|beauty_account).*media packages", line)
        if match:
            account = match[1]
        asset = re.match(r"- Asset: `([^`]+)`.*preview: \[[^]]+\]\((https://[^)]+)\)", line)
        if asset and account and counts.get(account, 0) < 2:
            selected.append({"account_id": account, "media_asset_id": asset[1], "preview_url": asset[2]})
            counts[account] = counts.get(account, 0) + 1
    return selected


def inspect_preview(row: dict[str, str], directory: Path) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    url = row["preview_url"]
    if urlsplit(url).hostname != "res.cloudinary.com" or urlsplit(url).scheme != "https":
        return {**row, "status": "BLOCKED_PREVIEW_HOST"}
    target = directory / "preview.mp4"
    try:
        with requests.get(url, stream=True, timeout=(10, 25), allow_redirects=False) as response:
            response.raise_for_status()
            if response.status_code != 200:
                raise ValueError("redirect_or_partial_preview")
            size = 0
            with target.open("wb") as handle:
                for block in response.iter_content(1024 * 1024):
                    size += len(block)
                    if size > 64 * 1024 * 1024:
                        raise ValueError("preview_size_limit")
                    handle.write(block)
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(target)],
                               capture_output=True, text=True, timeout=15, check=True)
        details = json.loads(probe.stdout)
        if not any(stream.get("codec_type") == "video" for stream in details.get("streams", [])):
            raise ValueError("video_stream_missing")
        frames = representative_frames(target, float(details["format"]["duration"]), directory)
        vision = vision_summary([path for _, path in frames], media_type="video",
                                source_metadata=row, transcript={"status": "UNAVAILABLE"})
        with target.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        return {**row, "status": "PREVIEW_READ_OK", "content_hash": digest,
                "frames": [{"timestamp": timestamp, "path": str(path.resolve()),
                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for timestamp, path in frames],
                "vision": vision, "rights_status": "UNVERIFIED", "permission_status": "UNVERIFIED"}
    except (requests.RequestException, subprocess.SubprocessError, OSError, ValueError, KeyError) as exc:
        return {**row, "status": "PREVIEW_UNAVAILABLE", "error_class": type(exc).__name__}


def render(rows: list[dict]) -> str:
    lines = ["# Content Quality V2 Media-First Review", "",
             "Draft only. Existing previews are read-only; no production writes or uploads.",
             "Historical preview links do not establish current rights. Captions are withheld without verified visual evidence and permission.",
             "MEDIA_FIRST_QUALITY_PROVEN=NO", ""]
    for row in rows:
        vision = row.get("vision", {})
        lines += [f"## {row['account_id']} / {row['media_asset_id']}", "",
                  f"MEDIA_PREVIEW: [video]({row['preview_url']})", f"FETCH_STATUS: {row['status']}",
                  "REPRESENTATIVE_FRAME_EVIDENCE:"]
        for frame in row.get("frames", []):
            lines += [f"- {frame['timestamp']}s; SHA256 `{frame['sha256']}`", f"![Frame]({frame['path']})"]
        verified = vision.get("status") == "PASS" and bool(vision.get("visual_summary"))
        lines += [f"VISUAL_STATUS: {'VISUAL_VERIFIED' if verified else 'VISUAL_UNVERIFIED'}",
                  f"VISUAL_SUMMARY: {vision.get('visual_summary') or 'UNVERIFIED'}",
                  f"WHAT_VIEWER_SEES: {vision.get('visual_summary') or 'UNVERIFIED'}",
                  "WHAT_VIEWER_HEARS: AUDIO_UNVERIFIED",
                  "WHY_THIS_ACCOUNT_SHOULD_POST_THIS: UNVERIFIED",
                  "POST_ANGLE_OPTIONS: NOT_GENERATED", "SELECTED_ANGLE: NONE", "MEDIA_ANCHOR: UNVERIFIED",
                  "PUBLIC_CAPTION: NOT_GENERATED", "REMOVE_MEDIA_TEST: NOT_RUN",
                  "FABRICATED_EXPERIENCE_CHECK: NOT_RUN", "RIGHTS/PERMISSION_STATUS: UNVERIFIED / UNVERIFIED",
                  "QUALITY_RANK: NOT_RANKED",
                  f"WARNINGS: {vision.get('failure_class', row.get('error_class', 'permission evidence unavailable'))}", ""]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/CONTENT_QUALITY_V2_MEDIA_FIRST_REVIEW.md")
    args = parser.parse_args()
    os.environ["BUFFERED_POSTING_ENABLED"] = "false"
    previews = selected_previews((ROOT / "docs/CONTENT_QUALITY_V2_REVIEW_PACK.md").read_text())
    rows = [inspect_preview(row, args.artifact_dir / row["media_asset_id"]) for row in previews]
    args.output.write_text(render(rows), encoding="utf-8")
    print(json.dumps({"previews": len(rows), "frames": sum(len(row.get("frames", [])) for row in rows),
                      "vision_verified": sum(row.get("vision", {}).get("status") == "PASS" for row in rows),
                      "caption_count": 0, "production_writes": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
