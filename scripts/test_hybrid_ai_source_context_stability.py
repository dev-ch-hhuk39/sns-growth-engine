#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

from hybrid_ai_source_context import (  # noqa: E402
    build_source_context,
    hybrid_ai_source_context_hash,
)


class FixtureClient:
    def __init__(self, records: dict[str, list[dict[str, str]]]) -> None:
        self.records = records

    class Worksheet:
        def __init__(self, rows: list[dict[str, str]]) -> None:
            self.rows = rows

        def get_all_records(self) -> list[dict[str, str]]:
            return self.rows

    def _ws(self, logical: str) -> Worksheet:
        return self.Worksheet(self.records.get(logical, []))


def main() -> None:
    queue = {
        "queue_id": "q_text_stability",
        "account_id": "night_scout",
        "target_account_id": "night_scout",
        "platform": "threads",
        "generation_mode": "original_text",
        "content_type": "original_text",
        "public_post_text": "Text candidate for context stability.",
        "internal_analysis": "first private diagnostic note",
    }
    first = build_source_context(object(), queue)
    changed_private_note = build_source_context(
        object(),
        {**queue, "internal_analysis": "different private diagnostic note"},
    )
    assert first["source_text"] == ""
    assert changed_private_note["source_text"] == ""
    assert hybrid_ai_source_context_hash(first) == hybrid_ai_source_context_hash(changed_private_note)

    missing = {**first, "permission_evidence_status": "MISSING"}
    approved = {**first, "permission_evidence_status": "APPROVED"}
    assert hybrid_ai_source_context_hash(missing) != hybrid_ai_source_context_hash(approved)

    source_text = "ベッカン担当キャストにコスメ情報を聞いた。"
    direct_queue = {
        **queue,
        "queue_id": "q_direct_source_context",
        "generation_mode": "direct_reference_media",
        "media_origin": "direct_reference",
        "source_post_id": "sp_direct_1",
        "source_id": "src_direct_1",
        "claim_support_json": (
            '[{"caption_claim":"整形した主張",'
            '"source_evidence":"キャストからコスメ情報を聞いた"}]'
        ),
    }
    direct = build_source_context(
        FixtureClient(
            {
                "source_posts": [
                    {
                        "source_post_id": "sp_direct_1",
                        "source_id": "src_direct_1",
                        "original_post_text": source_text,
                        "target_account_id": "night_scout",
                    }
                ]
            }
        ),
        direct_queue,
    )
    assert direct["original_post_text"] == source_text
    assert direct["source_text"] == source_text
    assert direct["transcript_excerpt"] == "キャストからコスメ情報を聞いた"
    assert "caption_claim" not in direct["source_text"]
    assert "caption_claim" not in direct["transcript_excerpt"]

    changed_evidence = build_source_context(
        FixtureClient(
            {
                "source_posts": [
                    {
                        "source_post_id": "sp_direct_1",
                        "source_id": "src_direct_1",
                        "original_post_text": source_text,
                        "target_account_id": "night_scout",
                    }
                ]
            }
        ),
        {
            **direct_queue,
            "claim_support_json": (
                '[{"caption_claim":"整形した主張",'
                '"source_evidence":"別の検証済み根拠文"}]'
            ),
        },
    )
    assert hybrid_ai_source_context_hash(direct) != hybrid_ai_source_context_hash(
        changed_evidence
    )

    fallback = build_source_context(
        object(),
        {
            **queue,
            "claim_support_json": (
                '[{"caption_claim":"整形した主張",'
                '"source_evidence":"公開可能な根拠文"}]'
            ),
        },
    )
    assert fallback["source_text"] == "公開可能な根拠文"
    assert "caption_claim" not in fallback["source_text"]
    print("PASS test_hybrid_ai_source_context_stability.py")


if __name__ == "__main__":
    main()
