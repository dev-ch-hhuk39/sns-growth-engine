#!/usr/bin/env python3
"""test_media_policy_guard.py — media policy / rights policy / Cloudinary upload ガード確認テスト

検証内容:
1. do_not_download ソースへの download/cut/upload が BLOCKED になること
2. plan_only ソースへの download/cut/upload/post が BLOCKED になること
3. rights_policy=unknown ソースへの media 利用が BLOCKED になること
4. candidate_status=candidate ソースへの download が BLOCKED になること
5. approved_media_only ソースへの download が OK になること（candidate_status=approved のみ）
6. Cloudinary upload guard: ALLOW_CLOUDINARY_UPLOAD=false で blocked になること
7. beauty_account ソースが BLOCKED 状態で取り扱われること
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "src"))


def _policy(source: dict, action: str) -> dict:
    from media.media_asset_store import check_source_media_policy
    return check_source_media_policy(source, action)


def test_do_not_download_blocks_download():
    source = {
        "source_id": "test_src_001",
        "rights_policy": "reference_only",
        "reuse_policy": "reference_only",
        "media_policy": "do_not_download",
        "candidate_status": "approved",
    }
    for action in ("download", "cut", "upload"):
        r = _policy(source, action)
        assert not r["allowed"], f"do_not_download は {action} を BLOCK すべき"
        assert r["status"] == "BLOCKED", f"status=BLOCKED expected, got {r['status']}"
    print("  [PASS] do_not_download → download/cut/upload BLOCKED")


def test_plan_only_blocks_download_and_post():
    source = {
        "source_id": "test_src_002",
        "rights_policy": "approved_media",
        "reuse_policy": "approved_media",
        "media_policy": "plan_only",
        "candidate_status": "approved",
    }
    for action in ("download", "cut", "upload", "post"):
        r = _policy(source, action)
        assert not r["allowed"], f"plan_only は {action} を BLOCK すべき"
    print("  [PASS] plan_only → download/cut/upload/post BLOCKED")


def test_unknown_rights_blocks_media_use():
    source = {
        "source_id": "test_src_003",
        "rights_policy": "unknown",
        "reuse_policy": "reference_only",
        "media_policy": "plan_only",
        "candidate_status": "candidate",
    }
    for action in ("download", "cut", "upload", "post"):
        r = _policy(source, action)
        assert not r["allowed"], f"rights_policy=unknown は {action} を BLOCK すべき"
    print("  [PASS] rights_policy=unknown → media利用 BLOCKED")


def test_candidate_status_blocks_download():
    source = {
        "source_id": "test_src_004",
        "rights_policy": "approved_media",
        "reuse_policy": "approved_media",
        "media_policy": "approved_media_only",
        "candidate_status": "candidate",
    }
    r = _policy(source, "download")
    assert not r["allowed"], "candidate_status=candidate は download を BLOCK すべき"
    print("  [PASS] candidate_status=candidate → download BLOCKED")


def test_approved_media_allows_download():
    source = {
        "source_id": "test_src_005",
        "rights_policy": "approved_media",
        "reuse_policy": "approved_media",
        "media_policy": "approved_media_only",
        "candidate_status": "approved",
    }
    r = _policy(source, "download")
    assert r["allowed"], f"approved_media + approved status は download OK のはず。reasons={r['blocked_reasons']}"
    print("  [PASS] approved_media + candidate_status=approved → download OK")


def test_cloudinary_upload_guard_blocked():
    os.environ.pop("ALLOW_CLOUDINARY_UPLOAD", None)
    from media.cloudinary_uploader import plan_cloudinary_upload
    asset = {
        "asset_id": "ma_test001",
        "account_id": "night_scout",
        "source_id": "src_test",
        "local_path": "/tmp/test.mp4",
        "media_policy": "approved_media_only",
        "rights_policy": "approved_media",
    }
    result = plan_cloudinary_upload(asset)
    assert result.get("status") == "BLOCKED" and not result.get("upload"), f"ALLOW_CLOUDINARY_UPLOAD 未設定時は upload BLOCKED のはず: {result}"
    print("  [PASS] ALLOW_CLOUDINARY_UPLOAD 未設定 → Cloudinary upload BLOCKED")


def test_beauty_account_sources_blocked():
    import json
    path = os.path.join(_ROOT, "config", "source_accounts", "default_sources.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    sources = data.get("sources", [])
    beauty_sources = [s for s in sources if "beauty_account" in s.get("target_account_ids", [])]
    assert beauty_sources, "beauty_account ソースが見つかりません"
    for s in beauty_sources:
        assert not s.get("active", False), f"{s['source_id']}: beauty_account ソースが active=true になっています"
        assert not s.get("fetch_enabled", False), f"{s['source_id']}: beauty_account ソースが fetch_enabled=true になっています"
    print(f"  [PASS] beauty_account ソース {len(beauty_sources)}件 全て active=false / fetch_enabled=false")


def test_production_sources_no_immediate_download():
    import json
    path = os.path.join(_ROOT, "config", "source_accounts", "default_sources.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    sources = data.get("sources", [])
    failed = []
    for s in sources:
        if s.get("allow_download") or s.get("allow_cut") or s.get("allow_upload"):
            if (
                s.get("rights_policy") not in ("approved_media", "own_media", "approved_creator_clip", "licensed")
                or s.get("permission_status") != "approved"
            ):
                failed.append(s["source_id"])
    assert not failed, f"rights_policy 未確定でdownload/cut/upload が有効なソース: {failed}"
    print(f"  [PASS] 全ソースで rights_policy 未確定のdownload/cut/uploadなし")


def main():
    tests = [
        test_do_not_download_blocks_download,
        test_plan_only_blocks_download_and_post,
        test_unknown_rights_blocks_media_use,
        test_candidate_status_blocks_download,
        test_approved_media_allows_download,
        test_cloudinary_upload_guard_blocked,
        test_beauty_account_sources_blocked,
        test_production_sources_no_immediate_download,
    ]
    passed = 0
    failed = 0
    print("\n=== test_media_policy_guard ===")
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            print(f"  [FAIL] {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  [ERROR] {t.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n結果: PASS={passed} FAIL={failed} / {len(tests)}件")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
