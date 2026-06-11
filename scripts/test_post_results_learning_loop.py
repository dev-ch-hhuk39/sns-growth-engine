"""
test_post_results_learning_loop.py - Phase 5.4 テストスイート

Phase 5.4: posted_results → learning loop 基盤テスト

実行方法: python scripts/test_post_results_learning_loop.py
"""
from __future__ import annotations

import csv
import io
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

# ============================================================
# テストフレームワーク
# ============================================================

_PASS = 0
_FAIL = 0
_tests: list[tuple[str, bool, str]] = []


def _test(name: str, fn) -> None:
    global _PASS, _FAIL
    try:
        fn()
        _PASS += 1
        _tests.append((name, True, ""))
    except Exception as e:
        _FAIL += 1
        _tests.append((name, False, str(e)))


# ============================================================
# サンプルデータ
# ============================================================

SAMPLE_RESULTS = [
    {
        "result_id": "pr_test_001",
        "account_id": "night_scout",
        "platform": "x",
        "posted_at": "2025-06-01T09:00:00Z",
        "text": "テスト投稿1",
        "generation_mode": "video_clip_reference",
        "impressions": 1200,
        "likes": 48,
        "reposts": 12,
        "replies": 3,
        "profile_clicks": 5,
        "line_clicks": 2,
        "url_clicks": 8,
    },
    {
        "result_id": "pr_test_002",
        "account_id": "night_scout",
        "platform": "x",
        "posted_at": "2025-06-02T10:00:00Z",
        "text": "テスト投稿2",
        "generation_mode": "reference_based",
        "impressions": 800,
        "likes": 20,
        "reposts": 5,
        "replies": 1,
        "profile_clicks": 2,
        "line_clicks": 0,
        "url_clicks": 3,
    },
    {
        "result_id": "pr_test_003",
        "account_id": "night_scout",
        "platform": "x",
        "posted_at": "2025-06-03T11:00:00Z",
        "text": "テスト投稿3（高エンゲージメント）",
        "generation_mode": "video_clip_reference",
        "impressions": 2500,
        "likes": 150,
        "reposts": 40,
        "replies": 10,
        "profile_clicks": 20,
        "line_clicks": 8,
        "url_clicks": 25,
    },
]


# ============================================================
# PostResultAnalyzer テスト
# ============================================================

print("\n=== PostResultAnalyzer ===")


def t_analyzer_importable():
    from learning.post_result_analyzer import PostResultAnalyzer
    assert PostResultAnalyzer is not None


def t_analyzer_analyze_basic():
    from learning.post_result_analyzer import PostResultAnalyzer
    analyzer = PostResultAnalyzer()
    result = analyzer.analyze(SAMPLE_RESULTS, account_id="night_scout")
    assert result["posted_count"] == 3
    assert "metrics" in result
    assert result["metrics"]["count"] == 3


def t_analyzer_empty_results():
    from learning.post_result_analyzer import PostResultAnalyzer
    analyzer = PostResultAnalyzer()
    result = analyzer.analyze([], account_id="night_scout")
    assert result["posted_count"] == 0
    assert result["metrics"] == {}


def t_analyzer_filter_by_account():
    from learning.post_result_analyzer import PostResultAnalyzer
    results_with_other = SAMPLE_RESULTS + [
        {"result_id": "other_001", "account_id": "other_account", "platform": "x",
         "posted_at": "2025-06-01T00:00:00Z", "impressions": 100, "likes": 5,
         "reposts": 1, "replies": 0, "profile_clicks": 0, "line_clicks": 0,
         "url_clicks": 0, "generation_mode": "direct"}
    ]
    analyzer = PostResultAnalyzer()
    result = analyzer.analyze(results_with_other, account_id="night_scout")
    assert result["posted_count"] == 3, "night_scout の投稿数は3であること"


def t_analyzer_engagement_rate():
    from learning.post_result_analyzer import PostResultAnalyzer
    analyzer = PostResultAnalyzer()
    result = analyzer.analyze(SAMPLE_RESULTS, account_id="night_scout")
    eng = result["metrics"]["engagement_rate"]
    assert 0 < eng < 1, f"エンゲージメント率は0〜1の範囲: {eng}"


def t_analyzer_top_bottom_posts():
    from learning.post_result_analyzer import PostResultAnalyzer
    analyzer = PostResultAnalyzer()
    result = analyzer.analyze(SAMPLE_RESULTS, account_id="night_scout")
    top = result["top_posts"]
    bottom = result["bottom_posts"]
    assert len(top) > 0, "top_postsが必要"
    assert len(bottom) > 0, "bottom_postsが必要"
    # top は高エンゲージメント
    if len(top) >= 1:
        top_imp = int(top[0].get("impressions", 0))
        top_likes = int(top[0].get("likes", 0))
        assert top_likes >= 20, f"top投稿のlikesが少なすぎる: {top_likes}"


def t_analyzer_by_generation_mode():
    from learning.post_result_analyzer import PostResultAnalyzer
    analyzer = PostResultAnalyzer()
    result = analyzer.analyze(SAMPLE_RESULTS, account_id="night_scout")
    by_mode = result["by_generation_mode"]
    assert "video_clip_reference" in by_mode, "video_clip_referenceモードが必要"
    assert "reference_based" in by_mode, "reference_basedモードが必要"
    vcr = by_mode["video_clip_reference"]
    assert vcr["count"] == 2, "video_clip_referenceは2件"


def t_analyzer_pv_cv_split():
    from learning.post_result_analyzer import PostResultAnalyzer
    analyzer = PostResultAnalyzer()
    result = analyzer.analyze(SAMPLE_RESULTS, account_id="night_scout")
    pv = result["pv_metrics"]
    cv = result["cv_metrics"]
    assert "impressions" in pv.get("total", {}), "PV系にimpressionsが必要"
    assert "likes" in cv.get("total", {}), "CV系にlikesが必要"


def t_analyzer_forbidden_conflict_detection():
    from learning.post_result_analyzer import PostResultAnalyzer
    analyzer = PostResultAnalyzer()
    conflict, detail = analyzer.detect_forbidden_conflict(
        "ギャンブルは危険です",
        ["ギャンブル", "風俗"],
        ["成人向け"],
    )
    assert conflict is True, "forbidden_keyword が含まれていれば conflict=True"
    assert "ギャンブル" in detail


def t_analyzer_no_forbidden_conflict():
    from learning.post_result_analyzer import PostResultAnalyzer
    analyzer = PostResultAnalyzer()
    conflict, detail = analyzer.detect_forbidden_conflict(
        "夜景スポットを紹介します",
        ["ギャンブル", "風俗"],
        ["成人向け"],
    )
    assert conflict is False, "forbidden に含まれなければ conflict=False"


for fn in [
    t_analyzer_importable,
    t_analyzer_analyze_basic,
    t_analyzer_empty_results,
    t_analyzer_filter_by_account,
    t_analyzer_engagement_rate,
    t_analyzer_top_bottom_posts,
    t_analyzer_by_generation_mode,
    t_analyzer_pv_cv_split,
    t_analyzer_forbidden_conflict_detection,
    t_analyzer_no_forbidden_conflict,
]:
    _test(fn.__name__, fn)


# ============================================================
# import_post_results.py テスト
# ============================================================

print("\n=== import_post_results.py ===")


def t_import_script_exists():
    p = os.path.join(_V2_ROOT, "scripts", "import_post_results.py")
    assert os.path.isfile(p), f"見つかりません: {p}"


def t_import_json_parse():
    import importlib.util
    p = os.path.join(_V2_ROOT, "scripts", "import_post_results.py")
    spec = importlib.util.spec_from_file_location("import_post_results", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    fixture = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_post_results_import.json")
    records = mod.load_input(fixture)
    assert len(records) >= 1, "JSON fixtureから読み込めること"
    assert records[0].get("account_id"), "account_idが必要"


def t_import_csv_parse():
    import importlib.util
    p = os.path.join(_V2_ROOT, "scripts", "import_post_results.py")
    spec = importlib.util.spec_from_file_location("import_post_results", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    fixture = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_post_results_import.csv")
    records = mod.load_input(fixture)
    assert len(records) >= 1, "CSV fixtureから読み込めること"


def t_import_validate_records():
    import importlib.util
    p = os.path.join(_V2_ROOT, "scripts", "import_post_results.py")
    spec = importlib.util.spec_from_file_location("import_post_results", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    test_records = [
        {"account_id": "night_scout", "platform": "x", "posted_at": "2025-06-01T00:00:00Z"},
        {"platform": "x"},  # account_id なし → エラー
    ]
    valid, errors = mod.validate_records(test_records)
    assert len(valid) == 1, "有効レコードは1件"
    assert len(errors) == 1, "エラーは1件"


def t_import_no_secret_fields():
    import importlib.util
    p = os.path.join(_V2_ROOT, "scripts", "import_post_results.py")
    spec = importlib.util.spec_from_file_location("import_post_results", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # secret フィールドが含まれていても除去される
    records = [{"account_id": "night_scout", "platform": "x",
                "posted_at": "2025-06-01T00:00:00Z",
                "x_api_secret": "should_be_removed",
                "access_token": "should_be_removed"}]
    valid, errors = mod.validate_records(records)
    if valid:
        assert "x_api_secret" not in valid[0], "secret フィールドは除去される"
        assert "access_token" not in valid[0], "secret フィールドは除去される"


def t_import_dry_run_no_sheets_write():
    p = os.path.join(_V2_ROOT, "scripts", "import_post_results.py")
    src = open(p, encoding="utf-8").read()
    assert "dry_run" in src.lower(), "dry-run制御が必要"
    assert "--dry-run" in src or "dry_run" in src, "dry-runフラグが必要"


def t_import_no_real_api():
    p = os.path.join(_V2_ROOT, "scripts", "import_post_results.py")
    src = open(p, encoding="utf-8").read()
    assert "tweepy" not in src, "X APIを呼び出してはいけない"
    assert "cloudinary.uploader" not in src, "Cloudinary APIを呼び出してはいけない"


for fn in [
    t_import_script_exists,
    t_import_json_parse,
    t_import_csv_parse,
    t_import_validate_records,
    t_import_no_secret_fields,
    t_import_dry_run_no_sheets_write,
    t_import_no_real_api,
]:
    _test(fn.__name__, fn)


# ============================================================
# analyze_post_results.py テスト
# ============================================================

print("\n=== analyze_post_results.py ===")


def t_analyze_script_exists():
    p = os.path.join(_V2_ROOT, "scripts", "analyze_post_results.py")
    assert os.path.isfile(p), f"見つかりません: {p}"


def t_analyze_no_real_api():
    p = os.path.join(_V2_ROOT, "scripts", "analyze_post_results.py")
    src = open(p, encoding="utf-8").read()
    assert "tweepy" not in src, "X APIを呼び出してはいけない"
    assert "requests.post" not in src, "実API呼び出し禁止"


for fn in [
    t_analyze_script_exists,
    t_analyze_no_real_api,
]:
    _test(fn.__name__, fn)


# ============================================================
# generate_learning_from_results.py テスト
# ============================================================

print("\n=== generate_learning_from_results.py ===")


def t_generate_script_exists():
    p = os.path.join(_V2_ROOT, "scripts", "generate_learning_from_results.py")
    assert os.path.isfile(p), f"見つかりません: {p}"


def t_generate_no_active_true():
    p = os.path.join(_V2_ROOT, "scripts", "generate_learning_from_results.py")
    src = open(p, encoding="utf-8").read()
    # active=true の自動設定が禁止されていること
    assert '"active": "true"' not in src and "'active': 'true'" not in src, \
        "active=true の自動設定禁止"
    assert '"active": True' not in src, "active=True の自動設定禁止"


def t_generate_waiting_review_status():
    p = os.path.join(_V2_ROOT, "scripts", "generate_learning_from_results.py")
    src = open(p, encoding="utf-8").read()
    assert "WAITING_REVIEW" in src, "全提案はWAITING_REVIEWで出力する"


def t_generate_no_code_rewrite():
    p = os.path.join(_V2_ROOT, "scripts", "generate_learning_from_results.py")
    src = open(p, encoding="utf-8").read()
    assert "open(" not in src or "write(" not in src or "encoding" not in src, \
        "コードファイルへの書き込みは禁止"


def t_generate_no_real_api():
    p = os.path.join(_V2_ROOT, "scripts", "generate_learning_from_results.py")
    src = open(p, encoding="utf-8").read()
    assert "tweepy" not in src, "X APIを呼び出してはいけない"


def t_generate_dry_run_default():
    p = os.path.join(_V2_ROOT, "scripts", "generate_learning_from_results.py")
    src = open(p, encoding="utf-8").read()
    assert "dry_run" in src.lower(), "dry-run制御が必要"


def t_generate_forbidden_conflict_check():
    p = os.path.join(_V2_ROOT, "scripts", "generate_learning_from_results.py")
    src = open(p, encoding="utf-8").read()
    assert "forbidden" in src.lower(), "forbidden矛盾チェックが必要"


for fn in [
    t_generate_script_exists,
    t_generate_no_active_true,
    t_generate_waiting_review_status,
    t_generate_no_code_rewrite,
    t_generate_no_real_api,
    t_generate_dry_run_default,
    t_generate_forbidden_conflict_check,
]:
    _test(fn.__name__, fn)


# ============================================================
# fixture バリデーション
# ============================================================

print("\n=== Fixture バリデーション ===")


def t_fixture_json_no_real_post_data():
    """fixture に本番投稿データが含まれていないこと。"""
    p = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_post_results_import.json")
    data = json.loads(open(p, encoding="utf-8").read())
    results = data.get("results", data) if isinstance(data, dict) else data
    for r in results:
        assert str(r.get("is_test_data", "")) == "true", \
            f"is_test_data=true が必要: {r.get('result_id')}"


def t_fixture_learning_no_active_true():
    """generated_learning fixture に active=true がないこと。"""
    p = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_generated_learning_from_results.json")
    data = json.loads(open(p, encoding="utf-8").read())
    suggestions = data.get("suggestions", [])
    for s in suggestions:
        active = str(s.get("active", "false")).lower()
        assert active == "false", f"active=false が必要: {s.get('suggestion_id')}"
        assert s.get("status") == "WAITING_REVIEW", \
            f"status=WAITING_REVIEW が必要: {s.get('suggestion_id')}"


def t_fixture_analysis_has_metrics():
    p = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_post_result_analysis.json")
    data = json.loads(open(p, encoding="utf-8").read())
    assert "metrics" in data, "metrics が必要"
    assert "by_generation_mode" in data, "by_generation_mode が必要"
    assert "pv_metrics" in data, "pv_metrics が必要"
    assert "cv_metrics" in data, "cv_metrics が必要"


for fn in [
    t_fixture_json_no_real_post_data,
    t_fixture_learning_no_active_true,
    t_fixture_analysis_has_metrics,
]:
    _test(fn.__name__, fn)


# ============================================================
# 結果出力
# ============================================================

print(f"\n{'=' * 60}")
print(f"  Phase 5.4 テスト結果: PASS={_PASS} / FAIL={_FAIL}")
print(f"{'=' * 60}")

if _FAIL > 0:
    print("\n[FAILED テスト一覧]")
    for name, ok, msg in _tests:
        if not ok:
            print(f"  FAIL: {name}")
            print(f"        {msg}")

sys.exit(0 if _FAIL == 0 else 1)
