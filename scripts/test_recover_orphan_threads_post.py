#!/usr/bin/env python3
"""test_recover_orphan_threads_post.py — recover_orphan_threads_post のロジックテスト。"""
from __future__ import annotations
import sys, os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

PASS_COUNT = FAIL_COUNT = 0


def check(label: str, cond: bool) -> None:
    global PASS_COUNT, FAIL_COUNT
    if cond:
        PASS_COUNT += 1
        print(f"  PASS {label}")
    else:
        FAIL_COUNT += 1
        print(f"  FAIL {label}")


print("=== test_recover_orphan_threads_post ===\n")

# -------- helper imports --------
from scripts.recover_orphan_threads_post import (
    _check_already_recovered,
    _match_post_in_api_results,
    _write_recovery,
)


# 1. _check_already_recovered — queue_id 一致で SKIP
posted_rows = [
    {"result_id": "r1", "queue_id": "recovery_ns_01", "draft_id": "d1", "derivative_id": "der1", "status": "RECOVERED"},
]
result = _check_already_recovered(posted_rows, "recovery_ns_01", "d1", "der1")
check("queue_id一致で already_recovered を返す", result is not None)

# 2. _check_already_recovered — 別 queue_id なら None
result2 = _check_already_recovered(posted_rows, "recovery_ns_02", "d2", "der2")
check("別 queue_id は already_recovered なし", result2 is None)

# 3. _check_already_recovered — draft_id POSTED で検出
posted_rows2 = [
    {"result_id": "r2", "queue_id": "other_q", "draft_id": "draft_posted", "derivative_id": "", "status": "POSTED"},
]
result3 = _check_already_recovered(posted_rows2, "new_queue_id", "draft_posted", "")
check("draft_id=POSTED で already_recovered を返す", result3 is not None)

# 4. _check_already_recovered — derivative_id 一致
posted_rows3 = [
    {"result_id": "r3", "queue_id": "q3", "draft_id": "d3", "derivative_id": "der_match", "status": "RECOVERED"},
]
result4 = _check_already_recovered(posted_rows3, "q_new", "d_new", "der_match")
check("derivative_id一致で already_recovered を返す", result4 is not None)

# 5. _check_already_recovered — 空の derivative_id は無視
posted_rows4 = [
    {"result_id": "r4", "queue_id": "q4", "draft_id": "d4", "derivative_id": "", "status": "RECOVERED"},
]
result5 = _check_already_recovered(posted_rows4, "q_new2", "d_new2", "")
check("derivative_id 空は一致しない", result5 is None)

# 6. _match_post_in_api_results — 完全一致
api_posts = [
    {"id": "111", "text": "バック率だけ見て店を決める子ほど、あとで苦しくなる。", "timestamp": "2026-06-25T10:00:00Z", "permalink": "https://threads.net/p/abc"},
]
matched = _match_post_in_api_results(api_posts, "バック率だけ見て店を決める子ほど、あとで苦しくなる。")
check("テキスト完全一致でマッチ", matched is not None and matched.get("id") == "111")

# 7. _match_post_in_api_results — 先頭20文字部分一致
long_text = "バック率だけ見て店を決める子ほど、" + "あとで苦しくなる。" * 5
api_posts2 = [
    {"id": "222", "text": long_text, "timestamp": "2026-06-25T11:00:00Z", "permalink": "https://threads.net/p/def"},
]
matched2 = _match_post_in_api_results(api_posts2, long_text)
check("長いテキストの完全一致でマッチ", matched2 is not None and matched2.get("id") == "222")

# 8. _match_post_in_api_results — 一致なし
api_posts3 = [
    {"id": "333", "text": "全く別の投稿テキストです。", "timestamp": "2026-06-25T12:00:00Z", "permalink": ""},
]
matched3 = _match_post_in_api_results(api_posts3, "バック率だけ見て店を決める子ほど")
check("テキスト不一致では None を返す", matched3 is None)

# 9. _match_post_in_api_results — API posts が空リスト
matched4 = _match_post_in_api_results([], "何かテキスト")
check("API posts 空リストで None を返す", matched4 is None)

# 10. スクリプトが import できること（再確認）
check("scripts/recover_orphan_threads_post.py import OK", True)

# 11. dry-run telemetry must not expose post text, permalink, or unknown
# metrics as fabricated zeroes.
secret_text = "公開前の投稿本文はstdoutに出さない"
dry_plan = _write_recovery(
    object(),
    queue_row={
        "queue_id": "q_redacted",
        "account_id": "night_scout",
        "draft_id": "d_redacted",
        "status": "POSTED_SAVE_FAILED",
    },
    social_derivative_id="sd_redacted",
    text=secret_text,
    external_post_id="external-redacted",
    post_url="https://www.threads.com/@example/post/redacted",
    dry_run=True,
)
dry_json = str(dry_plan)
check("dry-runに投稿本文を含めない", secret_text not in dry_json)
check("dry-runに投稿URLを含めない", "threads.com" not in dry_json)
preview = dry_plan["would_write"]["posted_results"]
check("dry-runはmetrics未計測を明示", preview["metrics_status"] == "MANUAL_PENDING")
check("dry-runは未知metricsの0を表示しない", not ({"views", "likes", "comments"} & set(preview)))

# 12. --help が exit 0 相当で通ること
import subprocess, sys as _sys
result_help = subprocess.run(
    [_sys.executable, "scripts/recover_orphan_threads_post.py", "--help"],
    capture_output=True, cwd=str(ROOT)
)
check("--help が exit 0 で終了する", result_help.returncode == 0)
check("--help に --apply が含まれる", b"--apply" in result_help.stdout)

# 13. beauty_account は choices に含まれない
check("beauty_account は --account-id の選択肢外", b"beauty_account" not in result_help.stdout)

print(f"\n--- 結果 ---")
print(f"PASS: {PASS_COUNT} / FAIL: {FAIL_COUNT}")
sys.exit(0 if FAIL_COUNT == 0 else 1)
