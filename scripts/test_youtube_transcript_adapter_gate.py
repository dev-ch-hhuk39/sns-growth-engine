#!/usr/bin/env python3
"""Offline CLI contract; external YouTube availability is not a CI prerequisite.

Mock the official-transcript adapter at the import boundary. This proves
plan-only/no-download/no-preview and structured output without any network.
"""
from __future__ import annotations

import contextlib
import importlib.machinery
import io
import json
import sys
import types
from unittest.mock import patch

import transcribe_video_reference as cli


class FakeTranscriptApi:
    def fetch(self, video_id: str, languages: list[str]):
        assert video_id == "dQw4w9WgXcQ"
        assert languages == ["ja", "en"]
        return [{"text": "PRIVATE_UT_TRANSCRIPT_LINE", "duration": 2}]


fake = types.ModuleType("youtube_transcript_api")
fake.__spec__ = importlib.machinery.ModuleSpec("youtube_transcript_api", loader=None)
fake.YouTubeTranscriptApi = FakeTranscriptApi
buf = io.StringIO()
args = [
    "transcribe_video_reference.py",
    "--account-id", "night_scout",
    "--video-url", "https://youtu.be/dQw4w9WgXcQ",
    "--fetch-youtube-transcript",
]
with patch.dict(sys.modules, {"youtube_transcript_api": fake}), patch.object(
    sys, "argv", args
), contextlib.redirect_stdout(buf):
    exit_code = cli.main()

result = json.loads(buf.getvalue())
transcripts = result.get("transcripts", [])
checks = [
    ("cli returns zero", exit_code == 0),
    ("plan only", result.get("status") == "PLAN_ONLY"),
    ("no real transcription api", result.get("real_transcription_api") is False),
    ("no download", result.get("download") is False),
    ("adapter installed via fake", result["adapter_status"]["youtube_transcript_api"] == "installed"),
    ("fake adapter fetched 1 chunk", len(transcripts) == 1 and transcripts[0].get("chunk_count") == 1),
    ("no transcript preview", all(t.get("text_preview", "") == "" for t in transcripts)),
    ("no private text printed", "PRIVATE_UT_TRANSCRIPT_LINE" not in buf.getvalue()),
]
fail = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(("PASS " if ok else "FAIL ") + name)
print(f"PASS: {len(checks)-len(fail)} / FAIL: {len(fail)}")
raise SystemExit(1 if fail else 0)
