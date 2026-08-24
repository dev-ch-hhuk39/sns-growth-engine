#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

from evidence_context_caption import generate_evidence_context_caption  # noqa: E402
from public_post_quality import apply_account_voice, final_public_post_validator  # noqa: E402
from run_direct_reference_media_pipeline import _source_map  # noqa: E402


class FakeClient:
    _direct_media_records_cache = {}


def main() -> int:
    malformed = (
        "配信でコメントを増やすには、初見が入りやすい空気を作ることが大事。"
        "私ならまず、答えやすい質問を一つ試すよんだよね。"
    )
    assert final_public_post_validator(malformed, "liver_manager")["status"] == "BLOCKED"
    assert "malformed_spoken_cadence" in final_public_post_validator(malformed, "liver_manager")["blocked_reasons"]

    voiced = apply_account_voice(
        "配信で初見が入りやすい状態を作るには、入室直後の声かけを確認する方がいいと思います。\n\n"
        "まずコメントが生まれる場面を見直すと、次の配信で試す行動を決めやすくなるよ。",
        "liver_manager",
    )
    assert "よんだよね" not in voiced, voiced
    assert "まず、まず" not in voiced, voiced

    polite_closing = apply_account_voice(
        "配信で初見が入りやすい状態を作るには、入室直後の声かけが大事。\n\n"
        "まず初見が入室した場面を見直すだけでも、配信の入りやすさを整えられます。",
        "liver_manager",
    )
    assert "ますんだよね" not in polite_closing, polite_closing
    assert "ますよね" in polite_closing, polite_closing

    beauty = generate_evidence_context_caption(
        account_id="beauty_account",
        transcript_excerpt=(
            "乾燥しやすい肌のスキンケアは、化粧水を一度にたくさん重ねるより、"
            "薄く分けて保湿すると肌の状態を確認しやすいと話しています。"
        ),
        recent_posts=[],
    )
    assert beauty["status"] == "PASS", beauty
    assert final_public_post_validator(beauty["public_post_text"], "beauty_account")["status"] == "PASS", beauty

    sheet_source = {
        "source_id": "src_test",
        "source_url": "https://example.com/old",
        "registered_owner_scope_id": "",
        "allow_new_caption": "false",
    }
    canonical_source = {
        "source_id": "src_test",
        "source_url": "https://example.com/canonical",
        "registered_owner_scope_id": "owner_scope_v1",
        "permission_status": "approved",
        "allow_new_caption": True,
        "provenance_required": True,
        "original_author_match_required": True,
    }
    with (
        patch("run_direct_reference_media_pipeline._records") as records,
        patch("run_direct_reference_media_pipeline.load_registry", return_value=[canonical_source]),
    ):
        records.side_effect = lambda _client, logical: [sheet_source] if logical == "source_accounts" else []
        mapped = _source_map(FakeClient())["src_test"]
    assert mapped["registered_owner_scope_id"] == "owner_scope_v1"
    assert mapped["allow_new_caption"] is True
    assert mapped["source_url"] == "https://example.com/old"

    print("test_final_media_caption_readiness: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
