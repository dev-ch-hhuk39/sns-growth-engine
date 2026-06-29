#!/usr/bin/env python3
"""recover_production_sheets_threads_first.py の source registry verify checks を検証。

Sheets に依存せず、source_rows() と registry JSON から
8つの不変条件 (verify_state に追加した checks) を直接検証する。
さらに各 check 名が verify_state に wired されていることを確認する。
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config/source_accounts/default_sources.json"
RECOVER_SRC = (ROOT / "scripts/recover_production_sheets_threads_first.py").read_text()

spec = importlib.util.spec_from_file_location("recover", ROOT / "scripts/recover_production_sheets_threads_first.py")
REC = importlib.util.module_from_spec(spec)
spec.loader.exec_module(REC)

RAW = json.loads(REGISTRY.read_text())["sources"]
ACC, VID = REC.source_rows()
BY_ID = {s.get("source_id"): s for s in RAW}

CHECK_NAMES = [
    "source_registry_has_required_categories",
    "source_urls_are_deduped",
    "x_sources_manual_only_current_phase",
    "tiktok_youtube_reference_only",
    "beauty_future_inactive",
    "beauty_target_account_id_preserved",
    "beauty_reference_only_safety",
    "waiting_url_input_not_fetchable",
    "third_party_media_not_reusable_by_default",
    "source_priority_valid_range",
]


def test_check_names_wired():
    for name in CHECK_NAMES:
        assert f'"{name}"' in RECOVER_SRC, f"check not wired: {name}"


def test_has_required_categories():
    assert any("night_scout" in (s.get("target_account_ids") or []) for s in RAW)
    assert any("liver_manager" in (s.get("target_account_ids") or []) for s in RAW)
    assert any(s.get("future_track") == "beauty_future" for s in RAW)
    cats = set()
    for s in RAW:
        c = s.get("source_category")
        cats.update(c if isinstance(c, list) else [c])
        cats.update(s.get("source_categories") or [])
    assert {"night_work_scout", "cabaret_knowhow", "video_reference", "article_reference", "trend_query", "text_reference"} <= cats


def test_urls_deduped():
    urls = [REC._norm_reg_url(s.get("source_url", "")) for s in RAW if str(s.get("source_url", "")).strip()]
    assert len(urls) == len(set(urls)), "duplicate source_url in registry"


def test_x_manual_only():
    xs = [r for r in ACC if r["source_platform"] == "x"]
    assert xs
    assert all(r["active"] == "false" and r["fetch_enabled"] == "false" for r in xs)


def test_tiktok_youtube_reference_only():
    vids = [r for r in ACC if r["source_platform"] in ("tiktok", "youtube")]
    assert vids
    assert all(r["reuse_policy"] == "reference_only" and r["media_policy"] == "do_not_download" for r in vids)
    assert all(r["allow_download"] == "false" and r["allow_cut"] == "false" and r["allow_upload"] == "false" for r in vids)


def test_beauty_future_inactive():
    bs = [r for r in ACC if BY_ID.get(r["source_id"], {}).get("future_track") == "beauty_future"]
    assert bs
    assert all(r["active"] == "false" for r in bs)


def test_beauty_target_account_id_preserved():
    raw = [s for s in RAW if s.get("future_track") == "beauty_future" or "beauty_account" in (s.get("target_account_ids") or [])]
    assert raw
    assert all("beauty_account" in (s.get("target_account_ids") or []) for s in raw)
    assert all("beauty_future" not in (s.get("target_account_ids") or []) for s in raw)


def test_beauty_reference_only_safety():
    bs = [r for r in ACC if BY_ID.get(r["source_id"], {}).get("future_track") == "beauty_future"]
    assert bs
    assert all(r["rights_policy"] == "reference_only" for r in bs)
    assert all(r["use_policy"] == "REFERENCE_ONLY" for r in bs)
    assert all(r["can_reuse_media"] == "false" for r in bs)


def test_waiting_url_input_not_fetchable():
    waiting = [r for r in ACC if not str(r.get("source_url", "")).strip()]
    assert all(r["fetch_enabled"] == "false" for r in waiting)


def test_third_party_media_not_reusable():
    assert all(r["allow_upload"] == "false" and r["allow_cut"] == "false" for r in ACC)


def test_priority_valid_range():
    assert all(REC._priority_in_range(s.get("priority")) for s in RAW)


def main() -> int:
    tests = [
        test_check_names_wired,
        test_has_required_categories,
        test_urls_deduped,
        test_x_manual_only,
        test_tiktok_youtube_reference_only,
        test_beauty_future_inactive,
        test_beauty_target_account_id_preserved,
        test_beauty_reference_only_safety,
        test_waiting_url_input_not_fetchable,
        test_third_party_media_not_reusable,
        test_priority_valid_range,
    ]
    passed = failed = 0
    print("\n=== test_source_registry_verify_checks ===")
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
