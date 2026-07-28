#!/usr/bin/env python3
"""Night Scout requires a supportive, reader-facing consultant voice."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from public_post_quality import final_public_post_validator

good = (
    "夜職で移籍を考える時、時給だけで決めるとあとから苦しくなることがある。\n\n"
    "僕が見ている中では、客層、ノルマ、出勤の相談しやすさまで確認すると、"
    "自分に合う店を選びやすい。\n\n無理に急がなくていい。続けられる条件を整理してから決めよう。"
)
wrong_voice = (
    "私は夜職の店を今すぐ応募で決めるべきだと思う。時給とノルマだけ見れば十分。"
    "必ず稼げる店を紹介します。"
)

assert final_public_post_validator(good, "night_scout")["status"] == "PASS"
blocked = final_public_post_validator(wrong_voice, "night_scout")
assert blocked["status"] == "BLOCKED"
assert "persona_first_person_mismatch" in blocked["blocked_reasons"]
assert "persona_aggressive_recruiting" in blocked["blocked_reasons"]
print("PASS test_persona_validator_night_scout.py")
