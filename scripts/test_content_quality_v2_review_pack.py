#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

from build_content_quality_v2_review_pack import media_candidates, render, text_candidates  # noqa: E402
from generation.content_quality_v2 import load_policy  # noqa: E402


def test_review_pack_counts_are_five_per_account() -> None:
    counts = load_policy()["draft_pack"]
    assert counts["text_per_account"] == 5
    assert counts["media_packages_per_account"] == 5
    assert counts["status"] == "DRAFT_ONLY"
    assert counts["never_write_ready"] is True


def test_text_sample_is_ranked_and_beauty_emoji_is_present() -> None:
    rows = text_candidates()
    assert {account: len(items) for account, items in rows.items()} == {
        "night_scout": 5, "liver_manager": 5, "beauty_account": 5,
    }
    beauty_allowed = load_policy()["accounts"]["beauty_account"]["emoji_allowed"]
    for item in rows["beauty_account"]:
        count = sum(item["text"].count(emoji) for emoji in beauty_allowed)
        assert 1 <= count <= 4
        assert item["hard_gate"]["status"] == "PASS"


def test_liver_draft_style_varies_without_blocking() -> None:
    rows = text_candidates()["liver_manager"]
    assert len({item.get("draft_style_variant") for item in rows}) > 1
    assert len({
        ("！" in item["text"], "？" in item["text"],
         any(emoji in item["text"] for emoji in ("☺️", "💡", "✨", "🌱", "🫶")))
        for item in rows
    }) > 1
    assert all("💡。" not in item["text"] for item in rows)
    assert all(item["hard_gate"]["status"] == "PASS" for item in rows)
    assert all(item["batch_style_diversity_status"] in {"PASS", "WARN"} for item in rows)


def test_media_preview_sample_is_unique_ranked_and_fail_closed() -> None:
    rows = []
    for account in ("night_scout", "liver_manager", "beauty_account"):
        for index in range(7):
            rows.append({
                "account_id": account,
                "media_asset_id": f"{account}-asset-{index}",
                "media_type": "video",
                "media_preview_url": f"https://preview.invalid/{account}/{index}.mp4",
                "quality_components": {
                    "reader_value": 100 - index * 10,
                    "account_relevance": 90 - index * 5,
                    "media_caption_relevance": 80,
                    "concrete_evidence": 80,
                },
            })
    result = media_candidates_from_rows(rows)
    assert {account: len(items) for account, items in result.items()} == {
        "night_scout": 5, "liver_manager": 5, "beauty_account": 5,
    }
    for account, items in result.items():
        ids = [item["media_asset_id"] for item in items]
        assert len(ids) == len(set(ids))
        assert items[0]["media_asset_id"].endswith("asset-0")
        assert all(item["status"] == "DRAFT_ONLY" for item in items)
        assert all(item["hard_gate"]["status"] == "BLOCKED" for item in items)
        assert all(item["media_understanding"]["visual_status"] == "VISUAL_UNVERIFIED" for item in items)
        assert all(item["public_caption"].startswith("NOT_GENERATED") for item in items)


def test_review_render_uses_target_counts_and_keeps_owner_grade_blank() -> None:
    import json
    import tempfile

    rows = [{
        "account_id": account,
        "media_asset_id": f"{account}-preview-{index}",
        "media_type": "video",
        "media_preview_url": f"https://preview.invalid/{account}/{index}.mp4",
    } for account in ("night_scout", "liver_manager", "beauty_account") for index in range(5)]
    with tempfile.TemporaryDirectory(prefix="cqv2-review-render-test-") as temp_dir:
        snapshot = Path(temp_dir) / "snapshot.json"
        snapshot.write_text(json.dumps({"review_rows": rows}), encoding="utf-8")
        document = render(snapshot)
    assert document.count("text drafts (5/5)") == 3
    assert document.count("media packages (5/5)") == 3
    assert "(15 requested; at most 5/account)" in document
    assert "- BLOCKER:" not in document
    assert document.count("OWNER_GRADE: `[ ] A [ ] B [ ] C`") == 30
    assert "VISUAL_UNVERIFIED" in document
    assert "no READY or production queue write" in document


def media_candidates_from_rows(rows):
    """Use the existing pure builder with a short-lived in-memory snapshot."""
    import json
    import tempfile

    with tempfile.TemporaryDirectory(prefix="cqv2-review-test-") as temp_dir:
        path = Path(temp_dir) / "snapshot.json"
        path.write_text(json.dumps({"review_rows": rows}), encoding="utf-8")
        return media_candidates(path)


if __name__ == "__main__":
    tests = [value for name, value in globals().items() if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
    print(f"PASS: {len(tests)} Content Quality V2 review pack tests")
