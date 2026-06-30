#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
src=(ROOT/"scripts/transcribe_video_reference.py").read_text()
ok="confirm_transcribe" in src and "ALLOW_TRANSCRIPTION_API" in src
print(f"  {'PASS' if ok else 'FAIL'} transcription confirm gate"); print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
raise SystemExit(0 if ok else 1)
