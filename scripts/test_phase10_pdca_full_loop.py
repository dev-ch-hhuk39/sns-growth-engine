#!/usr/bin/env python3
"""test_phase10_pdca_full_loop.py"""
from __future__ import annotations
import os, sys
from datetime import datetime, timedelta, timezone
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

results = []
JST = timezone(timedelta(hours=9))

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append((name, status, detail))
    print(f"  {'✓' if condition else '✗'} [{status}] {name}" + (f": {detail}" if detail else ""))

def main():
    print("=== Phase 10: PDCA Full Loop テスト ===\n")

    print("[1] PDCAOrchestrator import")
    try:
        from src.learning.pdca_orchestrator import PDCAOrchestrator
        check("import OK", True)
    except Exception as e:
        check("import", False, str(e))
        sys.exit(1)

    print("\n[2] WeeklyReportBuilder import")
    try:
        from src.learning.weekly_report_builder import build_weekly_report
        check("import OK", True)
    except Exception as e:
        check("import", False, str(e))

    print("\n[3] mock posted_results でPDCA実行")
    now = datetime.now(JST)
    mock_results = [
        {
            "post_id": f"p{i:03d}",
            "account_id": "night_scout",
            "platform": "x",
            "posted_at": (now - timedelta(days=i % 7)).isoformat(),
            "generation_type": ["reference_based", "original_hypothesis"][i % 2],
            "likes": (i + 1) * 80,
            "impressions": (i + 1) * 1000,
            "source_id": "src_001",
        }
        for i in range(10)
    ]

    try:
        from src.learning.pdca_orchestrator import PDCAOrchestrator
        orch = PDCAOrchestrator()
        result = orch.run(
            results=mock_results,
            account_id="night_scout",
            platform="x",
            days=7,
        )
        check("PDCA run 成功", result is not None)
        check("PDCA account_id", result.get("account_id") == "night_scout")
        check("PDCA suggestions あり", isinstance(result.get("improvement_suggestions", []), list))
        check("PDCA auto_apply=False", all(
            not s.get("auto_apply", False)
            for s in result.get("improvement_suggestions", [])
        ))
    except Exception as e:
        check("PDCA run", False, str(e))

    print("\n[4] WeeklyReport生成")
    try:
        from src.learning.weekly_report_builder import build_weekly_report
        report = build_weekly_report(
            account_id="night_scout",
            posted_results=mock_results,
            queue_items=[],
            learning_rules=[],
            suggestions=[],
            category_scores=[],
        )
        check("report 生成", report is not None)
        check("report account_id", report.get("account_id") == "night_scout")
    except Exception as e:
        check("weekly report", False, str(e))

    print("\n[5] learning_rules active=false 維持確認")
    try:
        from src.learning.pdca_orchestrator import PDCAOrchestrator
        orch = PDCAOrchestrator()
        suggestions = orch.run(
            results=mock_results,
            account_id="night_scout",
            platform="x",
            days=7,
        ).get("improvement_suggestions", [])

        for s in suggestions:
            check(f"suggestion status=WAITING_REVIEW",
                  s.get("status", "").upper() in ("WAITING_REVIEW", "PLANNED", "INFO"))
            check(f"auto_apply=False", not s.get("auto_apply", False))
    except Exception as e:
        check("learning_rules auto_apply check", False, str(e))

    print("\n[6] source priority 自動変更なし")
    # PDCA 結果に auto_source_priority_change があれば FAIL
    try:
        result = PDCAOrchestrator().run(
            results=mock_results,
            account_id="night_scout",
            platform="x",
            days=7,
        )
        auto_change = result.get("auto_source_priority_change", False)
        check("source priority 自動変更なし", not auto_change)
    except Exception as e:
        check("source priority check", False, str(e))

    print(f"\n{'='*50}")
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    print(f"結果: {passed} PASS / {failed} FAIL")
    if failed: sys.exit(1)
    print("[OK] PDCA Full Loop テスト完了")

if __name__ == "__main__":
    sys.exit(main() or 0)
