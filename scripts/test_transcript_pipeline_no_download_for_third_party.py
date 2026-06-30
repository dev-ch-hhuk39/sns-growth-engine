#!/usr/bin/env python3
from pathlib import Path
trans=(Path(__file__).resolve().parents[1]/"scripts/transcribe_video_reference.py").read_text(encoding="utf-8")
collect=(Path(__file__).resolve().parents[1]/"scripts/collect_video_references.py").read_text(encoding="utf-8")
checks=[("api gate", "ALLOW_TRANSCRIPTION_API" in trans), ("download false", '"can_download": False' in collect), ("third party rights", "third_party_reference_only" in collect)]
bad=[n for n,o in checks if not o]
for n,o in checks: print(f"  {'PASS' if o else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
