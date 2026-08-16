#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

from apply_v29_voice_correction import build_matrix  # noqa: E402


def main() -> int:
    matrix = build_matrix()
    assert len(matrix) == 10
    assert {item["account_id"] for item in matrix} == {"night_scout", "liver_manager"}
    for item in matrix:
        validation = item["validation"]
        assert validation["status"] == "PASS", item
        assert validation["voice_persona_check"]["status"] == "VOICE_PERSONA_PASS", item
        assert int(validation["public_post_quality_score"]) >= 85, item
        assert item["queue_id"].startswith("q_voice_v29_")
    print("PASS: V29 full 5x2 route matrix is deterministic-review ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
