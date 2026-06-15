#!/usr/bin/env python3
"""test_phase13_production_sources.py"""
from __future__ import annotations
import os, sys, json
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

results = []
SOURCES_FILE = os.path.join(_ROOT, "config", "source_accounts", "production_sources.example.json")

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append((name, status, detail))
    print(f"  {'✓' if condition else '✗'} [{status}] {name}" + (f": {detail}" if detail else ""))


def main():
    print("=== Phase 13: production_sources.example.json テスト ===\n")

    print("[1] ファイル存在確認")
    check("ファイルが存在する", os.path.isfile(SOURCES_FILE), SOURCES_FILE)

    print("\n[2] JSON として parse 可能")
    try:
        with open(SOURCES_FILE, encoding="utf-8") as f:
            data = json.load(f)
        check("JSON parse OK", True)
    except Exception as e:
        check("JSON parse", False, str(e))
        sys.exit(1)

    sources = [s for s in data.get("sources", []) if "source_id" in s]
    print(f"\n[3] source エントリ数 (source_id を持つもの)")
    check("46件以上", len(sources) >= 46, f"実際: {len(sources)}件")

    print("\n[4] 全ソースの必須フィールド")
    required_fields = ["source_id", "source_platform", "source_url", "target_account_ids",
                       "candidate_status", "active", "fetch_enabled"]
    for field in required_fields:
        missing = [s["source_id"] for s in sources if field not in s]
        check(f"全ソースに {field} あり", not missing, f"欠損: {missing[:3]}")

    print("\n[5] active=False / fetch_enabled=False が全ソースで設定されている")
    active_true = [s["source_id"] for s in sources if s.get("active") is True]
    fetch_true = [s["source_id"] for s in sources if s.get("fetch_enabled") is True]
    check("active=False (全件)", not active_true, f"active=true: {active_true}")
    check("fetch_enabled=False (全件)", not fetch_true, f"fetch_enabled=true: {fetch_true}")

    print("\n[6] candidate_status が有効値のみ")
    valid_statuses = {"candidate", "disabled", "active", "rejected"}
    invalid = [s["source_id"] for s in sources
               if s.get("candidate_status") not in valid_statuses]
    check("candidate_status 全件有効", not invalid, f"無効: {invalid}")

    print("\n[7] URL が https:// で始まる（https: 切断なし）")
    broken_urls = [s["source_id"] for s in sources
                   if s.get("source_url", "").startswith("https:")
                   and not s["source_url"].startswith("https://")]
    check("全ソースURL正常", not broken_urls, f"壊れたURL: {broken_urls}")

    print("\n[8] night_scout ソース (9X + 9YT = 18件)")
    ns = [s for s in sources if "night_scout" in s.get("target_account_ids", [])]
    ns_x = [s for s in ns if s["source_platform"] == "x"]
    ns_yt = [s for s in ns if s["source_platform"] == "youtube"]
    check("night_scout X: 9件", len(ns_x) == 9, f"実際: {len(ns_x)}")
    check("night_scout YT: 9件", len(ns_yt) == 9, f"実際: {len(ns_yt)}")

    print("\n[9] liver_manager ソース (7YT + 6note = 13件)")
    lm = [s for s in sources if "liver_manager" in s.get("target_account_ids", [])]
    lm_yt = [s for s in lm if s["source_platform"] == "youtube"]
    lm_note = [s for s in lm if s["source_platform"] == "note"]
    check("liver_manager YT: 7件", len(lm_yt) == 7, f"実際: {len(lm_yt)}")
    check("liver_manager note: 6件", len(lm_note) == 6, f"実際: {len(lm_note)}")

    print("\n[10] beauty_account ソース (10YT + 7TikTok + 6X = 23件)")
    ba = [s for s in sources if "beauty_account" in s.get("target_account_ids", [])]
    ba_yt = [s for s in ba if s["source_platform"] == "youtube"]
    ba_tt = [s for s in ba if s["source_platform"] == "tiktok"]
    ba_x = [s for s in ba if s["source_platform"] == "x"]
    check("beauty_account YT: 10件", len(ba_yt) == 10, f"実際: {len(ba_yt)}")
    check("beauty_account TikTok: 7件", len(ba_tt) == 7, f"実際: {len(ba_tt)}")
    check("beauty_account X: 6件", len(ba_x) == 6, f"実際: {len(ba_x)}")

    print("\n[11] beauty_account TikTok/X は全て disabled")
    ba_tt_disabled = [s for s in ba_tt if s.get("candidate_status") == "disabled"]
    ba_x_disabled = [s for s in ba_x if s.get("candidate_status") == "disabled"]
    check("beauty_account TikTok 全て disabled", len(ba_tt_disabled) == len(ba_tt))
    check("beauty_account X 全て disabled", len(ba_x_disabled) == len(ba_x))

    print("\n[12] beauty_account YouTube は candidate")
    ba_yt_cand = [s for s in ba_yt if s.get("candidate_status") == "candidate"]
    check("beauty_account YT 全て candidate", len(ba_yt_cand) == len(ba_yt))

    print("\n[13] beauty_account の subject_policy に female_subject_required=True")
    ba_no_female_check = [s["source_id"] for s in ba
                          if not s.get("subject_policy", {}).get("female_subject_required")]
    check("beauty_account 全件 female_subject_required", not ba_no_female_check, str(ba_no_female_check[:3]))

    print("\n[14] beauty_account allow_cut=False / allow_upload=False")
    ba_cut = [s["source_id"] for s in ba if s.get("allow_cut") is not False]
    ba_upload = [s["source_id"] for s in ba if s.get("allow_upload") is not False]
    check("beauty_account allow_cut=False 全件", not ba_cut, str(ba_cut[:3]))
    check("beauty_account allow_upload=False 全件", not ba_upload, str(ba_upload[:3]))

    print("\n[15] source_id の一意性")
    ids = [s["source_id"] for s in sources]
    check("source_id 重複なし", len(ids) == len(set(ids)))

    print("\n--- 結果 ---")
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    print(f"PASS: {passed} / FAIL: {failed}")
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
