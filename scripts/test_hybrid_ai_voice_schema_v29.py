#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

import hybrid_ai_gate  # noqa: E402


def main() -> int:
    required = set(hybrid_ai_gate.REVIEW_SCHEMA["required"])
    expected = {
        "voice_persona", "voice_persona_score", "identity_fit",
        "interpersonal_distance", "register_fit", "conversational_naturalness",
    }
    assert expected <= required
    prompt = hybrid_ai_gate._review_prompt(
        {"queue_id": "q", "account_id": "liver_manager"}, "source", "candidate", {}
    )
    assert "CANONICAL_VOICE_PROFILE" in prompt
    assert "女性TikTok LIVEマネージャー" in prompt
    assert hybrid_ai_gate.GATE_SCHEMA_VERSION == "hybrid_ai_gate_v4"
    print("PASS: Gemini review schema enforces semantic account voice")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
