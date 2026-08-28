#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "src"),
]

from evidence_context_caption import (  # noqa: E402
    generate_evidence_context_caption,
)
from public_post_quality import (  # noqa: E402
    final_public_post_validator,
)

evidence = """
リスナーの青文字でも読んじゃう。
質問コーナー。
挨拶しときゃ本当になんとかなる。
配信中の入室通知は読み上げますか？
ライバーが配信でリスナーへの挨拶をどうするかという話。
"""

result = generate_evidence_context_caption(
    account_id="liver_manager",
    transcript_excerpt=evidence,
    recent_posts=[],
)

print(
    json.dumps(
        result,
        ensure_ascii=False,
        indent=2,
    )
)

assert result["status"] == "PASS", (
    result.get(
        "blocked_reasons"
    )
)

text = str(
    result.get(
        "public_post_text",
        "",
    )
)

assert len(text) >= 65
assert "私ならまず、だから" not in text
assert "」っていう話" not in text
assert "配信" in text
assert any(
    term in text
    for term in (
        "リスナー",
        "初見",
        "入室",
        "コメント",
    )
)

validator = final_public_post_validator(
    text,
    "liver_manager",
)

assert validator["status"] == "PASS", (
    validator.get(
        "blocked_reasons"
    )
)

alignment = result.get(
    "semantic_alignment",
    {},
)

assert (
    alignment.get(
        "status"
    )
    == "PASS"
)

assert (
    int(
        alignment.get(
            "unsupported_claim_count",
            1,
        )
    )
    == 0
)

print(
    "[PASS] Liver Direct evidence caption reaches strict PASS"
)

print(
    "[PASS] voice/persona/public validator unchanged and PASS"
)

print(
    "[PASS] unsupported claim count remains zero"
)
