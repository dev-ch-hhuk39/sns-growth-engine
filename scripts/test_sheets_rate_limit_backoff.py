#!/usr/bin/env python3
"""test_sheets_rate_limit_backoff.py — Sheets retry and fresh schema safety."""
from __future__ import annotations
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

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

import scripts.process_threads_queue as ptq  # noqa: E402


# 1. _get_headers は ws.row_values(1) を呼ぶ
ws_mock = MagicMock()
ws_mock.row_values.return_value = ["col_a", "col_b"]
headers = ptq._get_headers(ws_mock)
check("_get_headers が ws.row_values(1) を呼ぶ", ws_mock.row_values.call_count == 1)
check("_get_headers がヘッダーリストを返す", headers == ["col_a", "col_b"])

# 2. A source mutation must NOT cache headers across invocations.
ws_mock.row_values.return_value = ["col_a", "new_column"]
headers2 = ptq._get_headers(ws_mock)
check("2回目も current provider headers を読む", ws_mock.row_values.call_count == 2)
check("provider schema drift を検出する", headers2 == ["col_a", "new_column"])

# 3. Independent worksheet objects always return their own fresh schema.
ws_mock2 = MagicMock()
ws_mock2.row_values.return_value = ["x", "y", "z"]
h2 = ptq._get_headers(ws_mock2)
check("別の ws オブジェクトの最新ヘッダーを返す",
      h2 == ["x", "y", "z"] and ws_mock2.row_values.call_count == 1)

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
with patch("time.sleep") as mock_sleep:
    headers_429 = ptq._get_headers(ws_429)
check("429後にリトライしてヘッダーを取得する", headers_429 == ["h1", "h2"])
check("429 発生時に sleep を呼ぶ", mock_sleep.called)

# 4b. Google Sheets が返す一時的な 409 operation aborted もリトライする
ws_409 = MagicMock()
call_count_409 = 0

def _row_values_409_then_ok(*args, **kwargs):
    global call_count_409
    call_count_409 += 1
    if call_count_409 < 2:
        raise Exception("APIError: [409]: The operation was aborted.")
    return ["h1", "h2"]

ws_409.row_values.side_effect = _row_values_409_then_ok
with patch("time.sleep") as mock_sleep_409:
    headers_409 = ptq._get_headers(ws_409)
check("operation-aborted 409後にヘッダー取得をリトライする", headers_409 == ["h1", "h2"])
check("operation-aborted 409で sleep を呼ぶ", mock_sleep_409.called)

# 5. 429 が 4 回続くと例外が上がる
call_count_always = 0

def _row_values_always_429(*args, **kwargs):
    raise Exception("APIError: 429 quota exceeded")

ws_always429 = MagicMock()
ws_always429.row_values.side_effect = _row_values_always_429
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
other_raised = False
with patch("time.sleep") as mock_sleep_other:
    try:
        ptq._get_headers(ws_other_err)
    except ValueError:
        other_raised = True
check("429 以外のエラーはリトライしない", other_raised)
check("429 以外のエラーで sleep は呼ばれない", not mock_sleep_other.called)

# 7. append_row must read current headers before a single RAW append
ws_append = MagicMock()
ws_append.row_values.return_value = ["queue_id", "status"]
ws_append.append_row.return_value = None

client_mock = MagicMock()
client_mock.dry_run = False  # write-capable fixture; dry-run mutations are forbidden
client_mock._ws.return_value = ws_append

ptq.append_row(client_mock, "queue", {"queue_id": "q1", "status": "WAITING_REVIEW"})
check("append_row が ws.row_values(1) を1回だけ呼ぶ", ws_append.row_values.call_count == 1)
check("append_row が ws.append_row を呼ぶ", ws_append.append_row.called)

# 8. update_row reads current headers, preflight and committed values
ws_update = MagicMock()
ws_update.row_values.return_value = ["queue_id", "status", "error"]
ws_update.findall.return_value = [MagicMock(row=2, value="q1")]
ws_update.batch_update.return_value = None
readback = {"count": 0}
def _current_and_persisted(number):
    if number == 1:
        return ["queue_id", "status", "error"]
    readback["count"] += 1
    return ["q1", "PROCESSING" if readback["count"] == 1 else "POSTED", ""]
ws_update.row_values.side_effect = _current_and_persisted

client_mock2 = MagicMock()
client_mock2.dry_run = False  # write-capable fixture; dry-run mutations are forbidden
client_mock2._ws.return_value = ws_update

ptq.update_row(client_mock2, "queue", "queue_id", "q1", {"status": "POSTED"})
check("update_row が最新ヘッダー・更新前・更新後を確認する",
      ws_update.row_values.call_count == 3
      and readback["count"] == 2
      and ws_update.row_values.call_args.args == (2,))
check("update_row が ws.batch_update を呼ぶ", ws_update.batch_update.called)
check("update_row が ws.update_cell を呼ばない", not ws_update.update_cell.called)

print("\n--- 結果 ---")
print(f"PASS: {PASS_COUNT} / FAIL: {FAIL_COUNT}")
sys.exit(0 if FAIL_COUNT == 0 else 1)
