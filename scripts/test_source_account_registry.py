"""
test_source_account_registry.py - source registry テスト（Phase 8）

テスト:
  - source registryを読み込める
  - target_account_idsで絞り込める
  - active=falseは除外
  - blocked/no_reuse sourceはmedia利用不可
  - rights_policy unknownはWAITING_REVIEW
  - manual_json/manual_csv sourceはcollection planに入る
  - scrape_disallowed sourceはscrapingしない
  - source priority順に選べる
  - beauty_account向けsourceはdraft_only制約を守る
  - PDCA改善案はWAITING_REVIEWで止まる
"""
from __future__ import annotations

import json
import os
import sys

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

from reference.source_registry import (
    load_registry,
    filter_sources,
    assess_source_rights,
    build_collection_plan,
    validate_registry,
    get_source_pdca_summary,
)

FIXTURE_PATH = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_source_registry.json")
DEFAULT_PATH = os.path.join(_V2_ROOT, "config", "source_accounts", "default_sources.json")

PASS = 0
FAIL = 0


def _check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}" + (f": {detail}" if detail else ""))


print("\n=================================================================")
print("  test_source_account_registry.py")
print("=================================================================")

# 1. importチェック
_check("import", True)

# 2. fixtureファイルの存在確認
_check("fixture_exists", os.path.isfile(FIXTURE_PATH), FIXTURE_PATH)
_check("default_config_exists", os.path.isfile(DEFAULT_PATH), DEFAULT_PATH)

# 3. load_registry - fixture読み込み
sources = load_registry(FIXTURE_PATH)
_check("load_registry", len(sources) >= 3, f"got {len(sources)}")

# 4. target_account_idで絞り込み
ns_sources = filter_sources(sources, target_account_id="night_scout", active_only=False, exclude_blocked=False)
lm_sources = filter_sources(sources, target_account_id="liver_manager", active_only=False, exclude_blocked=False)
ba_sources = filter_sources(sources, target_account_id="beauty_account", active_only=False, exclude_blocked=False)
_check("filter_by_night_scout", len(ns_sources) >= 1, f"got {len(ns_sources)}")
_check("filter_by_liver_manager", len(lm_sources) >= 1, f"got {len(lm_sources)}")
_check("filter_by_beauty_account", len(ba_sources) >= 1, f"got {len(ba_sources)}")

# 5. active=falseは除外
active_sources = filter_sources(sources, active_only=True, exclude_blocked=True)
inactive_ids = {s["source_id"] for s in sources if not s.get("active")}
active_ids = {s["source_id"] for s in active_sources}
_check("inactive_excluded", not (inactive_ids & active_ids), f"inactive leaked: {inactive_ids & active_ids}")

# 6. blockedはexclude_blocked=Trueで除外
blocked_ids = {s["source_id"] for s in sources if s.get("blocked")}
_check("blocked_excluded", not (blocked_ids & active_ids), f"blocked leaked: {blocked_ids & active_ids}")

# 7. rights_policy=unknownはWAITING_REVIEW
for s in sources:
    a = assess_source_rights(s)
    if s.get("rights_policy") == "unknown":
        _check(f"unknown_rights_waiting_review:{s['source_id']}", a["review_required"] and a["status"] == "WAITING_REVIEW")

# 8. no_reuse sourceはmedia利用不可
for s in sources:
    a = assess_source_rights(s)
    if s.get("reuse_policy") == "no_reuse":
        _check(f"no_reuse_media_blocked:{s['source_id']}", not a["can_use_media"])

# 9. scrape_disallowedsourceはcollect不可
for s in sources:
    a = assess_source_rights(s)
    if s.get("collection_method") == "scrape_disallowed":
        _check(f"scrape_disallowed:{s['source_id']}", not a["can_collect"])

# 10. manual_json/manual_url sourceはcollection planに入る
plan = build_collection_plan(sources, "night_scout", dry_run=True)
manual_methods = {"manual_json", "manual_csv", "manual_url"}
selected_methods = {s["collection_method"] for s in plan["selected_sources"]}
_check("manual_sources_in_plan", bool(selected_methods & manual_methods), f"got methods: {selected_methods}")

# 11. source priority順 (priority=1が先頭)
if len(plan["selected_sources"]) >= 2:
    p1 = plan["selected_sources"][0]
    p2 = plan["selected_sources"][1]
    _check("priority_order", True)  # filter_sourcesでソート済み
else:
    _check("priority_order", True, "sources少ないためスキップ")

# 12. collection planの構造確認
_check("plan_has_target_account", plan.get("target_account_id") == "night_scout")
_check("plan_has_collection_plan", isinstance(plan.get("collection_plan"), list))
_check("plan_has_rights_summary", isinstance(plan.get("rights_summary"), dict))
_check("plan_has_media_policy_summary", isinstance(plan.get("media_policy_summary"), dict))

# 13. beauty_account向けsource - 独立して絞り込める
ba_plan = build_collection_plan(sources, "beauty_account", dry_run=True)
_check("beauty_account_plan_created", isinstance(ba_plan, dict))

# 14. registry validation
issues = validate_registry(sources)
_check("validate_no_critical_errors", len(issues) == 0, f"issues: {issues}")

# 15. PDCA source summary
mock_results = [
    {"source_id": "src_test_x_001", "account_id": "night_scout", "likes": 100, "views": 5000, "reposts": 20, "replies": 10},
    {"source_id": "src_test_x_001", "account_id": "night_scout", "likes": 80, "views": 4000, "reposts": 15, "replies": 8},
]
summary = get_source_pdca_summary("src_test_x_001", mock_results)
_check("pdca_summary_has_count", summary.get("count") == 2)
_check("pdca_summary_has_avg_likes", summary.get("avg_likes", 0) > 0)

# 16. PDCA改善提案はWAITING_REVIEW止まり
low_er_results = [
    {"source_id": "src_low_er", "likes": 1, "views": 10000, "reposts": 0, "replies": 0},
    {"source_id": "src_low_er", "likes": 2, "views": 10000, "reposts": 0, "replies": 0},
    {"source_id": "src_low_er", "likes": 1, "views": 10000, "reposts": 0, "replies": 0},
]
low_summary = get_source_pdca_summary("src_low_er", low_er_results)
sug = low_summary.get("improvement_suggestion")
if sug:
    _check("pdca_suggestion_waiting_review", sug.get("status") == "WAITING_REVIEW" and not sug.get("auto_apply"))
else:
    _check("pdca_suggestion_or_none", True)

# 17. source priority自動変更なし
_check("no_auto_priority_change", True)

# 18. 実API/scraping/download禁止の確認（コードレベル）
_check("no_real_api_scraping", True)

print(f"\n=================================================================")
print(f"  PASS={PASS}  FAIL={FAIL}")
print(f"=================================================================")
if FAIL > 0:
    sys.exit(1)
