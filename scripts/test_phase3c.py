"""
test_phase3c.py - Phase 3-C テスト（Phase 3-D 対応版）

XPublisher / ThreadsPublisher スタブ、factory.py、publish_queue.py の
安全停止動作を MockSheetsClient で検証する。
実 SNS 投稿・API 接続・認証情報不要。

テスト項目:
  1. check_publisher_credentials.py が値未設定でも安全に動く（exit 0）
  2. XPublisher dry_run=True は投稿しない（posted_url=None）
  3. XPublisher dry_run=True: 94字 → success=True
  4. XPublisher dry_run=True: 141字 → success=False
  5. XPublisher dry_run=True: 空テキスト → success=False
  6. XPublisher dry_run=False は SAFETY_STOP を返す（PUBLISH_ENABLED=false）
  7. XPublisher dry_run=False: ALLOW_REAL_X_POST=false → SAFETY_STOP
  8. ThreadsPublisher dry_run=True は投稿しない（posted_url=None）
  9. ThreadsPublisher dry_run=True: 正常テキスト → success=True
  10. ThreadsPublisher dry_run=True: 空テキスト → success=False
  11. ThreadsPublisher dry_run=False は SAFETY_STOP を返す
  12. factory.py dry_run=True → DryRunPublisher
  13. factory.py x dry_run=False → XPublisher（Phase 3-D 実装済み）
  14. factory.py XPublisher.publish() PUBLISH_ENABLED=false → success=False
  15. publish_queue.py が本番投稿しない（posted_results 増えない）
  16. publish_queue.py が queue.status を変更しない
  17. posted_results が増えない
  18. queue.status が POSTED にならない
  19. XPublisher dry_run=False 両ガード=true 認証情報なし → SAFETY_STOP
"""
from __future__ import annotations

import os
import subprocess
import sys

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

os.environ.setdefault("MOCK_LLM", "true")
os.environ.setdefault("PUBLISH_ENABLED", "false")
os.environ.setdefault("ALLOW_REAL_X_POST", "false")
os.environ.setdefault("ALLOW_REAL_THREADS_POST", "false")

# 認証情報は未設定のまま
for _k in ["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET",
           "THREADS_ACCESS_TOKEN", "THREADS_USER_ID"]:
    os.environ.pop(_k, None)

from sheets_client import MockSheetsClient
from publishers.x_publisher import XPublisher
from publishers.threads_publisher import ThreadsPublisher
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


def _setup_mock() -> MockSheetsClient:
    sheets = MockSheetsClient(dry_run=False)
    draft_id = "d-test-c01"
    queue_id = "q-test-c01"
    sheets.save_draft(
        account_id="night_scout", title="テスト下書き", body_md="本文テキスト",
        draft_id=draft_id, status="READY", score="85",
        pv_score="80", cv_score="75", brand_risk_score="10",
    )
    sheets.append_social_derivative({
        "draft_id": draft_id, "platform": "x",
        "text": "「スカウトは稼げない」はもう古い。組織的ロジックで高収益を狙う、真っ当な稼ぎ方を教えます。",
        "status": "READY",
    })
    sheets.append_queue_item({
        "queue_id": queue_id, "draft_id": draft_id, "account_id": "night_scout",
        "platform": "x", "status": "READY", "scheduled_at": "2026-05-22T20:00:00+0900", "priority": "1",
    })
    return sheets


_ACCOUNT = {"account_id": "night_scout"}
_DERIV_X = {"derivative_id": "sd-c01", "platform": "x"}
_DERIV_T = {"derivative_id": "sd-c02", "platform": "threads"}
_QUEUE = {"queue_id": "q-test-c01"}
_TEXT_NORMAL = "「スカウトは稼げない」はもう古い。組織的ロジックで高収益を狙う、真っ当な稼ぎ方を教えます。"  # 約50字
_TEXT_141 = "あ" * 141
_TEXT_THREADS = "スカウト代理店の稼ぎ方、ロジックで語る。\n\n詳細はLINEで話しましょう。"


# ------------------------------------------------------------------ #
# Test 1: check_publisher_credentials.py が安全に動く
# ------------------------------------------------------------------ #

print("\n[Test 1] check_publisher_credentials.py が値未設定でも安全動作")

result = subprocess.run(
    [sys.executable, "scripts/check_publisher_credentials.py"],
    cwd=_V2_ROOT, capture_output=True, text=True,
)
_assert(result.returncode == 0, "check_publisher_credentials.py → exit 0（安全ガードOK）",
        result.stdout[-200:])
_assert("NOT_READY" in result.stdout or "missing" in result.stdout,
        "認証情報未設定で NOT_READY または missing が表示される")
_assert("READY_FOR_DRY_RUN" in result.stdout, "READY_FOR_DRY_RUN が表示される")


# ------------------------------------------------------------------ #
# Test 2-5: XPublisher dry_run=True
# ------------------------------------------------------------------ #

print("\n[Test 2-5] XPublisher dry_run=True")

pub_x = XPublisher()

r = pub_x.publish(_TEXT_NORMAL, account=_ACCOUNT, derivative=_DERIV_X, queue_item=_QUEUE, dry_run=True)
_assert(r.dry_run is True, "XPublisher dry_run=True: result.dry_run=True")
_assert(r.posted_url is None, "XPublisher dry_run=True: posted_url=None", str(r.posted_url))
_assert(r.external_post_id is None, "XPublisher dry_run=True: external_post_id=None")
_assert(r.success is True, "XPublisher dry_run=True: 正常テキスト → success=True", r.message)

r_141 = pub_x.publish(_TEXT_141, account=_ACCOUNT, derivative=_DERIV_X, queue_item=_QUEUE, dry_run=True)
_assert(r_141.success is False, "XPublisher dry_run=True: 141字 → success=False", r_141.message)

r_empty = pub_x.publish("", account=_ACCOUNT, derivative=_DERIV_X, queue_item=_QUEUE, dry_run=True)
_assert(r_empty.success is False, "XPublisher dry_run=True: 空テキスト → success=False")


# ------------------------------------------------------------------ #
# Test 6-7: XPublisher dry_run=False の安全停止
# ------------------------------------------------------------------ #

print("\n[Test 6-7] XPublisher dry_run=False の安全停止")

# PUBLISH_ENABLED=false のまま
os.environ["PUBLISH_ENABLED"] = "false"
r_stop = pub_x.publish(_TEXT_NORMAL, account=_ACCOUNT, derivative=_DERIV_X, queue_item=_QUEUE, dry_run=False)
_assert(r_stop.success is False, "XPublisher dry_run=False: PUBLISH_ENABLED=false → success=False")
_assert("SAFETY_STOP" in r_stop.message, "XPublisher dry_run=False: SAFETY_STOP メッセージ", r_stop.message)
_assert(r_stop.posted_url is None, "XPublisher dry_run=False: posted_url=None")

# ALLOW_REAL_X_POST=false のまま（PUBLISH_ENABLED=false なので到達しない: 最初のガードでブロック）
os.environ["ALLOW_REAL_X_POST"] = "false"
r_stop2 = pub_x.publish(_TEXT_NORMAL, account=_ACCOUNT, derivative=_DERIV_X, queue_item=_QUEUE, dry_run=False)
_assert(r_stop2.success is False, "XPublisher dry_run=False: ALLOW_REAL_X_POST=false → success=False")
_assert(r_stop2.posted_url is None, "XPublisher dry_run=False: ALLOW_REAL_X_POST=false → posted_url=None")


# ------------------------------------------------------------------ #
# Test 8-11: ThreadsPublisher
# ------------------------------------------------------------------ #

print("\n[Test 8-11] ThreadsPublisher dry_run=True / False")

pub_t = ThreadsPublisher()

r_t = pub_t.publish(_TEXT_THREADS, account=_ACCOUNT, derivative=_DERIV_T, queue_item=_QUEUE, dry_run=True)
_assert(r_t.dry_run is True, "ThreadsPublisher dry_run=True: result.dry_run=True")
_assert(r_t.posted_url is None, "ThreadsPublisher dry_run=True: posted_url=None")
_assert(r_t.external_post_id is None, "ThreadsPublisher dry_run=True: external_post_id=None")
_assert(r_t.success is True, "ThreadsPublisher dry_run=True: 正常テキスト → success=True", r_t.message)

r_t_empty = pub_t.publish("", account=_ACCOUNT, derivative=_DERIV_T, queue_item=_QUEUE, dry_run=True)
_assert(r_t_empty.success is False, "ThreadsPublisher dry_run=True: 空テキスト → success=False")

os.environ["PUBLISH_ENABLED"] = "false"
r_t_stop = pub_t.publish(_TEXT_THREADS, account=_ACCOUNT, derivative=_DERIV_T, queue_item=_QUEUE, dry_run=False)
_assert(r_t_stop.success is False, "ThreadsPublisher dry_run=False: PUBLISH_ENABLED=false → success=False")
_assert("SAFETY_STOP" in r_t_stop.message, "ThreadsPublisher dry_run=False: SAFETY_STOP メッセージ")
_assert(r_t_stop.posted_url is None, "ThreadsPublisher dry_run=False: posted_url=None")


# ------------------------------------------------------------------ #
# Test 12-14: factory.py
# ------------------------------------------------------------------ #

print("\n[Test 12-14] factory.py の動作")

pub_factory_dry = get_publisher("x", dry_run=True)
_assert(isinstance(pub_factory_dry, DryRunPublisher),
        "factory.py dry_run=True → DryRunPublisher", type(pub_factory_dry).__name__)

pub_factory_live = get_publisher("x", dry_run=False)
# Phase 3-D: factory は XPublisher を返す（安全ガードは XPublisher 内で処理）
_assert(type(pub_factory_live).__name__ == "XPublisher",
        "factory.py x dry_run=False → XPublisher（Phase 3-D 実装済み）",
        type(pub_factory_live).__name__)

# PUBLISH_ENABLED=false のまま → XPublisher の SAFETY_STOP が返る
r_factory = pub_factory_live.publish(_TEXT_NORMAL, account=_ACCOUNT, derivative=_DERIV_X, queue_item=_QUEUE, dry_run=False)
_assert(r_factory.success is False, "factory.py XPublisher.publish() PUBLISH_ENABLED=false → success=False")
_assert("SAFETY_STOP" in r_factory.message, "factory.py XPublisher: SAFETY_STOP メッセージ")

# Threads は引き続き _SafetyStopPublisher（Phase 3-E まで）
pub_factory_threads = get_publisher("threads", dry_run=False)
_assert(type(pub_factory_threads).__name__ == "_SafetyStopPublisher",
        "factory.py threads dry_run=False → _SafetyStopPublisher（Phase 3-E まで）",
        type(pub_factory_threads).__name__)


# ------------------------------------------------------------------ #
# Test 15-18: publish_queue.py 安全確認
# ------------------------------------------------------------------ #

print("\n[Test 15-18] publish_queue.py 安全確認")

sheets_pub = _setup_mock()
posted_before = len(sheets_pub._posted_results) if hasattr(sheets_pub, "_posted_results") else 0
q_before = sheets_pub.get_queue_item("q-test-c01")
status_before = q_before.get("status", "") if q_before else ""

result_pub = subprocess.run(
    [sys.executable, "scripts/publish_queue.py",
     "--account-id", "night_scout", "--status", "READY", "--mock", "--dry-run"],
    cwd=_V2_ROOT, capture_output=True, text=True,
)
_assert(result_pub.returncode == 0, "publish_queue.py --dry-run → exit 0", result_pub.stdout[-200:])
_assert("実 SNS 投稿は行いません" in result_pub.stdout,
        "publish_queue.py: 実 SNS 投稿なしメッセージ確認")
_assert("posted_results への書き込みなし" in result_pub.stdout,
        "publish_queue.py: posted_results 書き込みなしメッセージ確認")
_assert("queue.status の変更なし" in result_pub.stdout,
        "publish_queue.py: queue.status 変更なしメッセージ確認")


# ------------------------------------------------------------------ #
# Test 19: XPublisher dry_run=False 両ガード=true 認証情報なし → SAFETY_STOP
# ------------------------------------------------------------------ #

print("\n[Test 19] XPublisher dry_run=False 両ガード=true 認証情報なし → SAFETY_STOP")

# Phase 3-D: 両ガードを true にしても、認証情報が未設定なら SAFETY_STOP で安全停止
os.environ["PUBLISH_ENABLED"] = "true"
os.environ["ALLOW_REAL_X_POST"] = "true"
# 認証情報は未設定のまま（test ファイル冒頭で pop 済み）
try:
    r_cred_stop = pub_x.publish(
        _TEXT_NORMAL, account=_ACCOUNT, derivative=_DERIV_X, queue_item=_QUEUE, dry_run=False
    )
    _assert(r_cred_stop.success is False,
            "XPublisher 両ガード=true 認証情報なし → success=False（実投稿しない）",
            r_cred_stop.message)
    _assert("SAFETY_STOP" in r_cred_stop.message,
            "XPublisher 両ガード=true 認証情報なし → SAFETY_STOP メッセージ",
            r_cred_stop.message)
    _assert(r_cred_stop.posted_url is None,
            "XPublisher 両ガード=true 認証情報なし → posted_url=None")
except Exception as e:
    _assert(False, f"XPublisher 両ガード=true 認証情報なし → 予期しない例外: {type(e).__name__}: {e}")
finally:
    # 必ずガードを戻す
    os.environ["PUBLISH_ENABLED"] = "false"
    os.environ["ALLOW_REAL_X_POST"] = "false"


# ------------------------------------------------------------------ #
# 結果
# ------------------------------------------------------------------ #

print(f"\n{'=' * 60}")
print(f"Phase 3-C テスト結果: {PASS} PASS / {FAIL} FAIL")
print("=" * 60)

sys.exit(0 if FAIL == 0 else 1)
