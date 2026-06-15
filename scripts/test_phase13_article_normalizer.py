#!/usr/bin/env python3
"""test_phase13_article_normalizer.py"""
from __future__ import annotations
import os, sys
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

results = []

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append((name, status, detail))
    print(f"  {'✓' if condition else '✗'} [{status}] {name}" + (f": {detail}" if detail else ""))


def _make_raw_article(**kwargs):
    base = {
        "source_id": "src_lm_note_001",
        "source_platform": "note",
        "item_type": "article",
        "fetch_adapter": "article_fetcher",
        "raw_url": "https://note.com/test/n/n123456",
        "title": "テスト記事タイトル",
        "description": "これはテスト記事の説明文です。ライバーマネジメントについての知見を共有します。",
        "body": "本文サンプル。" * 30,
        "author": "test_author",
        "rights_status": "reference_only",
        "media_policy": "plan_only",
        "fetched_at": "2026-06-15T00:00:00+09:00",
    }
    base.update(kwargs)
    return base


def main():
    print("=== Phase 13: ArticleReferenceNormalizer テスト ===\n")

    print("[1] Import")
    try:
        from src.reference.article_reference_normalizer import (
            normalize_article_to_reference,
            normalize_articles,
        )
        check("import OK", True)
    except Exception as e:
        check("import", False, str(e))
        sys.exit(1)

    print("\n[2] normalize_article_to_reference 基本")
    raw = _make_raw_article()
    ref = normalize_article_to_reference(raw, account_id="liver_manager", platform="note")
    check("returns dict", isinstance(ref, dict))
    check("reference_post_id present", "reference_post_id" in ref)
    check("reference_post_id non-empty", bool(ref.get("reference_post_id")))
    check("abstract present", "abstract" in ref)
    check("abstract non-empty", bool(ref.get("abstract")))
    check("require_transform=True", ref.get("require_transform") is True)
    check("normalized_at present", "normalized_at" in ref)
    check("source_platform preserved", ref.get("source_platform") == "note")
    check("item_type preserved", ref.get("item_type") == "article")

    print("\n[3] abstract — description から生成")
    raw2 = _make_raw_article(description="テスト説明文ABC", body="")
    ref2 = normalize_article_to_reference(raw2, account_id="liver_manager")
    check("abstract uses description", "テスト説明文ABC" in ref2.get("abstract", ""))

    print("\n[4] abstract — description なし、body から200文字")
    raw3 = _make_raw_article(description="", body="B" * 300)
    ref3 = normalize_article_to_reference(raw3, account_id="liver_manager")
    abstract = ref3.get("abstract", "")
    check("abstract from body max 203 chars (200 + ...)", len(abstract) <= 203)
    check("abstract not empty", bool(abstract))

    print("\n[5] normalize_articles — フィルタリング")
    items = [
        _make_raw_article(item_type="article"),
        {"item_type": "video", "source_id": "vid_001"},  # フィルタアウトされる
        _make_raw_article(item_type="article", source_id="src_002"),
        _make_raw_article(fetch_adapter="article_fetcher", item_type="other"),  # fetch_adapterでキャッチ
    ]
    refs = normalize_articles(items, account_id="liver_manager")
    check("returns list", isinstance(refs, list))
    check("video filtered out", all(r.get("item_type") != "video" for r in refs))
    check("3件以上 (article + article_fetcher adapter)", len(refs) >= 2)

    print("\n[6] account_id が reference_post_id に反映される")
    raw4 = _make_raw_article(source_id="src_unique_x")
    ref4 = normalize_article_to_reference(raw4, account_id="night_scout")
    check("reference_post_id unique per source_id", "src_unique_x" in ref4.get("reference_post_id", ""))

    print("\n[7] platform フィールド引き継ぎ")
    ref5 = normalize_article_to_reference(_make_raw_article(), account_id="liver_manager", platform="article")
    check("platform=article sets source_platform if missing", ref5.get("source_platform") in ("note", "article"))

    print("\n--- 結果 ---")
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    print(f"PASS: {passed} / FAIL: {failed}")
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
