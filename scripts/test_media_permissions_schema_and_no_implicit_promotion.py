#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "src"))
from media_source_policy import decision
from sheets_client import TAB_DEFINITIONS
required = {"permission_id", "source_id", "usage_mode", "allow_original_repost", "evidence_reference", "revoked"}
assert required <= set(TAB_DEFINITIONS["media_permissions"])
clip_only = {"rights_status": "approved_creator_clip", "permission_status": "approved", "media_usage_mode": "clip_source", "permission_scope": ["download", "transcribe", "cut"]}
assert decision(clip_only, "direct_media")["allowed"] is False
print("PASS test_media_permissions_schema_and_no_implicit_promotion.py")
