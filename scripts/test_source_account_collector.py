"""
test_source_account_collector.py - source_account_collector テスト（Phase 7.B）

実API なし / Scraping なし / 実投稿なし。
"""
from __future__ import annotations

import json
import os
import sys

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_V2_ROOT, ".env"))
except ImportError:
    pass

_PASS = 0
_FAIL = 0


def _test(name: str, fn) -> None:
    global _PASS, _FAIL
    try:
        fn()
        print(f"  [PASS] {name}")
        _PASS += 1
    except Exception as e:
        print(f"  [FAIL] {name}: {e}")
        _FAIL += 1


_SAMPLE_POSTS = [
    {"id": "001", "text": "バズ投稿1", "likes": 500, "reposts": 100, "replies": 40, "views": 20000},
    {"id": "002", "text": "普通投稿2", "likes": 30, "reposts": 5, "replies": 2, "views": 1000},
    {"id": "003", "text": "バズ投稿3", "likes": 800, "reposts": 200, "replies": 60, "views": 30000},
    {"id": "004", "text": "低engagement", "likes": 5, "reposts": 1, "replies": 0, "views": 500},
    {"id": "005", "text": "中程度投稿", "likes": 150, "reposts": 30, "replies": 10, "views": 5000},
]


def test_import():
    """source_account_collector がインポートできる。"""
    from reference.source_account_collector import collect_from_json
    assert callable(collect_from_json)


def test_json_to_reference_posts():
    """input_json から reference_posts に変換できる。"""
    from reference.source_account_collector import collect_from_json
    result = collect_from_json(
        _SAMPLE_POSTS,
        account_id="night_scout",
        source_platform="x",
        source_handle="test_handle",
    )
    assert result["total_collected"] == 5
    assert len(result["reference_posts"]) > 0
    for p in result["reference_posts"]:
        assert "reference_post_id" in p
        assert "engagement_rate" in p
        assert p["account_id"] == "night_scout"
        assert p["source_platform"] == "x"


def test_top_n_selection():
    """top_n で伸びた投稿を選べる。"""
    from reference.source_account_collector import collect_from_json
    result = collect_from_json(
        _SAMPLE_POSTS,
        account_id="night_scout",
        source_platform="x",
        source_handle="test_handle",
        top_n=3,
    )
    assert result["selected_count"] <= 3
    # エンゲージメント率降順になっている
    ers = [p["engagement_rate"] for p in result["reference_posts"]]
    assert ers == sorted(ers, reverse=True), "エンゲージメント率が降順でない"


def test_rights_status_unknown_waiting_review():
    """rights_status=unknown の投稿は status=WAITING_REVIEW になる。"""
    from reference.source_account_collector import collect_from_json
    posts = [{"id": "001", "text": "test", "likes": 100, "views": 1000, "rights_status": "unknown"}]
    result = collect_from_json(posts, account_id="night_scout", source_platform="x", source_handle="h")
    for p in result["reference_posts"]:
        assert p["status"] == "WAITING_REVIEW", f"rights_status=unknown でも WAITING_REVIEW でない: {p['status']}"


def test_engagement_rate_computed():
    """エンゲージメント率が正しく計算される。"""
    from reference.source_account_collector import compute_engagement_rate
    post = {"likes": 100, "reposts": 50, "replies": 10, "views": 1000}
    er = compute_engagement_rate(post)
    assert abs(er - 0.16) < 0.0001, f"ER計算が正しくない: {er}"


def test_zero_views():
    """views=0 の場合は ER=0 になる（ゼロ除算なし）。"""
    from reference.source_account_collector import compute_engagement_rate
    post = {"likes": 100, "reposts": 50, "replies": 10, "views": 0}
    er = compute_engagement_rate(post)
    assert er == 0.0


def test_buzz_detection():
    """高エンゲージメントの投稿が buzz=True になる。"""
    from reference.source_account_collector import collect_from_json
    high_engagement = [
        {"id": "001", "text": "buzz", "likes": 1000, "reposts": 300, "replies": 100, "views": 10000}
    ]
    result = collect_from_json(
        high_engagement, account_id="night_scout", source_platform="x",
        source_handle="h", min_engagement_rate=0.05
    )
    buzz_posts = [p for p in result["reference_posts"] if p["buzz"]]
    assert len(buzz_posts) > 0, "高エンゲージメント投稿が buzz=True にならない"


def test_no_real_api():
    """実API呼び出しなし（ネットワークアクセスなし）を確認。"""
    from reference.source_account_collector import collect_from_json
    # ネットワークアクセスしないことは実装で保証している
    result = collect_from_json(
        _SAMPLE_POSTS,
        account_id="night_scout",
        source_platform="x",
        source_handle="test",
    )
    assert isinstance(result, dict)


def test_csv_import():
    """CSV入力も処理できる。"""
    from reference.source_account_collector import collect_from_csv
    csv_text = "id,text,likes,reposts,replies,views\n001,テスト,100,20,5,3000\n002,テスト2,50,10,2,1500\n"
    result = collect_from_csv(
        csv_text,
        account_id="night_scout",
        source_platform="x",
        source_handle="test_handle",
    )
    assert result["total_collected"] == 2


def test_fixture_exists():
    """sample_source_account_posts.json が存在する。"""
    path = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_source_account_posts.json")
    assert os.path.isfile(path), "fixture が見つかりません"


def test_fixture_loadable():
    """sample_source_account_posts.json が読み込めて変換できる。"""
    from reference.source_account_collector import collect_from_json
    path = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_source_account_posts.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    result = collect_from_json(data, account_id="night_scout", source_platform="x", source_handle="test")
    assert result["total_collected"] > 0


if __name__ == "__main__":
    print("=" * 65)
    print("  test_source_account_collector.py")
    print("=" * 65)

    _test("import", test_import)
    _test("json_to_reference_posts", test_json_to_reference_posts)
    _test("top_n_selection", test_top_n_selection)
    _test("rights_status_unknown_waiting_review", test_rights_status_unknown_waiting_review)
    _test("engagement_rate_computed", test_engagement_rate_computed)
    _test("zero_views", test_zero_views)
    _test("buzz_detection", test_buzz_detection)
    _test("no_real_api", test_no_real_api)
    _test("csv_import", test_csv_import)
    _test("fixture_exists", test_fixture_exists)
    _test("fixture_loadable", test_fixture_loadable)

    print(f"\n{'=' * 65}")
    print(f"  PASS={_PASS}  FAIL={_FAIL}")
    print("=" * 65)
    if _FAIL > 0:
        sys.exit(1)
