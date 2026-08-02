#!/usr/bin/env python3
"""Liver Manager requires a soft, concrete female manager voice."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from public_post_quality import final_public_post_validator
from public_post_quality import load_post_generation_rules

profile = load_post_generation_rules()["persona_profiles"]["liver_manager"]

assert profile["first_person"] == "私"
assert "僕" in profile["forbidden_first_person"]
assert "私" not in profile["forbidden_first_person"]

good = (
    "実際に配信を見ていると、初見さんが残らない子ほど"
    "入室後の声かけで損をしていることが多いんですよね。\n\n"
    "今の話題を短く伝えて、答えやすい質問を一つ置くと、"
    "コメントの入口が作れます。\n\n"
    "私なら、まず次の配信でこの一つだけ"
    "試してみるのがおすすめです。"
)

wrong_voice = (
    "僕は配信で重要なのは初見対応だ。\n"
    "改善する必要がある。\n"
    "準備も重要だ。\n"
    "配信時間\n"
    "初見への挨拶\n"
    "コメントの回収\n"
    "ギフト導線\n"
    "根性\n"
    "継続"
)

assert (
    final_public_post_validator(
        good,
        "liver_manager",
    )["status"]
    == "PASS"
)

blocked = final_public_post_validator(
    wrong_voice,
    "liver_manager",
)

assert blocked["status"] == "BLOCKED"

assert (
    "persona_first_person_mismatch"
    in blocked["blocked_reasons"]
)

assert (
    "persona_masculine_assertion_repetition"
    in blocked["blocked_reasons"]
)

assert (
    "persona_fragment_overuse"
    in blocked["blocked_reasons"]
)

print(
    "PASS test_persona_validator_liver_manager.py"
)
