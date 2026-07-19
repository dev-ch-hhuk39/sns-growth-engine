#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from media.rights_policy import rights_allows_media_use, rights_allows_reference_analysis

trans=(ROOT/"scripts/transcribe_video_reference.py").read_text(encoding="utf-8")
collect=(ROOT/"scripts/collect_video_references.py").read_text(encoding="utf-8")
checks=[
    ("api gate", "ALLOW_TRANSCRIPTION_API" in trans),
    ("download false", '"can_download": False' in collect),
    ("third party analysis allowed", rights_allows_reference_analysis("third_party_reference_only")),
    ("third party media blocked", not rights_allows_media_use("third_party_reference_only")),
]
bad=[n for n,o in checks if not o]
for n,o in checks: print(f"  {'PASS' if o else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
