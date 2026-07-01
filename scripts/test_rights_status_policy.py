#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from media.rights_policy import build_rights_decision, rights_allows_media_use

checks = [
    ("third party blocked", not rights_allows_media_use("third_party_reference_only")),
    ("unknown blocked", not rights_allows_media_use("unknown")),
    ("owned allowed", rights_allows_media_use("owned")),
    ("licensed allowed", rights_allows_media_use("licensed")),
    ("approved creator allowed", rights_allows_media_use("approved_creator_clip")),
    ("reference analysis still allowed", build_rights_decision("third_party_reference_only").reference_analysis_allowed),
]
bad = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
