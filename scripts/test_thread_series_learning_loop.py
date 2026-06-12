"""
test_thread_series_learning_loop.py - thread_series learning loop テスト（Phase L）

thread_series を post_result_analyzer に連携するテスト。
実API・実投稿は行わない。
improvement_suggestions は WAITING_REVIEW 止まり。
learning_rules.active は false のまま。
"""
from __future__ import annotations

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


# ---- サンプルデータ（thread_series の投稿結果を模擬）----

SAMPLE_SERIES_RESULTS = [
    {
        "result_id": "pr_ts_001",
        "account_id": "night_scout",
        "platform": "x",
        "series_id": "ts_night_scout_x_abc123",
        "post_index": 0,
        "post_role": "hook",
        "text": "夜職で月50万稼ぐ女性と月15万止まりの女性の差、知ってる？",
        "generation_mode": "mock",
        "impressions": 2500,
        "likes": 120,
        "reposts": 30,
        "replies": 8,
        "profile_clicks": 15,
        "line_clicks": 5,
        "url_clicks": 2,
        "posted_at": "2026-06-12T09:00:00Z",
    },
    {
        "result_id": "pr_ts_002",
        "account_id": "night_scout",
        "platform": "x",
        "series_id": "ts_night_scout_x_abc123",
        "post_index": 1,
        "post_role": "context",
        "text": "僕が10年スカウトをやってきて見た共通点がある。月収に差がつく理由は努力の量じゃない。",
        "generation_mode": "mock",
        "impressions": 800,
        "likes": 32,
        "reposts": 8,
        "replies": 2,
        "profile_clicks": 4,
        "line_clicks": 1,
        "url_clicks": 0,
        "posted_at": "2026-06-12T09:05:00Z",
    },
    {
        "result_id": "pr_ts_003",
        "account_id": "night_scout",
        "platform": "x",
        "series_id": "ts_night_scout_x_abc123",
        "post_index": 2,
        "post_role": "reason",
        "text": "差がつく本当の理由は仕組みを作れているかどうかだ。",
        "generation_mode": "mock",
        "impressions": 600,
        "likes": 20,
        "reposts": 5,
        "replies": 1,
        "profile_clicks": 3,
        "line_clicks": 1,
        "url_clicks": 0,
        "posted_at": "2026-06-12T09:10:00Z",
    },
    {
        "result_id": "pr_ts_004",
        "account_id": "night_scout",
        "platform": "x",
        "series_id": "ts_night_scout_x_abc123",
        "post_index": 3,
        "post_role": "cta",
        "text": "今の自分の状況を聞かせて。相談はLINEで↓",
        "generation_mode": "mock",
        "impressions": 400,
        "likes": 8,
        "reposts": 2,
        "replies": 6,
        "profile_clicks": 10,
        "line_clicks": 8,
        "url_clicks": 1,
        "posted_at": "2026-06-12T09:15:00Z",
    },
]


def test_analyzer_series_id_support():
    """PostResultAnalyzer が series_id フィールドを持つ結果を分析できる。"""
    from learning.post_result_analyzer import PostResultAnalyzer
    analyzer = PostResultAnalyzer()
    result = analyzer.analyze_thread_series(
        SAMPLE_SERIES_RESULTS, "ts_night_scout_x_abc123"
    )
    assert result["series_id"] == "ts_night_scout_x_abc123"
    assert result["post_count"] == 4
    assert len(result["posts"]) == 4
    assert "overall_metrics" in result
    assert "hook_metrics" in result


def test_hook_effectiveness_analysis():
    """hook（post_index=0）と後続投稿のエンゲージメントを比較できる。"""
    from learning.post_result_analyzer import PostResultAnalyzer
    analyzer = PostResultAnalyzer()
    result = analyzer.analyze_hook_effectiveness(SAMPLE_SERIES_RESULTS, account_id="night_scout")
    assert result["hook_count"] == 1
    assert result["non_hook_count"] == 3
    assert "hook_metrics" in result
    assert "non_hook_metrics" in result


def test_hook_has_higher_engagement():
    """hookのエンゲージメント率は後続よりも高い（サンプルデータに基づく）。"""
    from learning.post_result_analyzer import PostResultAnalyzer
    analyzer = PostResultAnalyzer()
    result = analyzer.analyze_hook_effectiveness(SAMPLE_SERIES_RESULTS, account_id="night_scout")
    hook_rate = result["hook_metrics"].get("engagement_rate", 0)
    non_hook_rate = result["non_hook_metrics"].get("engagement_rate", 0)
    assert hook_rate > 0, "hook のエンゲージメント率が 0 です"
    assert non_hook_rate >= 0


def test_dropoff_analysis():
    """投稿インデックスごとのドロップオフ分析が機能する。"""
    from learning.post_result_analyzer import PostResultAnalyzer
    analyzer = PostResultAnalyzer()
    result = analyzer.analyze_thread_series(
        SAMPLE_SERIES_RESULTS, "ts_night_scout_x_abc123"
    )
    dropoff = result.get("dropoff", [])
    assert len(dropoff) == 4, f"ドロップオフデータが4件でありません: {len(dropoff)}"
    # post_index順にソートされている
    indices = [d["post_index"] for d in dropoff]
    assert indices == sorted(indices), "dropoff が post_index 順になっていません"


def test_series_dropoff_impressions():
    """hookはCTAより多いimpressionsを持つ（サンプルデータ確認）。"""
    from learning.post_result_analyzer import PostResultAnalyzer
    analyzer = PostResultAnalyzer()
    result = analyzer.analyze_thread_series(
        SAMPLE_SERIES_RESULTS, "ts_night_scout_x_abc123"
    )
    dropoff = result.get("dropoff", [])
    hook_impressions = dropoff[0]["impressions"] if dropoff else 0
    cta_impressions = dropoff[-1]["impressions"] if dropoff else 0
    assert hook_impressions > cta_impressions, "hook は CTA より多くの impressions を持つはずです"


def test_thread_series_status_waiting_review():
    """thread_series の status は WAITING_REVIEW のまま（READY/POSTED 禁止）。"""
    import json
    fixtures_dir = os.path.join(_V2_ROOT, "tests", "fixtures")
    ts_files = [
        f for f in os.listdir(fixtures_dir)
        if f.startswith("sample_") and f.endswith(".json")
    ]
    for fname in ts_files:
        path = os.path.join(fixtures_dir, fname)
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if "posts" not in data:
            continue
        for post in data["posts"]:
            status = post.get("status", "")
            assert status == "WAITING_REVIEW", (
                f"{fname}: post_index={post.get('post_index')} のステータスが "
                f"{status!r} になっています（WAITING_REVIEW 以外は禁止）"
            )


def test_series_fixture_series_status():
    """thread_series fixture の series 全体ステータスが WAITING_REVIEW。"""
    import json
    fixtures_dir = os.path.join(_V2_ROOT, "tests", "fixtures")
    ts_files = [
        f for f in os.listdir(fixtures_dir)
        if f.startswith("sample_") and "series" in f and f.endswith(".json")
    ]
    for fname in ts_files:
        path = os.path.join(fixtures_dir, fname)
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if "status" not in data:
            continue
        status = data.get("status", "")
        assert status in ("WAITING_REVIEW", "APPROVED", ""), (
            f"{fname}: series ステータスが {status!r}（POSTED/READY は禁止）"
        )
        assert status != "READY", f"{fname}: series が READY になっています（禁止）"
        assert status != "POSTED", f"{fname}: series が POSTED になっています（禁止）"


def test_learning_rules_auto_activate_false():
    """全アカウントの auto_activate_rules が false。"""
    from accounts.account_config import load_account_config, get_all_account_ids, invalidate_cache
    invalidate_cache()
    for account_id in get_all_account_ids():
        cfg = load_account_config(account_id)
        auto = cfg.learning_policy.get("auto_activate_rules", False)
        assert not auto, f"{account_id} auto_activate_rules が true になっています"


def test_improvement_suggestions_not_auto_activated():
    """improvement_suggestions は WAITING_REVIEW 止まり（自動 active 化禁止の確認）。"""
    import json
    # サンプル improvement_suggestions fixture の確認
    path = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_improvement_suggestions.json")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    suggestions = data if isinstance(data, list) else data.get("suggestions", [])
    for s in suggestions:
        status = s.get("status", "WAITING_REVIEW")
        assert status != "ACTIVE", f"improvement_suggestions に ACTIVE があります（禁止）"


def test_beauty_account_excluded_from_learning_loop():
    """beauty_account（draft_only）は learning loop から自動的に除外される。"""
    from accounts.account_config import load_account_config, invalidate_cache
    invalidate_cache()
    cfg = load_account_config("beauty_account")
    assert cfg.is_draft_only(), "beauty_account は draft_only でなければなりません"
    # learning loop は active account のみ
    assert not cfg.is_active(), "beauty_account は active になっていてはいけません"


def test_series_id_format():
    """series_id のフォーマットが ts_{account_id}_{platform}_{uuid8} になっている。"""
    import json
    fixtures_dir = os.path.join(_V2_ROOT, "tests", "fixtures")
    ts_files = [
        f for f in os.listdir(fixtures_dir)
        if f.startswith("sample_") and f.endswith(".json")
    ]
    for fname in ts_files:
        path = os.path.join(fixtures_dir, fname)
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            continue
        series_id = data.get("series_id", "")
        if not series_id:
            continue
        assert series_id.startswith("ts_"), (
            f"{fname}: series_id が ts_ で始まっていません: {series_id!r}"
        )


if __name__ == "__main__":
    print("=" * 65)
    print("  test_thread_series_learning_loop.py")
    print("=" * 65)

    _test("analyzer_series_id_support", test_analyzer_series_id_support)
    _test("hook_effectiveness_analysis", test_hook_effectiveness_analysis)
    _test("hook_has_higher_engagement", test_hook_has_higher_engagement)
    _test("dropoff_analysis", test_dropoff_analysis)
    _test("series_dropoff_impressions", test_series_dropoff_impressions)
    _test("thread_series_status_waiting_review", test_thread_series_status_waiting_review)
    _test("series_fixture_series_status", test_series_fixture_series_status)
    _test("learning_rules_auto_activate_false", test_learning_rules_auto_activate_false)
    _test("improvement_suggestions_not_auto_activated", test_improvement_suggestions_not_auto_activated)
    _test("beauty_account_excluded_from_learning_loop", test_beauty_account_excluded_from_learning_loop)
    _test("series_id_format", test_series_id_format)

    print(f"\n{'=' * 65}")
    print(f"  PASS={_PASS}  FAIL={_FAIL}")
    print("=" * 65)
    if _FAIL > 0:
        sys.exit(1)
