#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
from media_source_policy import decision
source = {"source_id": "none", "rights_status": "approved_creator_clip", "permission_status": "approved", "permission_scope": ["download", "transcribe", "cut"]}
assert not decision(source, "direct_media")["allowed"]
print("PASS test_direct_reference_media_requires_explicit_permission.py")
