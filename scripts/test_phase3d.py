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
# Test 8-9: Product policy forbids all real X outbound requests
# ------------------------------------------------------------------ #

print("\n[Test 8-9] X real publishing is disabled by product policy")
os.environ["PUBLISH_ENABLED"] = "true"
os.environ["ALLOW_REAL_X_POST"] = "true"
os.environ["X_PUBLISHER_ENABLED"] = "true"
for key in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET"):
    os.environ[key] = "synthetic-test-value"

with mock.patch("requests.post", side_effect=AssertionError("X network forbidden")) as network:
    denied = XPublisher().publish(
        _TEXT_NORMAL, account=_ACCOUNT, derivative=_DERIV_X,
        queue_item=_QUEUE, dry_run=False,
    )
    _assert(not denied.success, "X forbidden despite all legacy env flags")
    _assert("X_REAL_POST_DISABLED_BY_PRODUCT_POLICY" in denied.message,
            "X product policy reason returned")
    _assert(denied.posted_url is None, "X no posted URL")
    _assert(denied.external_post_id is None, "X no external post ID")
    _assert(network.call_count == 0, "X no network request")
with mock.patch("requests.post", side_effect=AssertionError("X sink forbidden")) as network:
    denied_sink = XPublisher()._publish_with_oauth1(
        text=_TEXT_NORMAL, creds={}, account_id="night_scout",
        queue_id="q-test-d01", derivative_id="sd-d01",
    )
    _assert(not denied_sink.success, "direct X sink forbidden")
    _assert("X_HTTP_SINK_DISABLED_BY_PRODUCT_POLICY" in denied_sink.message,
            "X direct sink uses same immutable policy")
    _assert(network.call_count == 0, "direct X sink no network")

os.environ["PUBLISH_ENABLED"] = "false"
os.environ["ALLOW_REAL_X_POST"] = "false"
for key in ("X_PUBLISHER_ENABLED", "X_API_KEY", "X_API_SECRET",
            "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET"):
    os.environ.pop(key, None)


# ------------------------------------------------------------------ #
# Test 10-11: factory.py
# ------------------------------------------------------------------ #

print("\n[Test 10-11] factory.py")

from publishers.factory import _SafetyStopPublisher

pub_factory_x = get_publisher("x", dry_run=False)
_assert(isinstance(pub_factory_x, _SafetyStopPublisher),
        "factory.py x dry_run=False remains SAFETY_STOP", type(pub_factory_x).__name__)

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
# Test 14-15: Legacy X CLI refuses before Sheets/credential access
# ------------------------------------------------------------------ #

print("\n[Test 14-15] legacy X CLI cannot send or persist real posts")
sheets_real = _setup_mock(status="READY")
posted_before = len(sheets_real._posted_results)
queue_before = sheets_real.get_queue_item("q-test-d01")["status"]
env_test = {**os.environ,
            "PUBLISH_ENABLED": "true", "ALLOW_REAL_X_POST": "true",
            "X_PUBLISHER_ENABLED": "true"}
r_real_cli = subprocess.run(
    [sys.executable, "scripts/publish_queue.py",
     "--mock", "--account-id", "night_scout", "--platform", "x",
     "--status", "READY", "--confirm-real-post",
     "--queue-id", "q-test-d01", "--max-real-posts", "1"],
    cwd=_V2_ROOT, capture_output=True, text=True, env=env_test,
)
_assert(r_real_cli.returncode != 0,
        "legacy X CLI refuses real posting", str(r_real_cli.returncode))
_assert("X_REAL_POST_DISABLED_BY_PRODUCT_POLICY" in r_real_cli.stdout,
        "legacy X CLI reports immutable disable reason")
_assert(len(sheets_real._posted_results) == posted_before,
        "no posted_results mutation while X disabled")
_assert(sheets_real.get_queue_item("q-test-d01")["status"] == queue_before,
        "no queue status promotion while X disabled")


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
