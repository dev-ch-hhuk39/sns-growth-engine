#!/usr/bin/env python3
"""test_sheets_rate_limit_backoff.py — Sheets 429 バックオフとヘッダーキャッシュのテスト。"""
from __future__ import annotations
import sys, time
from pathlib import Path
from unittest.mock import MagicMock, patch, call

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


print("=== test_sheets_rate_limit_backoff ===\n")

import scripts.process_threads_queue as ptq


# ヘルパー: キャッシュをクリア
def clear_cache():
    ptq._headers_cache.clear()


# 1. _get_headers は ws.row_values(1) を呼ぶ
ws_mock = MagicMock()
ws_mock.row_values.return_value = ["col_a", "col_b"]
clear_cache()
headers = ptq._get_headers(ws_mock)
check("_get_headers が ws.row_values(1) を呼ぶ", ws_mock.row_values.call_count == 1)
check("_get_headers がヘッダーリストを返す", headers == ["col_a", "col_b"])

# 2. 2回目の呼び出しはキャッシュを使う（ws.row_values は呼ばれない）
headers2 = ptq._get_headers(ws_mock)
check("2回目は ws.row_values を呼ばない（キャッシュ）", ws_mock.row_values.call_count == 1)
check("2回目もヘッダーを返す", headers2 == ["col_a", "col_b"])

# 3. 別の ws オブジェクトは別エントリとしてキャッシュされる
ws_mock2 = MagicMock()
ws_mock2.row_values.return_value = ["x", "y", "z"]
clear_cache()
_ = ptq._get_headers(ws_mock)
ptq._headers_cache[id(ws_mock)].clear()  # ws_mock のキャッシュを無効化
ws_mock.row_values.reset_mock()
ptq._headers_cache.clear()
_ = ptq._get_headers(ws_mock)
h2 = ptq._get_headers(ws_mock2)
check("別の ws オブジェクトのヘッダーを独立して返す", h2 == ["x", "y", "z"])

# 4. 429 エラー発生時にリトライする
ws_429 = MagicMock()
call_count = 0

def _row_values_429_then_ok(*args, **kwargs):
    global call_count
    call_count += 1
    if call_count < 2:
        raise Exception("APIError: 429 quota exceeded")
    return ["h1", "h2"]

ws_429.row_values.side_effect = _row_values_429_then_ok
clear_cache()
with patch("time.sleep") as mock_sleep:
    headers_429 = ptq._get_headers(ws_429)
check("429後にリトライしてヘッダーを取得する", headers_429 == ["h1", "h2"])
check("429 発生時に sleep を呼ぶ", mock_sleep.called)

# 5. 429 が 4 回続くと例外が上がる
call_count_always = 0

def _row_values_always_429(*args, **kwargs):
    raise Exception("APIError: 429 quota exceeded")

ws_always429 = MagicMock()
ws_always429.row_values.side_effect = _row_values_always_429
clear_cache()
raised = False
with patch("time.sleep"):
    try:
        ptq._get_headers(ws_always429)
    except Exception:
        raised = True
check("429 が 4 回続くと最終的に例外を上げる", raised)

# 6. 429 以外の例外はリトライせずそのまま上がる
ws_other_err = MagicMock()
ws_other_err.row_values.side_effect = ValueError("unexpected error")
clear_cache()
other_raised = False
with patch("time.sleep") as mock_sleep_other:
    try:
        ptq._get_headers(ws_other_err)
    except ValueError:
        other_raised = True
check("429 以外のエラーはリトライしない", other_raised)
check("429 以外のエラーで sleep は呼ばれない", not mock_sleep_other.called)

# 7. append_row は _get_headers を通じてキャッシュされたヘッダーを使う
ws_append = MagicMock()
ws_append.row_values.return_value = ["queue_id", "status"]
ws_append.append_row.return_value = None
clear_cache()

client_mock = MagicMock()
client_mock._ws.return_value = ws_append

ptq.append_row(client_mock, "queue", {"queue_id": "q1", "status": "WAITING_REVIEW"})
check("append_row が ws.row_values(1) を1回だけ呼ぶ", ws_append.row_values.call_count == 1)
check("append_row が ws.append_row を呼ぶ", ws_append.append_row.called)

# 8. update_row も _get_headers キャッシュを使う
ws_update = MagicMock()
ws_update.row_values.return_value = ["queue_id", "status", "error"]
ws_update.find.return_value = MagicMock(row=2)
ws_update.update_cell.return_value = None
clear_cache()

client_mock2 = MagicMock()
client_mock2._ws.return_value = ws_update

ptq.update_row(client_mock2, "queue", "queue_id", "q1", {"status": "POSTED"})
check("update_row が ws.row_values(1) を1回だけ呼ぶ", ws_update.row_values.call_count == 1)
check("update_row が ws.update_cell を呼ぶ", ws_update.update_cell.called)

print(f"\n--- 結果 ---")
print(f"PASS: {PASS_COUNT} / FAIL: {FAIL_COUNT}")
sys.exit(0 if FAIL_COUNT == 0 else 1)
