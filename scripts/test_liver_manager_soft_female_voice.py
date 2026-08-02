#!/usr/bin/env python3
"""Liver Manager accepts soft female voice without Japanese full stops."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(
    0,
    str(ROOT / "scripts"),
)

from public_post_quality import final_public_post_validator

text = (
    "配信を始めたばかりだと、"
    "コメントが来ない時間って不安になりますよね\n\n"
    "でも、ずっと話し続けなくても大丈夫です！\n"
    "まずは今日あったことを一つ話して、"
    "答えやすい質問につなげてみてください\n\n"
    "私なら、二択で聞ける話題を一つ準備しておきます\n"
    "初見のリスナーも入りやすくなりますよ"
)

result = final_public_post_validator(
    text,
    "liver_manager",
)

assert "。" not in text
assert result["status"] == "PASS", result
assert result["naturalness_score"] >= 80, result

persona = result[
    "account_fit_check"
]["persona"]

assert persona["details"][
    "soft_marker_count"
] >= 1, persona

assert persona["details"][
    "emoji_count"
] == 0, persona

print(
    "PASS "
    "test_liver_manager_soft_female_voice.py"
)
