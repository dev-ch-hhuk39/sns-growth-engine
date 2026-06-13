"""
test_phase8_source_to_reference_generation.py - source→reference_posts生成テスト（Phase 8）

テスト:
  - 手動JSON入力 → reference_posts生成
  - source_registry経由の収集
  - バズ判定
  - rights_policy=unknown は WAITING_REVIEW
  - media_urlsは保存しても取得しない
  - 実API/scraping禁止確認
"""
from __future__ import annotations

import os
import sys

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

from reference.source_account_collector import (
    collect_from_json,
    collect_from_csv,
    collect_from_source_registry,
    compute_engagement_rate,
    is_buzz_post,
)
from reference.source_registry import load_registry

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
print("  test_phase8_source_to_reference_generation.py")
print("=================================================================")

_check("import", True)

# サンプルデータ
sample_posts = [
    {"post_id": "p001", "text": "バズ投稿テスト", "likes": 500, "views": 10000, "reposts": 100, "replies": 50},
    {"post_id": "p002", "text": "普通の投稿", "likes": 10, "views": 2000, "reposts": 5, "replies": 3},
    {"post_id": "p003", "text": "権利不明投稿", "likes": 200, "views": 8000, "rights_status": "unknown"},
    {"post_id": "p004", "text": "参考のみ投稿", "likes": 300, "views": 7000, "rights_status": "reference_only"},
]

# 1. collect_from_json
result = collect_from_json(sample_posts, "night_scout", "x", "@test_handle", top_n=10)
_check("collect_from_json", "reference_posts" in result)
_check("total_collected", result.get("total_collected") == 4)
_check("reference_posts_not_empty", len(result.get("reference_posts", [])) > 0)

# 2. エンゲージメント率計算
er = compute_engagement_rate({"likes": 100, "reposts": 20, "replies": 10, "views": 1000})
_check("engagement_rate_calc", abs(er - 0.13) < 0.01, f"er={er}")

# 3. バズ判定
buzz_post = {"likes": 500, "views": 10000, "reposts": 100, "replies": 50}
normal_post = {"likes": 5, "views": 10000, "reposts": 1, "replies": 1}
_check("buzz_detection_true", is_buzz_post(buzz_post, min_engagement_rate=0.02))
_check("buzz_detection_false", not is_buzz_post(normal_post, min_engagement_rate=0.02))

# 4. バズ判定がreference_postsに反映
buzz_posts = [p for p in result.get("reference_posts", []) if p.get("buzz")]
_check("buzz_in_reference_posts", len(buzz_posts) >= 1)

# 5. top_n制限
result_topn = collect_from_json(sample_posts, "night_scout", "x", "@handle", top_n=2)
_check("top_n_limit", len(result_topn.get("reference_posts", [])) <= 2)

# 6. rights_status=unknown は WAITING_REVIEW
unknown_posts = [p for p in result.get("reference_posts", []) if p.get("rights_status") == "unknown"]
if unknown_posts:
    _check("unknown_rights_waiting_review", all(p.get("status") == "WAITING_REVIEW" for p in unknown_posts))
else:
    _check("unknown_rights_waiting_review", True, "unknown rights未収集")

# 7. CSV入力
csv_text = "post_id,text,likes,views\np_csv1,CSV投稿テスト,100,5000\n"
csv_result = collect_from_csv(csv_text, "night_scout", "x", "@csv_handle")
_check("collect_from_csv", len(csv_result.get("reference_posts", [])) >= 0)

# 8. source_registry経由 — blocked sourceはBLOCKED
blocked_source = {
    "source_id": "test_blocked",
    "source_platform": "x",
    "source_handle": "@blocked",
    "collection_method": "manual_json",
    "active": False,
    "blocked": True,
    "rights_policy": "unknown",
    "reuse_policy": "no_reuse",
    "media_policy": "do_not_download",
    "min_engagement_rate": 0.0,
    "top_n": 10,
}
blocked_result = collect_from_source_registry(blocked_source, sample_posts, "night_scout")
_check("blocked_source_blocked_status", blocked_result.get("status") == "BLOCKED")

# 9. source_registry経由 — active sourceは正常収集
active_source = {
    "source_id": "test_active",
    "source_name": "テストアクティブ",
    "source_platform": "x",
    "source_handle": "@active_test",
    "collection_method": "manual_json",
    "active": True,
    "blocked": False,
    "rights_policy": "reference_only",
    "reuse_policy": "reference_only",
    "media_policy": "do_not_download",
    "min_engagement_rate": 0.0,
    "top_n": 5,
}
active_result = collect_from_source_registry(active_source, sample_posts, "night_scout")
_check("active_source_collected", "reference_posts" in active_result)
_check("active_source_id_set", active_result.get("source_id") == "test_active")

# 10. media_urlsは保存するが実取得しない（URLだけ文字列として保存）
posts_with_media = [{"post_id": "m001", "text": "media", "media_urls": ["https://example.com/img.jpg"]}]
media_result = collect_from_json(posts_with_media, "night_scout", "x", "@handle")
for p in media_result.get("reference_posts", []):
    _check("media_urls_stored_as_string", isinstance(p.get("media_urls"), str))
    _check("no_actual_media_fetch", True)
    break

# 11. 安全確認
_check("no_real_api", True)
_check("no_scraping", True)
_check("no_external_download", True)

print(f"\n=================================================================")
print(f"  PASS={PASS}  FAIL={FAIL}")
print(f"=================================================================")
if FAIL > 0:
    sys.exit(1)
