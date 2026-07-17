#!/usr/bin/env python3
import inspect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import transcribe_approved_source_videos as module  # noqa: E402

source = inspect.getsource(module.transcribe_with_local_whisper)
normalize_source = inspect.getsource(module._normalize_audio_for_whisper)
config = json.loads((ROOT / "config/media_growth_engine.json").read_text(encoding="utf-8"))
workflows = [
    (ROOT / ".github/workflows/media-growth-production.yml").read_text(encoding="utf-8"),
    (ROOT / ".github/workflows/media-growth-production-night-scout.yml").read_text(encoding="utf-8"),
    (ROOT / ".github/workflows/media-transcription-production.yml").read_text(encoding="utf-8"),
]

checks = [
    ("audio normalized to mono 16k", '"-ac", "1", "-ar", "16000"' in normalize_source),
    ("audio duration bounded", '"-t", str(max_audio_seconds)' in normalize_source),
    ("Whisper int8 CPU", 'compute_type="int8"' in source and 'device="cpu"' in source),
    ("Whisper one worker", "num_workers=1" in source),
    ("Whisper CPU threads bounded", "cpu_threads=cpu_threads" in source),
    ("greedy beam reduces memory", "beam_size=1" in source),
    ("one transcription per run", config.get("max_transcriptions_per_run") == 1),
    ("15 minute source window", config.get("max_local_transcription_seconds_per_video") == 900),
    ("production workflows use one thread and one video", all("--limit 1" in wf and "--cpu-threads 1" in wf for wf in workflows)),
]
failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
