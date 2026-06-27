#!/usr/bin/env python3
"""generate_next_queue_from_metrics の純粋ロジックを検証する（Sheets不要）。

- compute_engagement_rate: ER 計算
- rank_results_by_engagement: MEASURED のみ・ER降順・他アカウント/x除外
- build_next_queue_candidates: 生成 queue 行が ELIGIBLE_STATUSES に含まれない / suggestion は WAITING_REVIEW
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/generate_next_queue_from_metrics.py"


def _load():
    spec = importlib.util.spec_from_file_location("generate_next_queue_from_metrics", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    mod = _load()
    checks: list[tuple[str, bool]] = []

    # --- ER 計算 ---
    checks.append(("ER=(likes+comments)/views", mod.compute_engagement_rate(100, 8, 2) == 0.1))
    checks.append(("views=0 は ER=0", mod.compute_engagement_rate(0, 5, 5) == 0.0))

    posted = [
        # 対象: liver_manager / threads / MEASURED, ER=0.10
        {"result_id": "r_hi", "account_id": "liver_manager", "platform": "threads",
         "metrics_status": "MEASURED", "views": 100, "likes": 8, "comments": 2, "content_type": "tips"},
        # 対象: ER=0.30（最上位になるべき）
        {"result_id": "r_top", "account_id": "liver_manager", "platform": "threads",
         "metrics_status": "MEASURED", "views": 100, "likes": 20, "comments": 10, "content_type": "story"},
        # 未計測 → 除外
        {"result_id": "r_pending", "account_id": "liver_manager", "platform": "threads",
         "metrics_status": "PENDING", "views": 500, "likes": 50, "comments": 50},
        # 他アカウント → 除外
        {"result_id": "r_other", "account_id": "night_scout", "platform": "threads",
         "metrics_status": "MEASURED", "views": 100, "likes": 90, "comments": 0},
        # x → 除外
        {"result_id": "r_x", "account_id": "liver_manager", "platform": "x",
         "metrics_status": "MEASURED", "views": 100, "likes": 90, "comments": 0},
    ]

    ranked = mod.rank_results_by_engagement(posted, "liver_manager")
    ranked_ids = [r["result_id"] for r in ranked]
    checks.append(("MEASURED のみ抽出", set(ranked_ids) == {"r_hi", "r_top"}))
    checks.append(("ER降順（r_top が先頭）", ranked_ids[0] == "r_top"))
    checks.append(("未計測は除外", "r_pending" not in ranked_ids))
    checks.append(("他アカウントは除外", "r_other" not in ranked_ids))
    checks.append(("x は除外", "r_x" not in ranked_ids))

    drafts, queues, suggestion = mod.build_next_queue_candidates(ranked, "liver_manager", 2, "20260627000000")
    checks.append(("候補数 = count", len(queues) == 2 and len(drafts) == 2))
    # 最重要: 生成 queue 行は worker 非対象ステータス
    checks.append(("生成 status は ELIGIBLE_STATUSES に含まれない",
                   all(q["status"] not in mod.ELIGIBLE_STATUSES for q in queues)))
    checks.append(("生成 status = DRAFT (NON_POSTABLE)",
                   all(q["status"] == mod.NON_POSTABLE_STATUS for q in queues)))
    checks.append(("POSTED にしない", all(q["status"] != "POSTED" for q in queues)))
    checks.append(("auto_publish=false", all(q["auto_publish"] == "false" for q in queues)))
    checks.append(("media なし(media_strategy=none)", all(d["media_strategy"] == "none" for d in drafts)))
    checks.append(("platform=threads のみ", all(q["platform"] == "threads" for q in queues)))
    checks.append(("suggestion は WAITING_REVIEW", suggestion["status"] == "WAITING_REVIEW"))
    checks.append(("suggestion notes に auto_apply=false", "auto_apply=false" in suggestion["notes"]))

    # データ無し → 候補 0（安全に空）
    d0, q0, _ = mod.build_next_queue_candidates([], "liver_manager", 3, "20260627000000")
    checks.append(("MEASURED 無しなら候補0", q0 == [] and d0 == []))

    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {n}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
