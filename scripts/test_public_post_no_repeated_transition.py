#!/usr/bin/env python3
"""The production composer must not duplicate structural transition words."""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from public_post_quality import generate_grounded_reader_facing_post

for account, signal in {
    "night_scout": "時給と控除を含めた条件を比べて手取りを確認する",
    "liver_manager": "初見が入りやすい挨拶とコメントの入口を作る",
}.items():
    for index in range(32):
        text = generate_grounded_reader_facing_post(account, private_signal=signal, index=index, structure_variant=1)["public_post_text"]
        assert "最後に、最後" not in text, text
        assert "まず、まず" not in text, text
print("PASS test_public_post_no_repeated_transition.py")
