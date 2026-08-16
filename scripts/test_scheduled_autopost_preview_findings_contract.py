#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

from generate_threads_ideas_from_references import (  # noqa: E402
    build_measured_pdca_inputs,
    build_measured_pdca_public_text,
)
from public_post_quality import final_public_post_validator, generate_reader_facing_post  # noqa: E402
from run_scheduled_autopost_preview_v2 import _quality  # noqa: E402


def posted(result_id: str, text: str) -> dict[str, str]:
    return {
        "result_id": result_id,
        "account_id": "night_scout",
        "platform": "threads",
        "status": "POSTED",
        "posted_text": text,
        "content_route": "reference_text",
        "generation_mode": "reference_text",
    }


positive = {
    "snapshot_id": "s-positive",
    "result_id": "r-positive",
    "account_id": "night_scout",
    "platform": "threads",
    "metrics_status": "MEASURED",
    "views": "100",
    "likes": "1",
    "comments": "1",
    "reposts": "0",
    "quotes": "0",
    "collected_at": "2026-08-06T00:00:00+00:00",
}
zero_signal = {
    **positive,
    "snapshot_id": "s-zero",
    "result_id": "r-zero",
    "likes": "0",
    "comments": "0",
}
posts, scores, source_meta = build_measured_pdca_inputs(
    measured_rows=[positive, zero_signal],
    posted_results=[
        posted("r-positive", "夜職の条件は表示額より控除を先に確認したい。"),
        posted("r-zero", "反応がない投稿。"),
    ],
    account_id="night_scout",
)
assert posts and scores
assert set(source_meta) == {"r-positive"}, source_meta
pdca = build_measured_pdca_public_text(
    account_id="night_scout",
    meta=source_meta["r-positive"],
)
for marker in ("体入", "僕が", "控除", "早上がり", "店"):
    assert marker in pdca, (marker, pdca)
for internal_marker in ("前回の投稿", "100表示", "いいね1件", "検証します"):
    assert internal_marker not in pdca, (internal_marker, pdca)

original = generate_reader_facing_post("night_scout", 1)["public_post_text"]
assert "僕" in original, original
assert final_public_post_validator(original, "night_scout")["status"] == "PASS"

short_direct_quality = _quality(
    "初見バトルで出会った人と仲良くなれないライバーさん。",
    "liver_manager",
    "direct_reference_media",
)
assert short_direct_quality["pass"] is False, short_direct_quality

source = (ROOT / "scripts/generate_threads_ideas_from_references.py").read_text(encoding="utf-8")
assert 'post_type == "reference_text"' in source
assert "ns_1400_reference" in source and "lm_1300_reference" in source
assert "reference_source_required_for_reference_slot" in source
evidence_caption = (ROOT / "scripts/evidence_context_caption.py").read_text(encoding="utf-8")
assert 'PROVIDER_VERSION = "2"' in evidence_caption
assert evidence_caption.count("僕が夜職") >= 6
preview = (ROOT / "scripts/run_scheduled_autopost_preview_v2.py").read_text(encoding="utf-8")
assert "PREVIEW_COMPLETE_WITH_BLOCKS" in preview
assert "preview_blocked_reasons" in preview
assert "night_scout_first_person_boku_missing" in preview
quality_source = (ROOT / "scripts/public_post_quality.py").read_text(encoding="utf-8")
assert "persona_first_person_missing" not in quality_source
audit = (ROOT / "scripts/run_scheduled_autopost_readonly_audit.py").read_text(encoding="utf-8")
assert "quota exceeded" in audit.lower()
workflow = (ROOT / ".github/workflows/wp3-production-readonly-verification.yml").read_text(encoding="utf-8")
assert "main:refs/remotes/origin/main" in workflow
assert "schedule:" not in workflow
print("PASS test_scheduled_autopost_preview_findings_contract.py")
