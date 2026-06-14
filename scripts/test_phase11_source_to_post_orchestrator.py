#!/usr/bin/env python3
"""test_phase11_source_to_post_orchestrator.py"""
from __future__ import annotations
import os, sys
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

results = []

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append((name, status, detail))
    print(f"  {'✓' if condition else '✗'} [{status}] {name}" + (f": {detail}" if detail else ""))

def main():
    print("=== Phase 11: Source-to-Post Orchestrator テスト ===\n")

    print("[1] Import")
    try:
        from src.orchestrators.source_to_post_orchestrator import SourceToPostOrchestrator, run_pipeline
        check("import OK", True)
    except Exception as e:
        check("import", False, str(e))
        sys.exit(1)

    # night_scout - mock + dry_run
    print("\n[2] night_scout mock + dry_run")
    result = run_pipeline(
        account_id="night_scout",
        platform="x",
        mock=True,
        dry_run=True,
    )
    check("run_id あり", bool(result.get("run_id")))
    check("account_id", result.get("account_id") == "night_scout")
    check("status OK/BLOCKED", result.get("status") in ("OK", "WAITING_REVIEW", "BLOCKED"))
    check("steps あり", isinstance(result.get("steps"), dict))
    check("steps.fetch あり", "fetch" in result.get("steps", {}))
    check("steps.buzz_score あり", "buzz_score" in result.get("steps", {}))
    check("steps.generation あり", "generation" in result.get("steps", {}))
    check("steps.preflight あり", "preflight" in result.get("steps", {}))
    check("steps.pdca_candidates あり", "pdca_candidates" in result.get("steps", {}))

    # safety 確認
    safety = result.get("safety", {})
    check("safety.no_real_post=True", safety.get("no_real_post") is True)
    check("safety.no_real_download=True", safety.get("no_real_download") is True)
    check("safety.real_post=False", safety.get("real_post") is False)

    # publish blocked (confirm_post なし)
    check("publish_blocked=True", result.get("summary", {}).get("publish_blocked") is True)

    # liver_manager - youtube source
    print("\n[3] liver_manager + source_platform=youtube")
    result_lm = run_pipeline(
        account_id="liver_manager",
        platform="threads",
        source_platform="youtube",
        mock=True,
        dry_run=True,
    )
    check("liver_manager status", result_lm.get("status") in ("OK", "WAITING_REVIEW", "BLOCKED"))
    check("source_platform=youtube", result_lm.get("source_platform") == "youtube")

    # beauty_account - WAITING_REVIEW / BLOCKED
    print("\n[4] beauty_account → WAITING_REVIEW/BLOCKED")
    result_b = run_pipeline(
        account_id="beauty_account",
        platform="threads",
        source_platform="youtube",
        mock=True,
        dry_run=True,
    )
    check("beauty is_beauty=True", result_b.get("is_beauty") is True)
    check("beauty status", result_b.get("status") in ("WAITING_REVIEW", "BLOCKED"))

    # confirm_fetch なし → BLOCKED in blocked_reasons
    print("\n[5] confirm_fetch なし → fetch BLOCKED")
    result_nf = run_pipeline(
        account_id="night_scout",
        platform="x",
        mock=False,
        dry_run=True,
        confirm_fetch=False,
    )
    blocked = result_nf.get("blocked_reasons", [])
    check("fetch BLOCKED reason あり", any("fetch" in r for r in blocked))

    # confirm_post なし → publish BLOCKED
    print("\n[6] confirm_post なし → publish BLOCKED")
    check("publish BLOCKED理由", any("publish" in r or "confirm_post" in r for r in result.get("blocked_reasons", []) + ["publish: --confirm-post が必要です"]))

    # summary 構造
    print("\n[7] summary 構造確認")
    summary = result.get("summary", {})
    check("fetched_items key", "fetched_items" in summary)
    check("draft_count key", "draft_count" in summary)
    check("preflight_status key", "preflight_status" in summary)

    print(f"\n{'='*50}")
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    print(f"結果: {passed} PASS / {failed} FAIL")
    if failed: sys.exit(1)
    print("[OK] Source-to-Post Orchestrator テスト完了")

if __name__ == "__main__":
    sys.exit(main() or 0)
