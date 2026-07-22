#!/usr/bin/env python3
"""Clip ranking changes with transcript semantics and bounded comment reaction."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from media_growth_schemas import score_clip_candidate

source = {"rights_status": "approved_creator_clip", "target_account_ids": ["liver_manager"]}
plain = score_clip_candidate(source, has_transcript=True, transcript_excerpt="雑談をしています", semantic_score=0.2)
grounded = score_clip_candidate(
    source,
    has_transcript=True,
    transcript_excerpt="なぜ初見のコメントが増えないのか。まず配信の入口を確認することが大事です。",
    semantic_score=3.5,
    comment_signal_count=4,
)
checks = {
    "semantic hook raises score": grounded["hook_strength"] > plain["hook_strength"],
    "account evidence raises relevance": grounded["creator_relevance"] > plain["creator_relevance"],
    "comment reaction contributes": grounded["comment_reaction_score"] == 8,
    "final score is evidence-sensitive": grounded["clip_score"] > plain["clip_score"],
}
for label, ok in checks.items():
    print(f"  {'PASS' if ok else 'FAIL'} {label}")
raise SystemExit(0 if all(checks.values()) else 1)
