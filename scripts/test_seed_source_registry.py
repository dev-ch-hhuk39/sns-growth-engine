#!/usr/bin/env python3
"""seed_source_registry.py と回収済み source registry の分類/安全/重複/scoring を検証。

カバー範囲(タスクJの統合):
- test_source_url_discovery: 既存共有URLが registry に回収されている
- test_source_registry_classification: platform/target/future_track 分類
- test_x_sources_manual_only: X は active=false / fetch_enabled=false
- test_video_sources_reference_only: TikTok/YouTube は reference_only / 再利用不可
- test_beauty_future_inactive: beauty_future は active=false
- test_waiting_url_input_not_fetchable: URL未入力は fetch 不可
- test_seed_source_registry_duplicates: dedup で重複skip
- test_source_priority_rules: scoring/優先順位ルール
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config/source_accounts/default_sources.json"


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


SEED = _load("seed_source_registry", "scripts/seed_source_registry.py")
RAW = json.loads(REGISTRY.read_text())["sources"]


def _acc(target="all", platform="all"):
    _, acc, vid, dropped, raw_by_id = SEED.build_seed(REGISTRY, target, platform)
    return acc, vid, dropped, raw_by_id


def test_source_url_discovery():
    urls = {s.get("source_url") for s in RAW}
    # 既知の共有 Threads URL が回収されている
    for u in [
        "https://www.threads.com/@kyaba_oohata",
        "https://www.threads.com/@kyaba_rui_scout",
        "https://www.threads.com/@chiikawan400",
    ]:
        assert u in urls, f"missing recovered threads url: {u}"
    # example由来の実URLも回収されている
    assert any("tiktok.com/@" in str(u) for u in urls), "no tiktok url recovered"
    assert any("youtube.com/" in str(u) for u in urls), "no youtube url recovered"
    assert any("x.com/" in str(u) for u in urls), "no x url recovered"


def test_source_registry_classification():
    acc, _, _, raw_by_id = _acc()
    plats = {r["source_platform"] for r in acc}
    assert {"threads", "x", "tiktok", "youtube", "note"} <= plats, plats
    # target系統が存在
    tgts = {t for s in RAW for t in (s.get("target_account_ids") or [])}
    assert "night_scout" in tgts and "liver_manager" in tgts
    assert any(s.get("future_track") == "beauty_future" for s in RAW)
    assert "beauty_future" not in tgts, "beauty_future must never be a target_account_id"


def test_x_sources_manual_only():
    acc, _, _, _ = _acc(platform="x")
    assert acc, "no x sources"
    for r in acc:
        assert r["active"] == "false", r["source_id"]
        assert r["fetch_enabled"] == "false", r["source_id"]


def test_video_sources_reference_only():
    acc, _, _, raw_by_id = _acc()
    vids = [r for r in acc if r["source_platform"] in ("tiktok", "youtube")]
    assert vids
    for r in vids:
        raw = raw_by_id[r["source_id"]]
        if raw.get("rights_status") in {"owned", "licensed", "approved_creator_clip"}:
            assert raw.get("permission_status") == "approved", r["source_id"]
            assert r["reuse_policy"] == "approved_creator_clip", r["source_id"]
            assert r["media_policy"] == "approved_gated", r["source_id"]
            assert r["allow_download"] == "gated" and r["allow_cut"] == "gated" and r["allow_upload"] == "gated"
            assert r["can_reuse_media"] == "true", r["source_id"]
        else:
            assert r["reuse_policy"] == "reference_only", r["source_id"]
            assert r["allow_download"] == "false" and r["allow_cut"] == "false" and r["allow_upload"] == "false"
            assert r["can_reuse_media"] == "false", r["source_id"]


def test_beauty_future_inactive():
    acc, vid, _, raw_by_id = _acc(target="beauty_future")
    assert acc, "no beauty_future sources"
    assert vid, "beauty future video reference rows should remain seedable as blocked metadata"
    for r in acc:
        assert r["active"] == "false", r["source_id"]
        assert r["fetch_enabled"] == "false", r["source_id"]
        assert r["target_account_ids"] == "beauty_account", r["source_id"]
        assert r["future_track"] == "beauty_future", r["source_id"]
        assert r["source_track"] == "beauty_future", r["source_id"]
        assert r["usage_scope"] == "future_reference_only", r["source_id"]
        assert r["rights_policy"] == "reference_only", r["source_id"]
        assert r["use_policy"] == "REFERENCE_ONLY", r["source_id"]
        assert r["can_reuse_media"] == "false", r["source_id"]
        assert r["default_queue_status"] == "WAITING_REVIEW", r["source_id"]
        assert r["review_status"] == "BLOCKED_BEAUTY_ACCOUNT", r["source_id"]


def test_beauty_account_filter_keeps_video_rows():
    acc, vid, _, _ = _acc(target="beauty_account")
    assert len(acc) == 23, len(acc)
    assert len(vid) == 17, len(vid)
    assert all(r["account_id"] == "beauty_account" for r in vid)


def test_query_platform_filter():
    acc, vid, _, _ = _acc(platform="query")
    assert len(acc) == 1, len(acc)
    assert vid == []
    assert acc[0]["fetch_enabled"] == "false"


def test_waiting_url_input_not_fetchable():
    acc, _, _, _ = _acc()
    for r in acc:
        if not str(r.get("source_url", "")).strip():
            assert SEED._registry_status(r) == "WAITING_URL_INPUT"
            assert r["fetch_enabled"] == "false", r["source_id"]


def test_seed_source_registry_duplicates():
    # 同一URLを2件含む入力 -> 1件にdedup
    rows = [
        {"source_id": "a", "source_platform": "x", "source_handle": "@dup", "source_url": "https://x.com/dup"},
        {"source_id": "b", "source_platform": "x", "source_handle": "@dup2", "source_url": "https://www.x.com/dup/"},
        {"source_id": "c", "source_platform": "x", "source_handle": "@other", "source_url": "https://x.com/other"},
    ]
    kept, dropped = SEED._dedup(rows)
    assert len(kept) == 2, [r["source_id"] for r in kept]
    assert any("dup_source_url" in d[1] for d in dropped)
    # 全registryでも source_url 重複なし
    acc, _, _, _ = _acc()
    norm = [SEED._norm_url(r["source_url"]) for r in acc if r.get("source_url")]
    assert len(norm) == len(set(norm)), "registry has dup urls"


def test_source_priority_rules():
    scoring = _load("source_scoring", "src/reference/source_scoring.py")
    personal = {"source_platform": "tiktok", "source_handle": "@liver_creator",
                "source_category": "tiktok_live_creator", "target_account_ids": ["liver_manager"],
                "review_notes": "個人配信者 ノウハウ", "active": True}
    official = {"source_platform": "youtube", "source_handle": "@official_news",
                "source_category": "news", "target_account_ids": ["liver_manager"],
                "review_notes": "low_priority_media_official"}
    s_personal = scoring.source_selection_score(personal, "liver_manager")
    s_official = scoring.source_selection_score(official, "liver_manager")
    assert s_personal > s_official, (s_personal, s_official)
    assert scoring.media_official_penalty(official) == 1.0
    assert scoring.platform_priority_score({"source_platform": "tiktok"}) > scoring.platform_priority_score({"source_platform": "youtube"})
    assert 0.0 <= s_personal <= 1.0
    beauty = {"source_platform": "tiktok", "source_category": "trend_query",
              "target_account_ids": ["beauty_account"], "future_track": "beauty_future"}
    assert scoring.target_account_fit_score(beauty, "beauty_account") > 0.0
    assert scoring.target_account_fit_score(beauty, "beauty_future") > 0.0


def main() -> int:
    tests = [
        test_source_url_discovery,
        test_source_registry_classification,
        test_x_sources_manual_only,
        test_video_sources_reference_only,
        test_beauty_future_inactive,
        test_beauty_account_filter_keeps_video_rows,
        test_query_platform_filter,
        test_waiting_url_input_not_fetchable,
        test_seed_source_registry_duplicates,
        test_source_priority_rules,
    ]
    passed = failed = 0
    print("\n=== test_seed_source_registry ===")
    for t in tests:
        try:
            t(); passed += 1
        except AssertionError as e:
            print(f"  [FAIL] {t.__name__}: {e}"); failed += 1
        except Exception as e:  # noqa: BLE001
            print(f"  [ERROR] {t.__name__}: {type(e).__name__}: {e}"); failed += 1
    print(f"\n結果: PASS={passed} FAIL={failed} / {len(tests)}件")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
