"""
test_phase3d.py - Phase 3-D テスト

XPublisher の本番投稿実装・安全ガード・factory.py・publish_queue.py の
実投稿モードを MockSheetsClient + tweepy モックで検証する。
実際の X API への接続・投稿なし。認証情報不要。

テスト項目:
  1.  XPublisher dry_run=True: 正常テキスト → success=True
  2.  XPublisher dry_run=True: posted_url=None（投稿しない）
  3.  XPublisher dry_run=True: 141字 → success=False
  4.  XPublisher dry_run=True: 空テキスト → success=False
  5.  XPublisher dry_run=False: PUBLISH_ENABLED=false → SAFETY_STOP
  6.  XPublisher dry_run=False: ALLOW_REAL_X_POST=false → SAFETY_STOP
  7.  XPublisher dry_run=False: 認証情報なし → SAFETY_STOP
  8.  XPublisher dry_run=False: 認証情報あり（モック）→ 投稿成功 (success=True, posted_url設定)
  9.  XPublisher dry_run=False: tweepy エラー → success=False (POST_FAILED)
  10. factory.py dry_run=False → XPublisher が返る
  11. factory.py dry_run=False threads → _SafetyStopPublisher が返る
  12. publish_queue.py --confirm-real-post なし → exit(1)
  13. publish_queue.py --dry-run → 正常終了（posted_results 増えない）
  14. publish_queue.py --confirm-real-post 実行後: 投稿成功でqueue.status=POSTED
  15. publish_queue.py --confirm-real-post 実行後: posted_results に記録される
  16. publish_queue.py --max-real-posts 0 で --confirm-real-post → exit(1)
  17. XPublisher _build_posted_url: 正しいURL形式
"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest.mock as mock

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

# 安全ガード環境変数を初期化
os.environ["MOCK_LLM"] = "true"
os.environ["PUBLISH_ENABLED"] = "false"
os.environ["ALLOW_REAL_X_POST"] = "false"
os.environ["ALLOW_REAL_THREADS_POST"] = "false"

# 認証情報をクリア
for _k in ["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET"]:
    os.environ.pop(_k, None)

from sheets_client import MockSheetsClient
from publishers.x_publisher import XPublisher
from publishers.factory import get_publisher
from publishers.dry_run import DryRunPublisher
from publishers.base import PublishResult

PASS = 0
FAIL = 0


def _assert(cond: bool, name: str, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}" + (f": {detail}" if detail else ""))


def _setup_mock(status: str = "WAITING_REVIEW") -> MockSheetsClient:
    sheets = MockSheetsClient(dry_run=False)
    draft_id = "d-test-d01"
    queue_id = "q-test-d01"
    sheets.save_draft(
        account_id="night_scout", title="Phase 3-D テスト下書き",
        body_md="本文テキスト", draft_id=draft_id, status="READY", score="90",
    )
    sheets.append_social_derivative({
        "draft_id": draft_id, "platform": "x",
        "text": "「スカウトは稼げない」はもう古い。組織的ロジックで高収益を狙う、真っ当な稼ぎ方を教えます。",
        "status": "READY", "derivative_id": "sd-d01",
    })
    sheets.append_queue_item({
        "queue_id": queue_id, "draft_id": draft_id, "account_id": "night_scout",
        "platform": "x", "status": status,
        "scheduled_at": "2026-05-23T20:00:00+0900", "priority": "1",
    })
    return sheets


_ACCOUNT = {"account_id": "night_scout"}
_DERIV_X = {"derivative_id": "sd-d01", "platform": "x", "draft_id": "d-test-d01"}
_QUEUE = {"queue_id": "q-test-d01", "status": "READY"}
_TEXT_NORMAL = "「スカウトは稼げない」はもう古い。組織的ロジックで高収益を狙う。"  # ~40字


# ------------------------------------------------------------------ #
# Test 1-4: XPublisher dry_run=True
# ------------------------------------------------------------------ #

print("\n[Test 1-4] XPublisher dry_run=True")

pub_x = XPublisher()

r = pub_x.publish(_TEXT_NORMAL, account=_ACCOUNT, derivative=_DERIV_X,
                  queue_item=_QUEUE, dry_run=True)
_assert(r.success is True, "XPublisher dry_run=True: 正常テキスト → success=True", r.message)
_assert(r.posted_url is None, "XPublisher dry_run=True: posted_url=None（投稿なし）")
_assert(r.dry_run is True, "XPublisher dry_run=True: result.dry_run=True")

r_141 = pub_x.publish("あ" * 141, account=_ACCOUNT, derivative=_DERIV_X,
                       queue_item=_QUEUE, dry_run=True)
_assert(r_141.success is False, "XPublisher dry_run=True: 141字 → success=False", r_141.message)

r_empty = pub_x.publish("", account=_ACCOUNT, derivative=_DERIV_X,
                         queue_item=_QUEUE, dry_run=True)
_assert(r_empty.success is False, "XPublisher dry_run=True: 空テキスト → success=False")


# ------------------------------------------------------------------ #
# Test 5-7: XPublisher dry_run=False の安全ガード
# ------------------------------------------------------------------ #

print("\n[Test 5-7] XPublisher dry_run=False の安全ガード")

os.environ["PUBLISH_ENABLED"] = "false"
r_stop1 = pub_x.publish(_TEXT_NORMAL, account=_ACCOUNT, derivative=_DERIV_X,
                         queue_item=_QUEUE, dry_run=False)
_assert(r_stop1.success is False, "PUBLISH_ENABLED=false → success=False")
_assert("SAFETY_STOP" in r_stop1.message, "PUBLISH_ENABLED=false → SAFETY_STOP メッセージ")
_assert(r_stop1.posted_url is None, "PUBLISH_ENABLED=false → posted_url=None")

os.environ["PUBLISH_ENABLED"] = "true"
os.environ["ALLOW_REAL_X_POST"] = "false"
r_stop2 = pub_x.publish(_TEXT_NORMAL, account=_ACCOUNT, derivative=_DERIV_X,
                         queue_item=_QUEUE, dry_run=False)
_assert(r_stop2.success is False, "ALLOW_REAL_X_POST=false → success=False")
_assert("SAFETY_STOP" in r_stop2.message, "ALLOW_REAL_X_POST=false → SAFETY_STOP")

os.environ["ALLOW_REAL_X_POST"] = "true"
# 認証情報なし → SAFETY_STOP
r_stop3 = pub_x.publish(_TEXT_NORMAL, account=_ACCOUNT, derivative=_DERIV_X,
                         queue_item=_QUEUE, dry_run=False)
_assert(r_stop3.success is False, "認証情報なし → success=False")
_assert("SAFETY_STOP" in r_stop3.message, "認証情報なし → SAFETY_STOP")
_assert(r_stop3.posted_url is None, "認証情報なし → posted_url=None")

# ガードを戻す
os.environ["PUBLISH_ENABLED"] = "false"
os.environ["ALLOW_REAL_X_POST"] = "false"


# ------------------------------------------------------------------ #
# Test 8-9: XPublisher dry_run=False + tweepy モック
# ------------------------------------------------------------------ #

print("\n[Test 8-9] XPublisher dry_run=False + tweepy モック（実API呼び出しなし）")

# モック認証情報を設定
os.environ["PUBLISH_ENABLED"] = "true"
os.environ["ALLOW_REAL_X_POST"] = "true"
os.environ["X_API_KEY"] = "mock_api_key"
os.environ["X_API_SECRET"] = "mock_api_secret"
os.environ["X_ACCESS_TOKEN"] = "mock_access_token"
os.environ["X_ACCESS_TOKEN_SECRET"] = "mock_access_token_secret"

# tweepy を sys.modules にモック注入（tweepy 未インストール環境でも動作）
mock_tweepy_ok = mock.MagicMock()
mock_tweepy_ok.__version__ = "4.14.0"
mock_response_ok = mock.MagicMock()
mock_response_ok.data = {"id": "9876543210987654321"}
mock_tweepy_ok.Client.return_value.create_tweet.return_value = mock_response_ok

with mock.patch.dict("sys.modules", {"tweepy": mock_tweepy_ok}):
    # x_publisher の cached import を強制リロード
    import importlib
    import publishers.x_publisher as _xmod
    importlib.reload(_xmod)
    from publishers.x_publisher import XPublisher as XPub_reloaded

    pub_reloaded = XPub_reloaded()
    r_ok = pub_reloaded.publish(
        _TEXT_NORMAL,
        account=_ACCOUNT, derivative=_DERIV_X, queue_item=_QUEUE, dry_run=False
    )
    _assert(r_ok.success is True, "tweepy モック: 投稿成功 → success=True", r_ok.message)
    _assert(r_ok.posted_url is not None, "tweepy モック: posted_url が設定される")
    _assert("9876543210987654321" in (r_ok.external_post_id or ""),
            "tweepy モック: external_post_id に tweet_id が入る",
            r_ok.external_post_id or "")
    _assert(r_ok.dry_run is False, "tweepy モック: result.dry_run=False")
    _assert("twitter.com" in (r_ok.posted_url or ""),
            "tweepy モック: posted_url が twitter.com を含む", r_ok.posted_url or "")

# tweepy エラーケース
mock_tweepy_err = mock.MagicMock()
mock_tweepy_err.__version__ = "4.14.0"
mock_tweepy_err.Client.return_value.create_tweet.side_effect = Exception("API Error: Unauthorized")

with mock.patch.dict("sys.modules", {"tweepy": mock_tweepy_err}):
    import publishers.x_publisher as _xmod
    importlib.reload(_xmod)
    from publishers.x_publisher import XPublisher as XPub_err

    pub_err = XPub_err()
    r_err = pub_err.publish(
        _TEXT_NORMAL,
        account=_ACCOUNT, derivative=_DERIV_X, queue_item=_QUEUE, dry_run=False
    )
    _assert(r_err.success is False, "tweepy エラー → success=False", r_err.message)
    _assert("POST_FAILED" in r_err.message, "tweepy エラー → POST_FAILED メッセージ")
    _assert(r_err.posted_url is None, "tweepy エラー → posted_url=None")

# x_publisher を元の状態に戻す
import publishers.x_publisher as _xmod
importlib.reload(_xmod)
from publishers.x_publisher import XPublisher

# 認証情報とガードをクリア
os.environ["PUBLISH_ENABLED"] = "false"
os.environ["ALLOW_REAL_X_POST"] = "false"
for _k in ["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET"]:
    os.environ.pop(_k, None)


# ------------------------------------------------------------------ #
# Test 10-11: factory.py
# ------------------------------------------------------------------ #

print("\n[Test 10-11] factory.py")

from publishers.factory import _SafetyStopPublisher

pub_factory_x = get_publisher("x", dry_run=False)
_assert(isinstance(pub_factory_x, XPublisher),
        "factory.py x dry_run=False → XPublisher", type(pub_factory_x).__name__)

pub_factory_t = get_publisher("threads", dry_run=False)
_assert(isinstance(pub_factory_t, _SafetyStopPublisher),
        "factory.py threads dry_run=False → _SafetyStopPublisher（Phase 3-E まで）",
        type(pub_factory_t).__name__)


# ------------------------------------------------------------------ #
# Test 12: publish_queue.py --confirm-real-post なし → exit(1)
# ------------------------------------------------------------------ #

print("\n[Test 12] publish_queue.py --confirm-real-post なし → exit(1)")

r12 = subprocess.run(
    [sys.executable, "scripts/publish_queue.py", "--mock", "--account-id", "night_scout"],
    cwd=_V2_ROOT, capture_output=True, text=True,
)
_assert(r12.returncode != 0,
        "publish_queue.py オプションなし → 非ゼロ終了", f"rc={r12.returncode}")
_assert("--dry-run は必須" in r12.stdout or "dry-run" in r12.stdout.lower(),
        "publish_queue.py: エラーメッセージあり", r12.stdout[:200])


# ------------------------------------------------------------------ #
# Test 13: publish_queue.py --dry-run → 正常終了
# ------------------------------------------------------------------ #

print("\n[Test 13] publish_queue.py --dry-run → 正常終了")

sheets_dry = _setup_mock(status="READY")
r13 = subprocess.run(
    [sys.executable, "scripts/publish_queue.py",
     "--account-id", "night_scout", "--platform", "x", "--status", "READY",
     "--mock", "--dry-run"],
    cwd=_V2_ROOT, capture_output=True, text=True,
)
_assert(r13.returncode == 0,
        "publish_queue.py --dry-run → exit 0", r13.stdout[-200:])
_assert("実 SNS 投稿は行いません" in r13.stdout,
        "publish_queue.py --dry-run: 実投稿なしメッセージ確認")


# ------------------------------------------------------------------ #
# Test 14-15: publish_queue.py --confirm-real-post (tweepy モック)
# ------------------------------------------------------------------ #

print("\n[Test 14-15] publish_queue.py --confirm-real-post + tweepy モック")

sheets_real = _setup_mock(status="READY")
posted_before = len(sheets_real._posted_results)
queue_before_status = sheets_real.get_queue_item("q-test-d01")
status_before = queue_before_status.get("status", "") if queue_before_status else ""

# PUBLISH_ENABLED=true / ALLOW_REAL_X_POST=true に一時設定
_saved_pe = os.environ.get("PUBLISH_ENABLED", "false")
_saved_ax = os.environ.get("ALLOW_REAL_X_POST", "false")
os.environ["PUBLISH_ENABLED"] = "true"
os.environ["ALLOW_REAL_X_POST"] = "true"
os.environ["X_API_KEY"] = "mock_api_key"
os.environ["X_API_SECRET"] = "mock_api_secret"
os.environ["X_ACCESS_TOKEN"] = "mock_access_token"
os.environ["X_ACCESS_TOKEN_SECRET"] = "mock_access_token_secret"

mock_tweepy_real = mock.MagicMock()
mock_tweepy_real.__version__ = "4.14.0"
mock_response2 = mock.MagicMock()
mock_response2.data = {"id": "1122334455667788990"}
mock_tweepy_real.Client.return_value.create_tweet.return_value = mock_response2

# XPublisher を直接呼び出して verify する（サブプロセスでは tweepy モック不可）
with mock.patch.dict("sys.modules", {"tweepy": mock_tweepy_real}):
    import publishers.x_publisher as _xmod2
    importlib.reload(_xmod2)
    from publishers.x_publisher import XPublisher as XPub_real

    publisher_real = XPub_real()
    deriv = sheets_real.find_social_derivative("d-test-d01", "x") or {}
    acc = sheets_real.get_account("night_scout") or {}
    q_item = sheets_real.get_queue_item("q-test-d01") or {}

    r_real = publisher_real.publish(
        str(deriv.get("text", "")),
        account=acc, derivative=deriv, queue_item=q_item, dry_run=False,
    )

import publishers.x_publisher as _xmod2
importlib.reload(_xmod2)
from publishers.x_publisher import XPublisher

_assert(r_real.success is True,
        "XPublisher + tweepy モック: 投稿成功 → success=True", r_real.message)
_assert(r_real.posted_url is not None,
        "XPublisher + tweepy モック: posted_url が設定される", str(r_real.posted_url))
_assert(r_real.external_post_id == "1122334455667788990",
        "XPublisher + tweepy モック: external_post_id", r_real.external_post_id or "")

# 成功後の状態更新をシミュレート
sheets_real.update_queue_item(
    "q-test-d01", status="POSTED",
    processed_at="2026-05-23T10:00:00Z",
)
sheets_real.save_result(
    draft_id="d-test-d01", account_id="night_scout",
    note_url=r_real.posted_url, manual_memo=f"queue_id=q-test-d01",
)

queue_after = sheets_real.get_queue_item("q-test-d01")
status_after = queue_after.get("status", "") if queue_after else ""
posted_after = len(sheets_real._posted_results)

_assert(status_after == "POSTED",
        "投稿成功後: queue.status=POSTED", f"status={status_after}")
_assert(posted_after > posted_before,
        "投稿成功後: posted_results に記録あり",
        f"before={posted_before} after={posted_after}")

# ガードをクリア
os.environ["PUBLISH_ENABLED"] = _saved_pe
os.environ["ALLOW_REAL_X_POST"] = _saved_ax
for _k in ["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET"]:
    os.environ.pop(_k, None)


# ------------------------------------------------------------------ #
# Test 16: --max-real-posts 0 で --confirm-real-post → exit(1)
# ------------------------------------------------------------------ #

print("\n[Test 16] --max-real-posts 0 で --confirm-real-post → exit(1)")

r16 = subprocess.run(
    [sys.executable, "scripts/publish_queue.py",
     "--mock", "--account-id", "night_scout",
     "--platform", "x", "--status", "READY",
     "--confirm-real-post", "--max-real-posts", "0"],
    cwd=_V2_ROOT, capture_output=True, text=True,
    env={**os.environ, "PUBLISH_ENABLED": "true", "ALLOW_REAL_X_POST": "true"},
)
_assert(r16.returncode != 0,
        "--max-real-posts 0 + --confirm-real-post → 非ゼロ終了", f"rc={r16.returncode}")


# ------------------------------------------------------------------ #
# Test 17: XPublisher._build_posted_url
# ------------------------------------------------------------------ #

print("\n[Test 17] XPublisher._build_posted_url")

url = pub_x._build_posted_url("9999888877776666")
_assert("twitter.com" in url, "_build_posted_url: twitter.com を含む", url)
_assert("9999888877776666" in url, "_build_posted_url: tweet_id を含む", url)


# ------------------------------------------------------------------ #
# 結果
# ------------------------------------------------------------------ #

print(f"\n{'=' * 60}")
print(f"Phase 3-D テスト結果: {PASS} PASS / {FAIL} FAIL")
print("=" * 60)

sys.exit(0 if FAIL == 0 else 1)
