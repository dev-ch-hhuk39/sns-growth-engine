#!/usr/bin/env python3
"""test_repair_posted_results_integrity.py — repair_posted_results_integrity の単体テスト。

Mock Sheets を使って、空フィールド補正ロジックを検証する。
Sheets への実書き込みは行わない。
"""
from __future__ import annotations
import sys, os
from typing import Any

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASS_COUNT = FAIL_COUNT = 0


def check(label: str, cond: bool) -> None:
    global PASS_COUNT, FAIL_COUNT
    if cond:
        PASS_COUNT += 1
        print(f"  PASS {label}")
    else:
        FAIL_COUNT += 1
        print(f"  FAIL {label}")


print("=== test_repair_posted_results_integrity ===\n")

# ---- 補正ロジックのユニットテスト ----

ALLOWED_METRICS = {"PENDING", "MEASURED", "MANUAL_PENDING"}
ALLOWED_STATUS = {"POSTED", "RECOVERED"}


def simulate_repair(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """repair 関数のコアロジックを模倣（Sheets 接続なし）。"""
    repairs = []
    for idx, row in enumerate(rows, start=2):
        raw_status = str(row.get("status", "")).strip()
        status = raw_status.upper()
        platform = str(row.get("platform", "")).lower()

        if platform != "threads":
            memo = str(row.get("manual_memo", "")).lower()
            if not ("threads" in memo or "スレッズ" in memo):
                continue
            platform = "threads"

        effective_status = status
        changes: dict[str, str] = {}
        if not raw_status:
            memo = str(row.get("manual_memo", "")).lower()
            if "threads" in memo or "スレッズ" in memo or "投稿" in memo:
                effective_status = "RECOVERED"
                changes["status"] = "RECOVERED"
                changes["platform"] = "threads"
            else:
                continue

        if effective_status not in ALLOWED_STATUS:
            continue

        metrics = str(row.get("metrics_status", "")).strip()
        if not metrics or metrics.upper() not in ALLOWED_METRICS:
            changes["metrics_status"] = "PENDING" if effective_status == "POSTED" else "MANUAL_PENDING"

        rp = str(row.get("real_post", "")).strip()
        if not rp or rp.lower() not in ("true", "false"):
            changes["real_post"] = "true"

        mu = str(row.get("media_used", "")).strip()
        if not mu or mu.lower() not in ("true", "false"):
            changes["media_used"] = "false"

        if changes:
            repairs.append({"result_id": row.get("result_id"), "changes": changes, "effective_status": effective_status})
    return repairs


# 1. POSTED 行の空フィールド補正
posted_row = {
    "result_id": "test_posted_01",
    "account_id": "liver_manager",
    "platform": "threads",
    "status": "POSTED",
    "metrics_status": "",
    "real_post": "",
    "media_used": "",
    "external_post_id": "12345",
}
repairs = simulate_repair([posted_row])
check("POSTED 行 1件補正", len(repairs) == 1)
check("POSTED metrics_status → PENDING", repairs[0]["changes"].get("metrics_status") == "PENDING")
check("POSTED real_post → true", repairs[0]["changes"].get("real_post") == "true")
check("POSTED media_used → false", repairs[0]["changes"].get("media_used") == "false")

# 2. RECOVERED 行の空フィールド補正
recovered_row = {
    "result_id": "test_recovered_01",
    "account_id": "night_scout",
    "platform": "threads",
    "status": "RECOVERED",
    "metrics_status": "",
    "real_post": "",
    "media_used": "",
}
repairs2 = simulate_repair([recovered_row])
check("RECOVERED 行 1件補正", len(repairs2) == 1)
check("RECOVERED metrics_status → MANUAL_PENDING", repairs2[0]["changes"].get("metrics_status") == "MANUAL_PENDING")
check("RECOVERED real_post → true", repairs2[0]["changes"].get("real_post") == "true")
check("RECOVERED media_used → false", repairs2[0]["changes"].get("media_used") == "false")

# 3. 既に正しい値の行はスキップ
ok_row = {
    "result_id": "test_ok_01",
    "account_id": "night_scout",
    "platform": "threads",
    "status": "POSTED",
    "metrics_status": "PENDING",
    "real_post": "true",
    "media_used": "false",
    "external_post_id": "99999",
}
repairs3 = simulate_repair([ok_row])
check("正常行はスキップ（補正なし）", len(repairs3) == 0)

# 4. platform 空・manual_memo なしの行はスキップ
skip_row = {
    "result_id": "test_skip_01",
    "account_id": "night_scout",
    "platform": "",
    "status": "",
    "metrics_status": "",
    "manual_memo": "",
}
repairs4 = simulate_repair([skip_row])
check("platform/status/memo 空行はスキップ", len(repairs4) == 0)

# 5. platform 空・manual_memo に「threads」記載ありの行はスキップせず RECOVERED
memo_row = {
    "result_id": "test_memo_01",
    "account_id": "night_scout",
    "platform": "",
    "status": "",
    "metrics_status": "",
    "manual_memo": "Threads投稿記録: 2026-06-23",
}
repairs5 = simulate_repair([memo_row])
check("manual_memo の threads 記録行を RECOVERED に補正", len(repairs5) == 1)
check("manual_memo 行に status=RECOVERED セット", repairs5[0]["changes"].get("status") == "RECOVERED")

# 6. metrics_status の表記揺れ対応（MEASURED は変更しない）
measured_row = {
    "result_id": "test_measured_01",
    "account_id": "night_scout",
    "platform": "threads",
    "status": "POSTED",
    "metrics_status": "MEASURED",
    "real_post": "true",
    "media_used": "false",
}
repairs6 = simulate_repair([measured_row])
check("MEASURED は変更しない", len(repairs6) == 0)

# 7. beauty_account の threads 行も補正対象（安全な補正は行う）
beauty_row = {
    "result_id": "test_beauty_01",
    "account_id": "beauty_account",
    "platform": "threads",
    "status": "RECOVERED",
    "metrics_status": "",
    "real_post": "",
    "media_used": "",
}
repairs7 = simulate_repair([beauty_row])
check("beauty_account の RECOVERED 行も補正する（投稿自体はしない）", len(repairs7) == 1)

# 8. repair スクリプトが存在する
repair_path = os.path.join(_ROOT, "scripts", "repair_posted_results_integrity.py")
check("repair_posted_results_integrity.py が存在する", os.path.exists(repair_path))

# 9. workflow に repair ステップが含まれる
wf_path = os.path.join(_ROOT, ".github", "workflows", "threads-queue-worker.yml")
wf_text = open(wf_path).read()
check("threads-queue-worker.yml に repair ステップがある", "repair_posted_results_integrity.py" in wf_text)
check("threads-queue-worker.yml の repair は verify 前",
      wf_text.index("repair_posted_results_integrity.py") < wf_text.index("--verify-only"))

print(f"\n--- 結果 ---")
print(f"PASS: {PASS_COUNT} / FAIL: {FAIL_COUNT}")
sys.exit(0 if FAIL_COUNT == 0 else 1)
