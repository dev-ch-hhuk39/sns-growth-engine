#!/usr/bin/env python3
"""Liver Manager requires empathetic, concrete manager guidance."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from public_post_quality import final_public_post_validator

from public_post_quality import load_post_generation_rules

profile = load_post_generation_rules()["persona_profiles"]["liver_manager"]

assert profile["first_person"] == "僕"
assert "私" in profile["forbidden_first_person"]
assert "僕" not in profile["forbidden_first_person"]

good = (
    "実際に配信を見ていると、初見さんが残らない子ほど入室後の声かけで損をしていることが多いんですよね。\n\n"
    "今の話題を短く伝えて、答えやすい質問を一つ置くと、コメントの入口が作れます。\n\n"
    "僕なら、まず次の配信でこの一つだけ試してみるのがおすすめです。"
)
wrong_voice = (
    "私は配信で重要なのは初見対応だ。\n改善する必要がある。\n準備も重要だ。\n"
    "配信時間\n初見への挨拶\nコメントの回収\nギフト導線\n根性\n継続"
)

assert final_public_post_validator(good, "liver_manager")["status"] == "PASS"
blocked = final_public_post_validator(wrong_voice, "liver_manager")
assert blocked["status"] == "BLOCKED"
assert "persona_first_person_mismatch" in blocked["blocked_reasons"]
assert "persona_masculine_assertion_repetition" in blocked["blocked_reasons"]
assert "persona_fragment_overuse" in blocked["blocked_reasons"]
print("PASS test_persona_validator_liver_manager.py")
