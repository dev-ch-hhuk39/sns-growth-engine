#!/usr/bin/env python3
from __future__ import annotations
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("auto_approve_queue", ROOT / "scripts/auto_approve_queue.py")
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)


def main() -> int:
    rules = mod.rules_for_account(mod.load_rules(), "night_scout")
    q = {"queue_id": "q1", "account_id": "night_scout", "platform": "threads", "status": "WAITING_REVIEW", "generation_mode": "reference_score_to_threads", "media_reuse_risk": ""}
    d = {"source_refs": "ref1", "media_strategy": "none"}
    der = {"text": "夜職でしんどくなる人ほど、最初に見るべきポイントがある。\n\n不安を整理して、強すぎない相談導線に変換する投稿。プロフィールから相談できます。"}
    ev = mod.evaluate_item(queue=q, draft=d, derivative=der, scores_by_ref={"ref1": {"recommended_use": "REFERENCE_ONLY"}}, existing_texts=[], rules=rules)
    checks = [("dry-run candidate approvable", ev["status"] == "APPROVABLE"), ("scores present", ev["quality_score"] >= 75 and ev["safety_score"] >= 90)]
    failed = [n for n, ok in checks if not ok]
    for n, ok in checks: print(f"  {'PASS' if ok else 'FAIL'} {n}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0
if __name__ == "__main__": raise SystemExit(main())
