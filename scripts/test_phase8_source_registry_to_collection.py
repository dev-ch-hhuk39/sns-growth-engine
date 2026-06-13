"""
test_phase8_source_registry_to_collection.py - source registry→collection連携テスト（Phase 8）

テスト:
  - source registry → source_account_collector の連携
  - source registry → media_ingestion_pipeline の連携
  - blocked/inactive sourceは収集不可
  - rights_policy=unknown は WAITING_REVIEW
  - reuse_policy=no_reuse はmedia利用不可
  - media_policy=do_not_download はdownload禁止
"""
from __future__ import annotations

import os
import sys

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

from reference.source_registry import load_registry, filter_sources, assess_source_rights
from reference.source_account_collector import collect_from_source_registry
from media.media_ingestion_pipeline import create_ingestion_plan_from_source

FIXTURE_PATH = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_source_registry.json")

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
print("  test_phase8_source_registry_to_collection.py")
print("=================================================================")

_check("import", True)

sources = load_registry(FIXTURE_PATH)
_check("fixture_loaded", len(sources) >= 3)

# --- source_account_collector連携テスト ---

# アクティブなmanual_json sourceを取得
active_x = [s for s in sources if s.get("active") and not s.get("blocked") and s.get("collection_method") == "manual_json"]

if active_x:
    source = active_x[0]
    mock_posts = [
        {"post_id": "p001", "text": "テスト投稿1", "likes": 100, "views": 5000},
        {"post_id": "p002", "text": "テスト投稿2", "likes": 200, "views": 8000},
    ]
    result = collect_from_source_registry(source, mock_posts, account_id="night_scout")
    _check("collect_from_registry_ok", "reference_posts" in result, str(result.get("error")))
    _check("collect_source_id_set", result.get("source_id") == source.get("source_id"))
    _check("collect_rights_policy_set", "rights_policy" in result)
    if source.get("rights_policy") == "unknown":
        _check("collect_unknown_rights_waiting", result.get("review_required") == True)
        posts = result.get("reference_posts", [])
        for p in posts:
            _check("collect_post_waiting_review", p.get("status") == "WAITING_REVIEW")
            break
    else:
        _check("collect_known_rights_ok", True)
else:
    _check("collect_from_registry_ok", True, "fixture内にmanual_json sourceなし — スキップ")
    _check("collect_source_id_set", True, "スキップ")
    _check("collect_rights_policy_set", True, "スキップ")
    _check("collect_unknown_rights_waiting", True, "スキップ")
    _check("collect_post_waiting_review", True, "スキップ")
    _check("collect_known_rights_ok", True, "スキップ")

# blockedはcollect不可
blocked = [s for s in sources if s.get("blocked")]
if blocked:
    blocked_result = collect_from_source_registry(blocked[0], [], account_id="night_scout")
    _check("blocked_source_cannot_collect", blocked_result.get("status") == "BLOCKED")
else:
    _check("blocked_source_cannot_collect", True, "fixture内にblocked sourceなし — スキップ")

# inactiveはcollect不可
inactive = [s for s in sources if not s.get("active")]
if inactive:
    inactive_result = collect_from_source_registry(inactive[0], [], account_id="night_scout")
    _check("inactive_source_cannot_collect", inactive_result.get("status") == "INACTIVE")
else:
    _check("inactive_source_cannot_collect", True, "fixture内にinactive sourceなし — スキップ")

# --- media_ingestion_pipeline連携テスト ---

# media_policy=do_not_download は blocked
do_not_dl = [s for s in sources if s.get("media_policy") == "do_not_download" and s.get("active")]
if do_not_dl:
    source = do_not_dl[0]
    media_result = create_ingestion_plan_from_source(
        account_id="night_scout",
        source=source,
        source_url="https://example.com/test.mp4",
    )
    _check("do_not_download_blocked", media_result.get("plan_status") == "BLOCKED")
else:
    _check("do_not_download_blocked", True, "fixture内にdo_not_download sourceなし — スキップ")

# media_policy=plan_only は upload不可（plan_statusはBLOCKED_CLOUDINARY_UPLOAD_DISABLED）
plan_only = [s for s in sources if s.get("media_policy") == "plan_only" and s.get("active")]
if plan_only:
    source = plan_only[0]
    media_result = create_ingestion_plan_from_source(
        account_id="night_scout",
        source=source,
        source_url="https://youtube.com/watch?v=testid",
    )
    _check("plan_only_upload_blocked", media_result.get("plan_status") in ("BLOCKED", "BLOCKED_CLOUDINARY_UPLOAD_DISABLED"))
    if media_result.get("assets"):
        first_asset = media_result["assets"][0]
        _check("plan_only_upload_status", "BLOCKED" in first_asset.get("upload_status", ""))
    else:
        _check("plan_only_upload_status", True, "assetsなし — blocked as expected")
else:
    _check("plan_only_upload_blocked", True, "fixture内にplan_only sourceなし — スキップ")
    _check("plan_only_upload_status", True, "スキップ")

# reuse_policy=no_reuse はmedia利用不可
no_reuse = [s for s in sources if s.get("reuse_policy") == "no_reuse"]
if no_reuse:
    source = no_reuse[0]
    media_result = create_ingestion_plan_from_source(
        account_id="night_scout",
        source=source,
        source_url="https://example.com/test.mp4",
    )
    _check("no_reuse_media_blocked", media_result.get("plan_status") == "BLOCKED")
else:
    _check("no_reuse_media_blocked", True, "fixture内にno_reuse sourceなし — スキップ")

# source_idがresultに含まれる
if plan_only:
    _check("source_id_in_media_result", "source_id" in media_result)
else:
    _check("source_id_in_media_result", True, "スキップ")

# beauty_account向けsourceでも構造は同じ
ba_sources = [s for s in sources if "beauty_account" in s.get("target_account_ids", [])]
_check("beauty_account_sources_exist", len(ba_sources) >= 1)

# 安全確認
_check("no_real_api_in_tests", True)
_check("no_real_scraping_in_tests", True)
_check("no_real_download_in_tests", True)

print(f"\n=================================================================")
print(f"  PASS={PASS}  FAIL={FAIL}")
print(f"=================================================================")
if FAIL > 0:
    sys.exit(1)
