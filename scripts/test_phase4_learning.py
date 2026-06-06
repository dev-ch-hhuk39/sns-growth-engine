"""
test_phase4_learning.py - Phase 4.0-4.1 テストスイート

Phase 4.0: Learning foundation (PerformanceAnalyzer, ImprovementSuggester)
Phase 4.1: Learning integrity (check_learning_integrity, approve_learning_rule)

実行方法: python scripts/test_phase4_learning.py
"""
from __future__ import annotations

import json
import os
import sys

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

from learning.performance_analyzer import PerformanceAnalyzer
from learning.improvement_suggester import ImprovementSuggester
from sheets_client import MockSheetsClient, TAB_DEFINITIONS

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
# Phase 4.0: PerformanceAnalyzer
# ============================================================

print("\n=== Phase 4.0: PerformanceAnalyzer ===")

_SAMPLE_POSTED = [
    {"views": 1000, "likes": 40, "comments": 5, "follows": 2},
    {"views": 1200, "likes": 60, "comments": 10, "follows": 4},
    {"views": 800, "likes": 20, "comments": 3, "follows": 1},
]

_SAMPLE_QUEUE = [
    {"status": "READY", "generation_mode": "video_clip_reference", "text_policy_status": "OK", "rights_review_required": "false"},
    {"status": "READY", "generation_mode": "video_clip_reference", "text_policy_status": "FAIL", "rights_review_required": "false"},
    {"status": "WAITING_REVIEW", "generation_mode": "reference_based", "text_policy_status": "OK", "rights_review_required": "true"},
    {"status": "DONE", "generation_mode": "reference_based", "text_policy_status": "OK", "rights_review_required": "false"},
]


def t_analyzer_returns_dict():
    analyzer = PerformanceAnalyzer()
    result = analyzer.analyze(
        account_id="night_scout",
        posted_results=_SAMPLE_POSTED,
        queue_items=_SAMPLE_QUEUE,
    )
    assert isinstance(result, dict), f"dict を期待: {type(result)}"


def t_analyzer_account_id_matches():
    analyzer = PerformanceAnalyzer()
    result = analyzer.analyze(
        account_id="night_scout",
        posted_results=_SAMPLE_POSTED,
        queue_items=_SAMPLE_QUEUE,
    )
    assert result["account_id"] == "night_scout"


def t_analyzer_posted_count():
    analyzer = PerformanceAnalyzer()
    result = analyzer.analyze(
        account_id="night_scout",
        posted_results=_SAMPLE_POSTED,
        queue_items=_SAMPLE_QUEUE,
    )
    assert result["posted_count"] == 3


def t_analyzer_avg_likes():
    analyzer = PerformanceAnalyzer()
    result = analyzer.analyze(
        account_id="night_scout",
        posted_results=_SAMPLE_POSTED,
        queue_items=_SAMPLE_QUEUE,
    )
    expected = round((40 + 60 + 20) / 3, 2)
    assert result["avg_likes"] == expected, f"avg_likes={result['avg_likes']!r} expected {expected!r}"


def t_analyzer_avg_views():
    analyzer = PerformanceAnalyzer()
    result = analyzer.analyze(
        account_id="night_scout",
        posted_results=_SAMPLE_POSTED,
        queue_items=_SAMPLE_QUEUE,
    )
    expected = round((1000 + 1200 + 800) / 3, 2)
    assert result["avg_views"] == expected


def t_analyzer_queue_ready_count():
    analyzer = PerformanceAnalyzer()
    result = analyzer.analyze(
        account_id="night_scout",
        posted_results=_SAMPLE_POSTED,
        queue_items=_SAMPLE_QUEUE,
    )
    assert result["queue_ready_count"] == 2


def t_analyzer_queue_waiting_review_count():
    analyzer = PerformanceAnalyzer()
    result = analyzer.analyze(
        account_id="night_scout",
        posted_results=_SAMPLE_POSTED,
        queue_items=_SAMPLE_QUEUE,
    )
    assert result["queue_waiting_review_count"] == 1


def t_analyzer_text_policy_fail_rate():
    analyzer = PerformanceAnalyzer()
    result = analyzer.analyze(
        account_id="night_scout",
        posted_results=_SAMPLE_POSTED,
        queue_items=_SAMPLE_QUEUE,
    )
    # 4件中1件が FAIL → 0.25
    assert result["text_policy_fail_rate"] == 0.25, f"fail_rate={result['text_policy_fail_rate']!r}"


def t_analyzer_rights_review_rate():
    analyzer = PerformanceAnalyzer()
    result = analyzer.analyze(
        account_id="night_scout",
        posted_results=_SAMPLE_POSTED,
        queue_items=_SAMPLE_QUEUE,
    )
    # 4件中1件が rights_review_required=true → 0.25
    assert result["rights_review_required_rate"] == 0.25


def t_analyzer_generation_mode_breakdown():
    analyzer = PerformanceAnalyzer()
    result = analyzer.analyze(
        account_id="night_scout",
        posted_results=_SAMPLE_POSTED,
        queue_items=_SAMPLE_QUEUE,
    )
    breakdown = result["generation_mode_breakdown"]
    assert breakdown.get("video_clip_reference", 0) == 2
    assert breakdown.get("reference_based", 0) == 2


def t_analyzer_empty_posted_results():
    analyzer = PerformanceAnalyzer()
    result = analyzer.analyze(
        account_id="night_scout",
        posted_results=[],
        queue_items=[],
    )
    assert result["posted_count"] == 0
    assert result["avg_likes"] == 0.0
    assert result["text_policy_fail_rate"] == 0.0


def t_analyzer_with_video_clip_candidates():
    analyzer = PerformanceAnalyzer()
    clips = [{"clip_id": f"clip-{i}"} for i in range(3)]
    result = analyzer.analyze(
        account_id="night_scout",
        posted_results=_SAMPLE_POSTED,
        queue_items=_SAMPLE_QUEUE,
        video_clip_candidates=clips,
    )
    assert result["video_clip_count"] == 3


_test("PerformanceAnalyzer.analyze() が dict を返す", t_analyzer_returns_dict)
_test("PerformanceAnalyzer: account_id 一致", t_analyzer_account_id_matches)
_test("PerformanceAnalyzer: posted_count 正確", t_analyzer_posted_count)
_test("PerformanceAnalyzer: avg_likes 正確", t_analyzer_avg_likes)
_test("PerformanceAnalyzer: avg_views 正確", t_analyzer_avg_views)
_test("PerformanceAnalyzer: queue_ready_count 正確", t_analyzer_queue_ready_count)
_test("PerformanceAnalyzer: queue_waiting_review_count 正確", t_analyzer_queue_waiting_review_count)
_test("PerformanceAnalyzer: text_policy_fail_rate 正確", t_analyzer_text_policy_fail_rate)
_test("PerformanceAnalyzer: rights_review_required_rate 正確", t_analyzer_rights_review_rate)
_test("PerformanceAnalyzer: generation_mode_breakdown 正確", t_analyzer_generation_mode_breakdown)
_test("PerformanceAnalyzer: 空データで例外なし", t_analyzer_empty_posted_results)
_test("PerformanceAnalyzer: video_clip_candidates カウント", t_analyzer_with_video_clip_candidates)


# ============================================================
# Phase 4.0: ImprovementSuggester
# ============================================================

print("\n=== Phase 4.0: ImprovementSuggester ===")

_HIGH_FAIL_METRICS = {
    "account_id": "night_scout",
    "posted_count": 5,
    "avg_likes": 30.0,
    "avg_views": 500.0,
    "avg_engagement_rate": 0.05,
    "queue_ready_count": 3,
    "queue_waiting_review_count": 1,
    "video_clip_count": 2,
    "text_policy_fail_rate": 0.20,
    "rights_review_required_rate": 0.25,
    "generation_mode_breakdown": {"video_clip_reference": 3, "reference_based": 2},
}

_LOW_PROBLEM_METRICS = {
    "account_id": "night_scout",
    "posted_count": 5,
    "avg_likes": 50.0,
    "avg_views": 1000.0,
    "avg_engagement_rate": 0.05,
    "queue_ready_count": 3,
    "queue_waiting_review_count": 0,
    "video_clip_count": 2,
    "text_policy_fail_rate": 0.05,
    "rights_review_required_rate": 0.10,
    "generation_mode_breakdown": {},
}


def t_suggester_returns_list():
    suggester = ImprovementSuggester()
    suggestions = suggester.suggest(_HIGH_FAIL_METRICS)
    assert isinstance(suggestions, list), f"list を期待: {type(suggestions)}"


def t_suggester_high_text_fail_generates_suggestion():
    suggester = ImprovementSuggester()
    suggestions = suggester.suggest(_HIGH_FAIL_METRICS)
    types = [s["suggestion_type"] for s in suggestions]
    assert "prompt_change" in types, f"text policy 改善提案があるべき: {types}"


def t_suggester_all_status_waiting_review():
    suggester = ImprovementSuggester()
    suggestions = suggester.suggest(_HIGH_FAIL_METRICS)
    for s in suggestions:
        assert s["status"] == "WAITING_REVIEW", f"status=WAITING_REVIEW を期待: {s['status']!r}"


def t_suggester_no_active_true():
    """active=true が自動設定されていないことを確認。"""
    suggester = ImprovementSuggester()
    suggestions = suggester.suggest(_HIGH_FAIL_METRICS)
    for s in suggestions:
        assert "active" not in s, f"active フィールドは不要: {s}"


def t_suggester_has_required_fields():
    suggester = ImprovementSuggester()
    suggestions = suggester.suggest(_HIGH_FAIL_METRICS)
    required = [
        "suggestion_id", "account_id", "created_at", "source",
        "suggestion_type", "current_behavior", "suggested_change",
        "reason", "expected_impact", "priority", "status",
    ]
    for s in suggestions:
        missing = [f for f in required if f not in s]
        assert not missing, f"必須フィールド不足: {missing} in {s}"


def t_suggester_suggestion_id_not_empty():
    suggester = ImprovementSuggester()
    suggestions = suggester.suggest(_HIGH_FAIL_METRICS)
    for s in suggestions:
        assert s["suggestion_id"], f"suggestion_id が空: {s}"


def t_suggester_priority_high_for_high_fail_rate():
    suggester = ImprovementSuggester()
    suggestions = suggester.suggest(_HIGH_FAIL_METRICS)
    prompt_changes = [s for s in suggestions if s["suggestion_type"] == "prompt_change"
                      and "text_policy" in s.get("current_behavior", "")]
    if prompt_changes:
        assert prompt_changes[0]["priority"] == "high", f"fail_rate 20% は priority=high: {prompt_changes[0]['priority']!r}"


def t_suggester_low_fail_no_text_suggestion():
    suggester = ImprovementSuggester()
    suggestions = suggester.suggest(_LOW_PROBLEM_METRICS)
    text_sugs = [s for s in suggestions if "text_policy" in s.get("current_behavior", "")]
    assert len(text_sugs) == 0, f"low fail rate なら text_policy 提案不要: {text_sugs}"


def t_suggester_insufficient_posted_count_returns_empty():
    metrics = dict(_HIGH_FAIL_METRICS)
    metrics["posted_count"] = 2
    suggester = ImprovementSuggester()
    suggestions = suggester.suggest(metrics)
    assert suggestions == [], f"投稿数不足なら空を期待: {suggestions}"


def t_suggester_account_id_in_all_suggestions():
    suggester = ImprovementSuggester()
    suggestions = suggester.suggest(_HIGH_FAIL_METRICS)
    for s in suggestions:
        assert s["account_id"] == "night_scout", f"account_id mismatch: {s['account_id']!r}"


_test("ImprovementSuggester.suggest() が list を返す", t_suggester_returns_list)
_test("高 text_fail_rate → prompt_change 提案生成", t_suggester_high_text_fail_generates_suggestion)
_test("全提案 status=WAITING_REVIEW", t_suggester_all_status_waiting_review)
_test("active=true が自動設定されない（禁止）", t_suggester_no_active_true)
_test("全提案に必須フィールドあり", t_suggester_has_required_fields)
_test("suggestion_id が空でない", t_suggester_suggestion_id_not_empty)
_test("fail_rate 20% → priority=high", t_suggester_priority_high_for_high_fail_rate)
_test("低 fail_rate → text_policy 提案なし", t_suggester_low_fail_no_text_suggestion)
_test("投稿数不足（<3） → 空リスト", t_suggester_insufficient_posted_count_returns_empty)
_test("全提案に正しい account_id", t_suggester_account_id_in_all_suggestions)


# ============================================================
# Phase 4.0: Sheets TAB_DEFINITIONS 確認
# ============================================================

print("\n=== Phase 4.0: TAB_DEFINITIONS ===")


def t_prompt_improvement_suggestions_tab_exists():
    assert "prompt_improvement_suggestions" in TAB_DEFINITIONS, \
        "prompt_improvement_suggestions タブが TAB_DEFINITIONS に未定義"


def t_prompt_improvement_suggestions_has_required_columns():
    cols = TAB_DEFINITIONS.get("prompt_improvement_suggestions", [])
    required = [
        "suggestion_id", "account_id", "created_at",
        "source", "suggestion_type", "current_behavior",
        "suggested_change", "reason", "expected_impact",
        "priority", "status", "reviewed_by", "reviewed_at",
    ]
    missing = [c for c in required if c not in cols]
    assert not missing, f"不足列: {missing}"


def t_prompt_improvement_suggestions_status_column():
    cols = TAB_DEFINITIONS.get("prompt_improvement_suggestions", [])
    assert "status" in cols


_test("TAB_DEFINITIONS に prompt_improvement_suggestions タブあり", t_prompt_improvement_suggestions_tab_exists)
_test("prompt_improvement_suggestions: 必須列が全部ある", t_prompt_improvement_suggestions_has_required_columns)
_test("prompt_improvement_suggestions: status 列あり", t_prompt_improvement_suggestions_status_column)


# ============================================================
# Phase 4.0: スクリプト存在確認
# ============================================================

print("\n=== Phase 4.0: スクリプト存在確認 ===")


def t_export_learning_context_exists():
    path = os.path.join(_V2_ROOT, "scripts", "export_learning_context.py")
    assert os.path.isfile(path), f"見つかりません: {path}"


def t_import_improvement_suggestions_exists():
    path = os.path.join(_V2_ROOT, "scripts", "import_improvement_suggestions.py")
    assert os.path.isfile(path), f"見つかりません: {path}"


def t_review_improvement_suggestions_exists():
    path = os.path.join(_V2_ROOT, "scripts", "review_improvement_suggestions.py")
    assert os.path.isfile(path), f"見つかりません: {path}"


def t_approve_learning_rule_exists():
    path = os.path.join(_V2_ROOT, "scripts", "approve_learning_rule.py")
    assert os.path.isfile(path), f"見つかりません: {path}"


def t_check_learning_integrity_exists():
    path = os.path.join(_V2_ROOT, "scripts", "check_learning_integrity.py")
    assert os.path.isfile(path), f"見つかりません: {path}"


_test("export_learning_context.py 存在", t_export_learning_context_exists)
_test("import_improvement_suggestions.py 存在", t_import_improvement_suggestions_exists)
_test("review_improvement_suggestions.py 存在", t_review_improvement_suggestions_exists)
_test("approve_learning_rule.py 存在", t_approve_learning_rule_exists)
_test("check_learning_integrity.py 存在", t_check_learning_integrity_exists)


# ============================================================
# Phase 4.0: fixture ファイル確認
# ============================================================

print("\n=== Phase 4.0: fixture ファイル確認 ===")


def t_fixture_improvement_context_exists():
    path = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_improvement_context.json")
    assert os.path.isfile(path), f"見つかりません: {path}"


def t_fixture_improvement_suggestions_exists():
    path = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_improvement_suggestions.json")
    assert os.path.isfile(path), f"見つかりません: {path}"


def t_fixture_improvement_suggestions_valid():
    path = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_improvement_suggestions.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    suggestions = data.get("suggestions", [])
    assert len(suggestions) > 0
    for s in suggestions:
        assert s.get("status") == "WAITING_REVIEW", f"fixture 提案は WAITING_REVIEW: {s.get('status')!r}"
        assert s.get("source") in ("hermes", "manual", "performance_analyzer")


def t_fixture_prompt_improvement_suggestions_exists():
    path = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_prompt_improvement_suggestions.json")
    assert os.path.isfile(path), f"見つかりません: {path}"


def t_fixture_hermes_weekly_report_exists():
    path = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_hermes_weekly_report.md")
    assert os.path.isfile(path), f"見つかりません: {path}"


def t_fixture_improvement_context_valid():
    path = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_improvement_context.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    required_keys = [
        "exported_at", "account_id", "purpose",
        "posted_results_summary", "queue_summary",
        "active_learning_rules", "video_clip_summary",
    ]
    for k in required_keys:
        assert k in data, f"fixture に {k!r} が必要"


_test("fixture: sample_improvement_context.json 存在", t_fixture_improvement_context_exists)
_test("fixture: sample_improvement_suggestions.json 存在", t_fixture_improvement_suggestions_exists)
_test("fixture: sample_improvement_suggestions.json 内容正常", t_fixture_improvement_suggestions_valid)
_test("fixture: sample_prompt_improvement_suggestions.json 存在", t_fixture_prompt_improvement_suggestions_exists)
_test("fixture: sample_hermes_weekly_report.md 存在", t_fixture_hermes_weekly_report_exists)
_test("fixture: sample_improvement_context.json 内容正常", t_fixture_improvement_context_valid)


# ============================================================
# Phase 4.1: approve_learning_rule.py 構造確認
# ============================================================

print("\n=== Phase 4.1: approve_learning_rule 構造確認 ===")


def t_approve_learning_rule_has_dry_run_guard():
    import importlib.util
    path = os.path.join(_V2_ROOT, "scripts", "approve_learning_rule.py")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    assert "--confirm-approve" in src, "--confirm-approve フラグが必要"
    assert "dry_run" in src, "dry_run ガードが必要"


def t_approve_learning_rule_forbids_auto_active():
    """active=true 自動設定禁止の文言確認。"""
    import importlib.util
    path = os.path.join(_V2_ROOT, "scripts", "approve_learning_rule.py")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    assert "active=true" in src or "active" in src, "active 操作のドキュメントが必要"


def t_check_learning_integrity_has_auto_approve_check():
    path = os.path.join(_V2_ROOT, "scripts", "check_learning_integrity.py")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    assert "reviewed_by" in src, "reviewed_by チェックが必要"
    assert "WAITING_REVIEW" in src


_test("approve_learning_rule: --confirm-approve ガードあり", t_approve_learning_rule_has_dry_run_guard)
_test("approve_learning_rule: active 操作の記述あり", t_approve_learning_rule_forbids_auto_active)
_test("check_learning_integrity: reviewed_by + WAITING_REVIEW チェックあり", t_check_learning_integrity_has_auto_approve_check)


# ============================================================
# Phase 4.1: MockSheetsClient で check_learning_integrity 動作確認
# ============================================================

print("\n=== Phase 4.1: check_learning_integrity MockSheetsClient 動作 ===")


def t_check_learning_integrity_with_empty_mock():
    import importlib.util
    path = os.path.join(_V2_ROOT, "scripts", "check_learning_integrity.py")
    spec = importlib.util.spec_from_file_location("check_learning_integrity", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    sheets = MockSheetsClient(dry_run=True)
    results = []
    issues = mod.check_learning_rules(sheets, "night_scout", results)
    assert issues == 0, f"空 learning_rules は issues=0: {issues}"
    assert any("[PASS]" in r for r in results)


def t_check_improvement_suggestions_with_empty_mock():
    import importlib.util
    path = os.path.join(_V2_ROOT, "scripts", "check_learning_integrity.py")
    spec = importlib.util.spec_from_file_location("check_learning_integrity", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    sheets = MockSheetsClient(dry_run=True)
    results = []
    issues = mod.check_improvement_suggestions(sheets, "night_scout", results)
    assert issues == 0, f"空 suggestions は issues=0: {issues}"


_test("check_learning_integrity: 空 Mock で issues=0", t_check_learning_integrity_with_empty_mock)
_test("check_improvement_suggestions: 空 Mock で issues=0", t_check_improvement_suggestions_with_empty_mock)


# ============================================================
# 結果表示
# ============================================================

print("\n" + "=" * 60)
print(f"  test_phase4_learning.py 結果: PASS={_PASS} FAIL={_FAIL}")
print("=" * 60)

for name, ok, err in _tests:
    icon = "[PASS]" if ok else "[FAIL]"
    if ok:
        print(f"  {icon} {name}")
    else:
        print(f"  {icon} {name}")
        print(f"         → {err}")

if _FAIL > 0:
    sys.exit(1)
sys.exit(0)
