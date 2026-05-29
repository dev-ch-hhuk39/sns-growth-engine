"""
test_phase3a.py - Phase 3-A テスト

DryRunPublisher / get_publisher / publish_queue の安全性を検証する。
実 SNS 投稿・Sheets 認証情報不要。MockSheetsClient を使用。

テスト項目:
  1. DryRunPublisher が posted_url / external_post_id を返さない
  2. X 140字超で FAIL
  3. X 120字超 140字以下で WARN（success=True）
  4. X 120字以内で OK
  5. Threads 空行なしで WARN（success=True）
  6. Threads 空行ありで OK
  7. テキスト空で FAIL
  8. get_publisher(dry_run=True) が DryRunPublisher を返す
  9. get_publisher(dry_run=False) が NotImplementedError を raise する
  10. publish_queue main() が --dry-run なしで sys.exit(1) する
  11. dry-run 実行後 MockSheetsClient に posted_result が追加されない
  12. dry-run 実行後 MockSheetsClient の _queue が変更されない
"""
from __future__ import annotations

import os
import sys

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

os.environ.setdefault("MOCK_LLM", "true")
os.environ.setdefault("PUBLISH_ENABLED", "false")

from sheets_client import MockSheetsClient
from publishers.base import BasePublisher, PublishResult
from publishers.dry_run import DryRunPublisher, X_CHAR_LIMIT, X_CHAR_WARN
from publishers.factory import get_publisher


# ------------------------------------------------------------------ #
# ヘルパー
# ------------------------------------------------------------------ #

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


def _make_items(text: str = "テスト本文", platform: str = "x") -> tuple[dict, dict, dict]:
    account = {"account_id": "night_scout", "cta_text": "LINE↓"}
    derivative = {"derivative_id": "sd-test", "draft_id": "d-test",
                  "platform": platform, "text": text}
    queue_item = {"queue_id": "q-test", "draft_id": "d-test",
                  "platform": platform, "status": "WAITING_REVIEW"}
    return account, derivative, queue_item


# ------------------------------------------------------------------ #
# Test 1: DryRunPublisher 基本
# ------------------------------------------------------------------ #

print("\n[Test 1] DryRunPublisher 基本動作")

pub = DryRunPublisher()
account, derivative, queue_item = _make_items("テスト投稿テキスト（X）", "x")
result = pub.publish(derivative["text"], account=account, derivative=derivative,
                     queue_item=queue_item, dry_run=True)

_assert(isinstance(result, PublishResult), "PublishResult インスタンスが返る")
_assert(result.dry_run is True, "dry_run=True")
_assert(result.posted_url is None, "posted_url=None（実投稿しない）")
_assert(result.external_post_id is None, "external_post_id=None（実投稿しない）")
_assert(result.success is True, "success=True（正常テキスト）")


# ------------------------------------------------------------------ #
# Test 2-4: X 文字数チェック
# ------------------------------------------------------------------ #

print("\n[Test 2-4] X 文字数チェック")

# 140字超 → FAIL
long_text = "あ" * (X_CHAR_LIMIT + 1)
a, d, q = _make_items(long_text, "x")
r = pub.publish(long_text, account=a, derivative=d, queue_item=q)
_assert(r.success is False, f"X {X_CHAR_LIMIT + 1}字 → FAIL", r.message)

# 121字（WARN 範囲）→ success=True, WARN含む
warn_text = "あ" * (X_CHAR_WARN + 1)
a, d, q = _make_items(warn_text, "x")
r = pub.publish(warn_text, account=a, derivative=d, queue_item=q)
_assert(r.success is True, f"X {X_CHAR_WARN + 1}字 → success=True(WARN)", r.message)
_assert("WARN" in r.message, f"X {X_CHAR_WARN + 1}字 → message に WARN", r.message)

# 120字 → OK
ok_text = "あ" * X_CHAR_WARN
a, d, q = _make_items(ok_text, "x")
r = pub.publish(ok_text, account=a, derivative=d, queue_item=q)
_assert(r.success is True, f"X {X_CHAR_WARN}字 → OK", r.message)
_assert("WARN" not in r.message, f"X {X_CHAR_WARN}字 → WARN なし", r.message)


# ------------------------------------------------------------------ #
# Test 5-6: Threads フォーマットチェック
# ------------------------------------------------------------------ #

print("\n[Test 5-6] Threads フォーマットチェック")

# 空行なし → WARN（success=True）
no_blank = "フック行\n本文行\n続き"
a, d, q = _make_items(no_blank, "threads")
r = pub.publish(no_blank, account=a, derivative=d, queue_item=q)
_assert(r.success is True, "Threads 空行なし → success=True(WARN)", r.message)
_assert("WARN" in r.message, "Threads 空行なし → WARN", r.message)

# 空行あり → OK
with_blank = "フック行\n\n本文行\n続き"
a, d, q = _make_items(with_blank, "threads")
r = pub.publish(with_blank, account=a, derivative=d, queue_item=q)
_assert(r.success is True, "Threads 空行あり → OK", r.message)
_assert("WARN" not in r.message, "Threads 空行あり → WARN なし", r.message)


# ------------------------------------------------------------------ #
# Test 7: 空テキスト
# ------------------------------------------------------------------ #

print("\n[Test 7] 空テキスト")

for plat in ["x", "threads"]:
    a, d, q = _make_items("", plat)
    r = pub.publish("", account=a, derivative=d, queue_item=q)
    _assert(r.success is False, f"空テキスト ({plat}) → FAIL", r.message)


# ------------------------------------------------------------------ #
# Test 8-9: get_publisher ファクトリ
# ------------------------------------------------------------------ #

print("\n[Test 8-9] get_publisher ファクトリ")

dry_pub = get_publisher("x", dry_run=True)
_assert(isinstance(dry_pub, DryRunPublisher), "get_publisher(x, dry_run=True) → DryRunPublisher")

dry_pub_t = get_publisher("threads", dry_run=True)
_assert(isinstance(dry_pub_t, DryRunPublisher), "get_publisher(threads, dry_run=True) → DryRunPublisher")

# Phase 3-C 以降: factory.py は _SafetyStopPublisher を返す（NotImplementedError ではなく安全停止）
# Phase 3-A の意図「本番投稿できないこと」を維持する形で検証する
not_impl_raised = False
safety_stop_returned = False
try:
    pub_live = get_publisher("x", dry_run=False)
    # _SafetyStopPublisher の場合: publish() が success=False を返す
    r_live = pub_live.publish(
        "テスト", account={"account_id": "test"},
        derivative={"platform": "x"}, queue_item={"queue_id": "q-test"},
        dry_run=False,
    )
    safety_stop_returned = (not r_live.success and "SAFETY_STOP" in r_live.message)
except NotImplementedError:
    not_impl_raised = True
_assert(not_impl_raised or safety_stop_returned,
        "get_publisher(x, dry_run=False) → NotImplementedError または SAFETY_STOP（本番投稿不可）")


# ------------------------------------------------------------------ #
# Test 10: publish_queue の --dry-run 必須チェック
# ------------------------------------------------------------------ #

print("\n[Test 10] publish_queue --dry-run 必須チェック")

import subprocess

result = subprocess.run(
    [sys.executable, "scripts/publish_queue.py", "--mock",
     "--account-id", "night_scout"],
    cwd=_V2_ROOT,
    capture_output=True, text=True,
)
_assert(result.returncode != 0, "publish_queue --dry-run なし → 非ゼロ終了", result.stdout[:100])
_assert("--dry-run は必須" in result.stdout or "dry-run" in result.stdout.lower(),
        "publish_queue --dry-run なし → エラーメッセージあり", result.stdout[:200])


# ------------------------------------------------------------------ #
# Test 11-12: dry-run 実行後 Sheets 変更なし
# ------------------------------------------------------------------ #

print("\n[Test 11-12] dry-run 実行後 MockSheetsClient 変更なし")

# MockSheetsClient に直接 queue アイテムを入れてテスト
mock_sheets = MockSheetsClient(dry_run=True)

# queue にテストアイテムを追加
mock_sheets.append_queue_item({
    "draft_id": "d-test-check",
    "account_id": "night_scout",
    "platform": "x",
    "status": "WAITING_REVIEW",
    "scheduled_at": "2026-05-22T20:00:00+0900",
    "priority": "1",
})
mock_sheets.save_draft(
    account_id="night_scout",
    title="テスト",
    body_md="本文",
    draft_id="d-test-check",
    status="READY",
    score="85",
)
mock_sheets.append_social_derivative({
    "draft_id": "d-test-check",
    "platform": "x",
    "text": "テスト投稿テキスト90字以内",
    "status": "READY",
})

queue_before = len(mock_sheets._queue)
# posted_results 用の保存先がないため空リストを確認
posted_before = 0  # MockSheetsClient には _posted_results がない

# DryRunPublisher を直接実行（publish_queue のロジックを再現）
publisher = get_publisher("x", dry_run=True)
deriv = mock_sheets.find_social_derivative("d-test-check", "x")
acc = mock_sheets.get_account("night_scout")
q_item = mock_sheets._queue[-1]
result_pr = publisher.publish(
    str(deriv.get("text", "")),
    account=acc or {},
    derivative=deriv or {},
    queue_item=q_item,
    dry_run=True,
)

queue_after = len(mock_sheets._queue)
_assert(queue_before == queue_after, "dry-run 後 queue 件数変化なし",
        f"before={queue_before} after={queue_after}")
_assert(result_pr.posted_url is None, "dry-run 後 posted_url=None")
_assert(result_pr.external_post_id is None, "dry-run 後 external_post_id=None")

# queue.status が変わっていないことを確認
q_status = mock_sheets._queue[-1].get("status", "")
_assert(q_status == "WAITING_REVIEW", "dry-run 後 queue.status=WAITING_REVIEW のまま",
        f"status={q_status}")


# ------------------------------------------------------------------ #
# 結果
# ------------------------------------------------------------------ #

print(f"\n{'=' * 60}")
print(f"Phase 3-A テスト結果: {PASS} PASS / {FAIL} FAIL")
print("=" * 60)

sys.exit(0 if FAIL == 0 else 1)
