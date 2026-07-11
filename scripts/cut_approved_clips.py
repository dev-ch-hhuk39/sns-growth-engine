#!/usr/bin/env python3
"""Cut only owned/licensed/approved clips with ffmpeg gates."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from media.rights_policy import build_rights_decision


def _load_clip_candidates(path: str) -> list[dict]:
    if not path:
        path = str(ROOT / "output/source_videos/video_clip_candidates.json")
    candidate = Path(path)
    if not candidate.exists():
        return []
    return json.loads(candidate.read_text(encoding="utf-8"))


def _resolve_clip_candidate(args: argparse.Namespace) -> dict:
    injected = getattr(args, "clip_candidate_row", None)
    if isinstance(injected, dict):
        return dict(injected)
    clip_id = getattr(args, "clip_candidate_id", "")
    if not clip_id:
        return {}
    for row in _load_clip_candidates(getattr(args, "clip_candidates_json", "")):
        if str(row.get("clip_candidate_id") or row.get("clip_id")) == str(clip_id):
            return dict(row)
    return {}


def build_plan(args: argparse.Namespace) -> dict:
    clip_candidate = _resolve_clip_candidate(args)
    if clip_candidate:
        args.rights_status = clip_candidate.get("rights_status") or args.rights_status
        args.input_path = clip_candidate.get("local_path") or clip_candidate.get("local_clip_path") or args.input_path
        args.start_seconds = float(clip_candidate.get("start_seconds") or clip_candidate.get("start_time") or args.start_seconds or 0)
        args.end_seconds = float(clip_candidate.get("end_seconds") or clip_candidate.get("end_time") or args.end_seconds or 0)
    allowed_env = os.environ.get("ALLOW_VIDEO_CUT", "").lower() == "true"
    decision = build_rights_decision(args.rights_status, action="cut")
    ffmpeg_cli = shutil.which("ffmpeg") is not None
    ffmpeg_python = importlib.util.find_spec("ffmpeg") is not None
    start_seconds = float(getattr(args, "start_seconds", 0) or 0)
    end_seconds = float(getattr(args, "end_seconds", 0) or 0)
    blocked = []
    if getattr(args, "clip_candidate_id", "") and not clip_candidate:
        blocked.append("clip_candidate_id_not_found")
    if not decision.allowed:
        blocked.append(decision.reason)
    if clip_candidate and not args.input_path:
        blocked.append("downloaded_media_required")
    if str(clip_candidate.get("cut_status", "")).upper() in {"CUT", "DONE"}:
        blocked.append("already_cut")
    if args.cut and not args.confirm_cut:
        blocked.append("--cut requires --confirm-cut")
    if args.cut and not allowed_env:
        blocked.append("ALLOW_VIDEO_CUT=true is required")
    if args.cut and not args.input_path:
        blocked.append("input_path is required")
    if args.cut and end_seconds <= start_seconds:
        blocked.append("end_seconds must be greater than start_seconds")
    if args.cut and not ffmpeg_cli:
        blocked.append("ffmpeg CLI is not installed")
    clip_id = str(getattr(args, "clip_candidate_id", "") or clip_candidate.get("clip_id") or datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"))
    safe_clip_id = "".join(c if c.isalnum() or c in "_-" else "_" for c in clip_id)[:140]
    output_path = str(ROOT / "output" / "clips" / f"{safe_clip_id}.mp4")
    return {
        "status": "READY" if args.cut and not blocked else "BLOCKED" if blocked else "PLAN_ONLY",
        "adapter_status": {
            "ffmpeg_cli": "installed" if ffmpeg_cli else "not_installed",
            "ffmpeg_python": "installed" if ffmpeg_python else "not_installed",
        },
        "rights_status": decision.rights_status,
        "clip_candidate_id": getattr(args, "clip_candidate_id", ""),
        "source_video_id": clip_candidate.get("source_video_id", ""),
        "rights_decision": decision.as_dict(),
        "input_path": args.input_path,
        "start_seconds": start_seconds,
        "end_seconds": end_seconds,
        "duration_seconds": max(0, end_seconds - start_seconds),
        "output_path": output_path,
        "ffmpeg_cut": bool(args.cut and not blocked),
        "would_cut": bool(args.cut and not blocked),
        "blocked_reasons": blocked,
        "vertical_9x16": args.vertical,
        "burn_subtitles": args.burn_subtitles,
        "media_asset_result": {
            "media_asset_id": "",
            "local_path": output_path,
            "media_type": "video",
            "rights_status": decision.rights_status,
            "status": "WAITING_REVIEW",
            "upload_status": "NOT_UPLOADED",
        } if decision.allowed else None,
    }


def execute_cut(plan: dict) -> dict:
    if plan.get("status") != "READY" or not plan.get("would_cut"):
        return plan
    output_path = Path(str(plan["output_path"]))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    duration = float(plan.get("duration_seconds") or 0)
    cmd = [
        "ffmpeg", "-y", "-ss", str(plan["start_seconds"]),
        "-i", str(plan["input_path"]), "-t", str(duration),
    ]
    if plan.get("vertical_9x16"):
        cmd += ["-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "21", "-c:a", "aac", "-movflags", "+faststart", str(output_path)]
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)
        if completed.returncode != 0 or not output_path.exists():
            return {**plan, "status": "FAILED", "would_cut": False, "blocked_reasons": ["ffmpeg_cut_failed"]}
        media_asset = dict(plan.get("media_asset_result") or {})
        media_asset.update({
            "media_asset_id": f"ma_{plan.get('clip_candidate_id') or output_path.stem}",
            "local_path": str(output_path),
            "status": "APPROVED",
            "upload_status": "NOT_UPLOADED",
            "aspect_ratio": "9:16" if plan.get("vertical_9x16") else "source",
            "duration_seconds": duration,
        })
        return {**plan, "status": "CUT", "would_cut": False, "media_asset_result": media_asset}
    except Exception as exc:  # noqa: BLE001
        return {**plan, "status": "FAILED", "would_cut": False, "blocked_reasons": [f"{type(exc).__name__}: ffmpeg_cut_failed"]}


def main() -> int:
    parser = argparse.ArgumentParser(description="cut approved clips")
    parser.add_argument("--input-path", default="")
    parser.add_argument("--clip-candidate-id", default="")
    parser.add_argument("--clip-candidates-json", default="")
    parser.add_argument("--rights-status", default="third_party_reference_only")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--cut", action="store_true")
    parser.add_argument("--confirm-cut", action="store_true")
    parser.add_argument("--start-seconds", type=float, default=0)
    parser.add_argument("--end-seconds", type=float, default=0)
    parser.add_argument("--vertical", action="store_true")
    parser.add_argument("--burn-subtitles", action="store_true")
    args = parser.parse_args()
    plan = build_plan(args)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    if plan["status"] == "BLOCKED":
        return 1
    if plan["status"] != "READY":
        return 0
    if args.dry_run:
        return 0
    result = execute_cut(plan)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "CUT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
