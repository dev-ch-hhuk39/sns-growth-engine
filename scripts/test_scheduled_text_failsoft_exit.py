#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

from run_scheduled_text_slot_pipeline import no_post_exit_code  # noqa: E402


for reason in (
    "GEMINI_RATE_LIMITED",
    "NO_AI_APPROVED_CANDIDATE",
    "QUALITY_BLOCKED",
    "NO_READY_CANDIDATE",
    "NO_AI_APPROVED_SLOT_CANDIDATE",
    "SCHEDULED_RUN_OUT_OF_WINDOW",
):
    assert no_post_exit_code(reason) == 0, reason

for reason in (
    "CANDIDATE_GENERATION_FAILED",
    "HYBRID_REVIEW_FAILED",
    "RUNTIME_ACTIVATION_GATE_BLOCKED",
    "UNKNOWN_OPERATIONAL_FAILURE",
):
    assert no_post_exit_code(reason) == 2, reason

print("PASS test_scheduled_text_failsoft_exit.py")
