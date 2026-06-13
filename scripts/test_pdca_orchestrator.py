"""
test_pdca_orchestrator.py - PDCAオーケストレーター テスト（Phase 7.E）

実投稿なし / 自動反映なし / learning_rules active=false 維持。
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


_SAMPLE_RESULTS = [
    {
        "result_id": "pr_001", "account_id": "night_scout", "platform": "x",
        "content_type": "single_post", "generation_mode": "single_post",
        "likes": 80, "reposts": 15, "replies": 5, "impressions": 2000,
        "posted_at": "2026-06-10T09:00:00Z",
    },
    {
        "result_id": "pr_002", "account_id": "night_scout", "platform": "x",
        "content_type": "thread_series", "generation_mode": "thread_series",
        "series_id": "ts_night_scout_x_abc123", "post_index": 0, "post_role": "hook",
        "likes": 120, "reposts": 30, "replies": 8, "impressions": 2500,
        "posted_at": "2026-06-11T09:00:00Z",
    },
    {
        "result_id": "pr_003", "account_id": "night_scout", "platform": "x",
        "content_type": "thread_series", "generation_mode": "thread_series",
        "series_id": "ts_night_scout_x_abc123", "post_index": 1, "post_role": "context",
        "likes": 32, "reposts": 8, "replies": 2, "impressions": 800,
        "posted_at": "2026-06-11T09:05:00Z",
    },
    {
        "result_id": "pr_004", "account_id": "night_scout", "platform": "x",
        "content_type": "reference_based", "generation_mode": "reference_based",
        "likes": 55, "reposts": 10, "replies": 3, "impressions": 1500,
        "posted_at": "2026-06-12T09:00:00Z",
    },
]


def test_import():
    """pdca_orchestrator がインポートできる。"""
    from learning.pdca_orchestrator import PDCAOrchestrator
    assert callable(PDCAOrchestrator)


def test_basic_run():
    """基本的なPDCAnサイクルが実行できる。"""
    from learning.pdca_orchestrator import PDCAOrchestrator
    orchestrator = PDCAOrchestrator()
    result = orchestrator.run(_SAMPLE_RESULTS, account_id="night_scout", platform="x")
    assert "pdca_run_id" in result
    assert result["pdca_run_id"].startswith("pdca_")
    assert "analysis" in result
    assert "improvement_suggestions" in result


def test_posted_results_analyzed():
    """posted_results が分析される。"""
    from learning.pdca_orchestrator import PDCAOrchestrator
    orchestrator = PDCAOrchestrator()
    result = orchestrator.run(_SAMPLE_RESULTS, account_id="night_scout", platform="x")
    assert result["analysis"]["total_results"] > 0


def test_content_type_comparison():
    """single_post / thread_series / reference_based が比較される。"""
    from learning.pdca_orchestrator import PDCAOrchestrator
    orchestrator = PDCAOrchestrator()
    result = orchestrator.run(_SAMPLE_RESULTS, account_id="night_scout", platform="x")
    comparison = result["analysis"]["content_type_comparison"]
    assert len(comparison) >= 2, "コンテンツタイプが2種類以上比較されていない"


def test_improvement_suggestions_waiting_review():
    """improvement_suggestions は全て WAITING_REVIEW。"""
    from learning.pdca_orchestrator import PDCAOrchestrator
    orchestrator = PDCAOrchestrator()
    result = orchestrator.run(_SAMPLE_RESULTS, account_id="night_scout", platform="x")
    for s in result["improvement_suggestions"]:
        assert s["status"] == "WAITING_REVIEW", (
            f"improvement_suggestion が WAITING_REVIEW でない: {s['status']}"
        )
        assert s["active"] is False, f"active が True になっています（禁止）: {s}"


def test_learning_rules_not_auto_activated():
    """learning_rules が自動 active 化されない。"""
    from learning.pdca_orchestrator import PDCAOrchestrator
    orchestrator = PDCAOrchestrator()
    result = orchestrator.run(_SAMPLE_RESULTS, account_id="night_scout", platform="x")
    for s in result["improvement_suggestions"]:
        assert s.get("active") is False, "improvement_suggestion が active=True になっています（禁止）"


def test_next_jobs_planned():
    """next_generation_jobs は全て PLANNED ステータス。"""
    from learning.pdca_orchestrator import PDCAOrchestrator
    orchestrator = PDCAOrchestrator()
    result = orchestrator.run(
        _SAMPLE_RESULTS,
        account_id="night_scout",
        platform="x",
        generate_next_plan=True,
    )
    assert result["next_jobs_count"] > 0, "次回 jobs が生成されていない"
    for job in result["next_generation_jobs"]:
        assert job["status"] == "PLANNED", f"次回 job が PLANNED でない: {job['status']}"
        assert job["status"] != "POSTED", "次回 job が POSTED になっています（禁止）"
        assert job["status"] != "READY", "次回 job が READY になっています（禁止）"


def test_beauty_account_no_active_results():
    """beauty_account は draft_only なので、結果がゼロでもエラーにならない。"""
    from learning.pdca_orchestrator import PDCAOrchestrator
    orchestrator = PDCAOrchestrator()
    result = orchestrator.run([], account_id="beauty_account", platform="x")
    assert result["analysis"]["total_results"] == 0
    assert isinstance(result["improvement_suggestions"], list)


def test_safety_notes_present():
    """safety_notes が出力に含まれる。"""
    from learning.pdca_orchestrator import PDCAOrchestrator
    orchestrator = PDCAOrchestrator()
    result = orchestrator.run(_SAMPLE_RESULTS, account_id="night_scout", platform="x")
    assert len(result["safety_notes"]) > 0
    notes_text = " ".join(result["safety_notes"])
    assert "WAITING_REVIEW" in notes_text
    assert "false" in notes_text.lower() or "active" in notes_text.lower()


def test_fixture_exists():
    """sample_pdca_cycle.json が存在する。"""
    path = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_pdca_cycle.json")
    assert os.path.isfile(path), "fixture が見つかりません"


def test_no_real_post():
    """PDCAサイクルが実投稿を行わない（スクリプト実行なし）。"""
    from learning.pdca_orchestrator import PDCAOrchestrator
    orchestrator = PDCAOrchestrator()
    result = orchestrator.run(_SAMPLE_RESULTS)
    # POSTED ステータスの job がないことを確認
    for job in result.get("next_generation_jobs", []):
        assert job.get("status") != "POSTED", "実投稿が実行されました（禁止）"


if __name__ == "__main__":
    print("=" * 65)
    print("  test_pdca_orchestrator.py")
    print("=" * 65)

    _test("import", test_import)
    _test("basic_run", test_basic_run)
    _test("posted_results_analyzed", test_posted_results_analyzed)
    _test("content_type_comparison", test_content_type_comparison)
    _test("improvement_suggestions_waiting_review", test_improvement_suggestions_waiting_review)
    _test("learning_rules_not_auto_activated", test_learning_rules_not_auto_activated)
    _test("next_jobs_planned", test_next_jobs_planned)
    _test("beauty_account_no_active_results", test_beauty_account_no_active_results)
    _test("safety_notes_present", test_safety_notes_present)
    _test("fixture_exists", test_fixture_exists)
    _test("no_real_post", test_no_real_post)

    print(f"\n{'=' * 65}")
    print(f"  PASS={_PASS}  FAIL={_FAIL}")
    print("=" * 65)
    if _FAIL > 0:
        sys.exit(1)
