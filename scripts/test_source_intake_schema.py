#!/usr/bin/env python3
"""test_source_intake_schema.py — source registry JSON のスキーマ検証テスト

検証内容:
1. 必須フィールドの存在
2. rights_policy / media_policy の整合性
3. beauty_account ソースが active=false であること
4. allow_download/cut/upload と rights_policy の整合性
5. auto_priority_change_allowed=false であること
"""
from __future__ import annotations

import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "src"))

REGISTRY_PATH = os.path.join(_ROOT, "config", "source_accounts", "default_sources.json")

REQUIRED_FIELDS = [
    "source_id", "source_name", "source_platform", "source_handle",
    "target_account_ids", "active", "rights_policy", "media_policy",
    "allow_download", "allow_cut", "allow_upload",
    "auto_priority_change_allowed",
]

VALID_RIGHTS_POLICIES = {"reference_only", "approved_media", "own_media", "unknown", "do_not_use"}
VALID_MEDIA_POLICIES = {"do_not_download", "approved_media_only", "plan_only"}


def _load_sources() -> list[dict]:
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("sources", [])


def test_required_fields():
    sources = _load_sources()
    assert sources, "sources リストが空です"
    failed = []
    for s in sources:
        sid = s.get("source_id", "?")
        missing = [f for f in REQUIRED_FIELDS if f not in s]
        if missing:
            failed.append(f"{sid}: 必須フィールド不足 {missing}")
    assert not failed, "\n".join(failed)
    print(f"  [PASS] 必須フィールド確認 ({len(sources)}件)")


def test_valid_policies():
    sources = _load_sources()
    failed = []
    for s in sources:
        sid = s.get("source_id", "?")
        rp = s.get("rights_policy", "")
        mp = s.get("media_policy", "")
        if rp not in VALID_RIGHTS_POLICIES:
            failed.append(f"{sid}: 不正な rights_policy={repr(rp)}")
        if mp and mp not in VALID_MEDIA_POLICIES:
            failed.append(f"{sid}: 不正な media_policy={repr(mp)}")
    assert not failed, "\n".join(failed)
    print(f"  [PASS] rights_policy / media_policy 値確認")


def test_beauty_account_inactive():
    sources = _load_sources()
    failed = []
    for s in sources:
        if "beauty_account" in s.get("target_account_ids", []):
            if s.get("active", False):
                failed.append(f"{s['source_id']}: beauty_account ソースが active=true になっています")
    assert not failed, "\n".join(failed)
    print(f"  [PASS] beauty_account ソースは全て active=false")


def test_download_requires_approved_media():
    sources = _load_sources()
    failed = []
    approved = {"approved_media", "own_media"}
    for s in sources:
        sid = s.get("source_id", "?")
        rp = s.get("rights_policy", "")
        if s.get("allow_download") and rp not in approved:
            failed.append(f"{sid}: allow_download=true だが rights_policy={repr(rp)} (approved_media/own_media のみ許可)")
        if s.get("allow_cut") and rp not in approved:
            failed.append(f"{sid}: allow_cut=true だが rights_policy={repr(rp)}")
        if s.get("allow_upload") and rp not in approved:
            failed.append(f"{sid}: allow_upload=true だが rights_policy={repr(rp)}")
    assert not failed, "\n".join(failed)
    print(f"  [PASS] allow_download/cut/upload と rights_policy の整合性確認")


def test_auto_priority_change_disabled():
    sources = _load_sources()
    failed = []
    for s in sources:
        if s.get("auto_priority_change_allowed", False):
            failed.append(f"{s['source_id']}: auto_priority_change_allowed=true (禁止)")
    assert not failed, "\n".join(failed)
    print(f"  [PASS] auto_priority_change_allowed=false 確認")


def test_source_ids_unique():
    sources = _load_sources()
    ids = [s.get("source_id", "") for s in sources]
    duplicates = [sid for sid in ids if ids.count(sid) > 1]
    assert not duplicates, f"source_id 重複: {set(duplicates)}"
    print(f"  [PASS] source_id ユニーク確認 ({len(sources)}件)")


def test_target_account_ids_known():
    sources = _load_sources()
    known = {"night_scout", "liver_manager", "beauty_account"}
    failed = []
    for s in sources:
        sid = s.get("source_id", "?")
        for tgt in s.get("target_account_ids", []):
            if tgt not in known:
                failed.append(f"{sid}: 未知の target_account_id={repr(tgt)}")
    assert not failed, "\n".join(failed)
    print(f"  [PASS] target_account_ids 確認")


def main():
    tests = [
        test_required_fields,
        test_valid_policies,
        test_beauty_account_inactive,
        test_download_requires_approved_media,
        test_auto_priority_change_disabled,
        test_source_ids_unique,
        test_target_account_ids_known,
    ]
    passed = 0
    failed = 0
    print(f"\n=== test_source_intake_schema ===")
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
