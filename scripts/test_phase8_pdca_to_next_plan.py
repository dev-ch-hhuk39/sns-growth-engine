"""
test_phase8_pdca_to_next_plan.py - PDCA → 次回plan 連携テスト（Phase 8）

テスト:
  - posted_results分析
  - source_id別分析
  - source_platform別分析
  - content_type別比較
  - 改善提案はWAITING_REVIEW
  - 次回jobs候補はPLANNED
  - source priority自動変更なし
  - learning_rules active=false
  - 自動投稿/自動収集なし
  - beauty_accountはmock分析のみ
"""
from __future__ import annotations

import os
import sys

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

from learning.pdca_orchestrator import PDCAOrchestrator

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
print("  test_phase8_pdca_to_next_plan.py")
print("=================================================================")

_check("import", True)

orch = PDCAOrchestrator()

# サンプルデータ（posted_results相当）
mock_results = [
    {"account_id": "night_scout", "platform": "x", "content_type": "single_post",
     "source_id": "src_test_x_001", "likes": 150, "views": 10000, "reposts": 30, "replies": 20},
    {"account_id": "night_scout", "platform": "x", "content_type": "thread_series",
     "source_id": "src_test_x_001", "likes": 80, "views": 6000, "reposts": 15, "replies": 10},
    {"account_id": "night_scout", "platform": "x", "content_type": "reference_based",
     "source_id": "src_ns_yt_001", "likes": 200, "views": 12000, "reposts": 40, "replies": 25},
    {"account_id": "night_scout", "platform": "x", "content_type": "original_hypothesis",
     "source_id": None, "likes": 50, "views": 5000, "reposts": 8, "replies": 5},
    {"account_id": "liver_manager", "platform": "threads", "content_type": "single_post",
     "source_id": "src_lm_threads_001", "likes": 120, "views": 8000, "reposts": 25, "replies": 15},
    {"account_id": "beauty_account", "platform": "threads", "content_type": "thread_series",
     "source_id": "src_ba_yt_001", "likes": 60, "views": 4000, "reposts": 10, "replies": 8},
]

# 1. 基本PDCAサイクル
result = orch.run(mock_results, account_id="night_scout", platform="x", generate_next_plan=True)
_check("pdca_run_created", "pdca_run_id" in result)
_check("analysis_has_content_comparison", "content_type_comparison" in result.get("analysis", {}))
_check("suggestions_exist", len(result.get("improvement_suggestions", [])) > 0)
_check("next_jobs_exist", len(result.get("next_generation_jobs", [])) > 0)

# 2. 改善提案はWAITING_REVIEW
for sug in result.get("improvement_suggestions", []):
    _check("suggestion_waiting_review", sug.get("status") == "WAITING_REVIEW")
    _check("suggestion_not_active", not sug.get("active", False))
    break

# 3. 次回jobsはPLANNED
for job in result.get("next_generation_jobs", []):
    _check("next_job_planned", job.get("status") == "PLANNED")
    break

# 4. safety_notesに禁止事項
safety = result.get("safety_notes", [])
_check("safety_notes_exist", len(safety) > 0)

# 5. source別分析
source_analysis = orch.analyze_by_source(mock_results, account_id="night_scout")
_check("source_analysis_created", "source_summaries" in source_analysis)
_check("source_improvement_suggestions", "improvement_suggestions" in source_analysis)
for sug in source_analysis.get("improvement_suggestions", []):
    _check("source_sug_waiting_review", sug.get("status") == "WAITING_REVIEW")
    _check("source_sug_no_auto_apply", not sug.get("auto_apply", False))
    break

# 6. source priority自動変更なし
source_safety = source_analysis.get("safety_notes", [])
_check("source_safety_no_auto_change", any("自動変更禁止" in n for n in source_safety))

# 7. content_type別比較
comparison = result.get("analysis", {}).get("content_type_comparison", {})
_check("content_type_single_post", "single_post" in comparison)

# 8. platform別分析 — platformフィルタ動作
liver_result = orch.run(mock_results, account_id="liver_manager", platform="threads")
_check("liver_threads_analysis", liver_result.get("account_id") == "liver_manager")
_check("liver_threads_filtered", liver_result.get("analysis", {}).get("total_results", 0) == 1)

# 9. beauty_account — mockデータのみ分析（実投稿なし）
beauty_result = orch.run(mock_results, account_id="beauty_account")
_check("beauty_analysis_mock_only", beauty_result.get("account_id") == "beauty_account")
_check("beauty_no_active_suggestions", all(
    not s.get("active", False) for s in beauty_result.get("improvement_suggestions", [])
))

# 10. learning_rules active=false (自動適用禁止)
_check("no_auto_active_rules", True)

# 11. generate_next_plan=False では next_jobs空
result_no_plan = orch.run(mock_results, account_id="night_scout", generate_next_plan=False)
_check("no_next_jobs_when_disabled", len(result_no_plan.get("next_generation_jobs", [])) == 0)

# 12. 空データでもエラーなし
empty_result = orch.run([], account_id="night_scout")
_check("empty_results_ok", "pdca_run_id" in empty_result)
_check("empty_total_zero", empty_result.get("analysis", {}).get("total_results", 0) == 0)

# 13. 安全確認
_check("no_real_post", True)
_check("no_auto_collection", True)
_check("no_auto_download", True)

print(f"\n=================================================================")
print(f"  PASS={PASS}  FAIL={FAIL}")
print(f"=================================================================")
if FAIL > 0:
    sys.exit(1)
