#!/usr/bin/env python3
"""Owner-approved registered sources retain scope but never bless reposts."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from acquire_approved_source_posts import post_matches_registered_author  # noqa: E402
from reference.source_registry import load_registry  # noqa: E402

sources = load_registry()
approved = [source for source in sources if source.get("registered_owner_scope_id")]
assert approved
assert all(source["rights_status"] == "approved_creator_clip" for source in approved)
assert all(source["permission_status"] == "approved" for source in approved)
assert all(source["media_usage_mode"] == "direct_and_clip" for source in approved)
assert all(source["original_author_match_required"] is True for source in approved)
assert all(source["allow_new_caption"] is True for source in approved)

source = next(source for source in approved if source.get("source_handle"))
handle = str(source["source_handle"]).lstrip("@")
assert post_matches_registered_author(SimpleNamespace(author_handle=handle), source)
assert not post_matches_registered_author(SimpleNamespace(author_handle="unrelated_reposter"), source)
assert not post_matches_registered_author(SimpleNamespace(author_handle=""), source)

print("PASS: registered source scope and original-author provenance gate")
