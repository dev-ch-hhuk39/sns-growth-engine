#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

from auto_approve_queue import evaluate_item  # noqa: E402


def main() -> int:
    queue = {
        "queue_id": "q_voice_fixture",
        "account_id": "night_scout",
        "platform": "threads",
        "status": "WAITING_REVIEW",
        "generation_mode": "original_text",
        "public_post_text": "僕は夜職の店選びについて判断します。時給とノルマを確認します。客層も確認します。担当へ相談します。",
    }
    rules = {
        "auto_ready_enabled": True,
        "require_no_media_for_auto_ready": True,
        "allow_third_party_media": False,
        "blocked_terms": [],
        "min_quality_score": 0,
        "min_safety_score": 0,
        "max_risk_score": 100,
        "min_reader_value_score": 0,
        "min_naturalness_score": 0,
        "min_account_fit_score": 0,
        "max_cta_pressure_score": 100,
    }
    result = evaluate_item(
        queue=queue,
        draft=None,
        derivative=None,
        scores_by_ref={},
        existing_texts=[],
        rules=rules,
    )
    assert result["status"] == "REJECTED", result
    assert "voice_persona_not_pass" in result["reasons"], result
    assert result["voice_persona_status"] == "BLOCKED"
    print("PASS: AUTO_READY requires canonical voice persona PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
