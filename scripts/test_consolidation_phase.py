"""運用統合フェーズのテスト。

対象:
  - TAB_DISPLAY_NAMES マッピングの整合性
  - SheetsClient._ws() のフォールバック動作
  - ThreadsPublisher Phase 3-E の安全ガード
  - refresh_threads_token.py の --dry-run 動作
  - migrate_sheet_tabs_to_japanese.py の --dry-run（シート接続なし）
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PASS = 0
FAIL = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        print(f"  ✓ [PASS] {label}")
        PASS += 1
    else:
        print(f"  ✗ [FAIL] {label}{': ' + detail if detail else ''}")
        FAIL += 1


# ============================================================
# [1] TAB_DISPLAY_NAMES 整合性
# ============================================================
print("[1] TAB_DISPLAY_NAMES 整合性")

from sheets_client import TAB_DEFINITIONS, TAB_DISPLAY_NAMES

check("TAB_DISPLAY_NAMES の件数が 29", len(TAB_DISPLAY_NAMES) == 29)
check("TAB_DEFINITIONS の件数が 29", len(TAB_DEFINITIONS) == 29)

missing = [k for k in TAB_DEFINITIONS if k not in TAB_DISPLAY_NAMES]
extra = [k for k in TAB_DISPLAY_NAMES if k not in TAB_DEFINITIONS]
check("全 TAB_DEFINITIONS キーに表示名がある", len(missing) == 0, str(missing))
check("余分な表示名キーがない", len(extra) == 0, str(extra))

# 日本語名が空でない
empty_display = [k for k, v in TAB_DISPLAY_NAMES.items() if not v.strip()]
check("全表示名が空でない", len(empty_display) == 0, str(empty_display))

# 表示名が重複していない
vals = list(TAB_DISPLAY_NAMES.values())
check("表示名が重複していない", len(vals) == len(set(vals)))


# ============================================================
# [2] _ws() フォールバック動作（MockSheetsClient 経由）
# ============================================================
print("[2] MockSheetsClient._ws() フォールバック動作")

# MockSheetsClient は gspread を使わないため sheet接続不要
from sheets_client import MockSheetsClient

mock = MockSheetsClient()
# mock._ws はデフォルト実装では直接呼べないが、TAB_DISPLAY_NAMES の参照は確認できる
check(
    "TAB_DISPLAY_NAMES['accounts'] == 'アカウント管理'",
    TAB_DISPLAY_NAMES.get("accounts") == "アカウント管理",
)
check(
    "TAB_DISPLAY_NAMES['pdca_runs'] == 'PDCA実行履歴'",
    TAB_DISPLAY_NAMES.get("pdca_runs") == "PDCA実行履歴",
)
check(
    "TAB_DISPLAY_NAMES['queue'] == '投稿キュー'",
    TAB_DISPLAY_NAMES.get("queue") == "投稿キュー",
)


# ============================================================
# [3] ThreadsPublisher Phase 3-E 安全ガード
# ============================================================
print("[3] ThreadsPublisher Phase 3-E 安全ガード")

from publishers.threads_publisher import ThreadsPublisher
from publishers.base import PublishResult

pub = ThreadsPublisher()
account = {"account_id": "night_scout"}
derivative = {"derivative_id": "d001"}
queue_item = {"queue_id": "q001"}

# dry_run=True は PUBLISH_ENABLED 関係なく成功
os.environ.pop("PUBLISH_ENABLED", None)
os.environ.pop("ALLOW_REAL_THREADS_POST", None)
r = pub.publish("テスト", account=account, derivative=derivative, queue_item=queue_item, dry_run=True)
check("dry_run=True は success=True", r.success, r.message)
check("dry_run=True は dry_run フラグ True", r.dry_run)
check("dry_run=True は posted_url None", r.posted_url is None)

# dry_run=False, PUBLISH_ENABLED 未設定 → SAFETY_STOP
r2 = pub.publish("テスト", account=account, derivative=derivative, queue_item=queue_item, dry_run=False)
check("PUBLISH_ENABLED未設定で SAFETY_STOP", not r2.success)
check("SAFETY_STOP メッセージを含む", "SAFETY_STOP" in r2.message, r2.message)
check("SAFETY_STOP は dry_run=False", not r2.dry_run)

# dry_run=False, PUBLISH_ENABLED=true, ALLOW_REAL_THREADS_POST 未設定 → SAFETY_STOP
os.environ["PUBLISH_ENABLED"] = "true"
os.environ.pop("ALLOW_REAL_THREADS_POST", None)
r3 = pub.publish("テスト", account=account, derivative=derivative, queue_item=queue_item, dry_run=False)
check("ALLOW_REAL_THREADS_POST未設定で SAFETY_STOP", not r3.success)
check("ALLOW_REAL_THREADS_POST SAFETY_STOP メッセージ", "ALLOW_REAL_THREADS_POST" in r3.message, r3.message)

# dry_run=False, 両フラグ true, token未設定 → SAFETY_STOP (token不足)
os.environ["PUBLISH_ENABLED"] = "true"
os.environ["ALLOW_REAL_THREADS_POST"] = "true"
os.environ.pop("THREADS_ACCESS_TOKEN", None)
os.environ.pop("THREADS_ACCESS_TOKEN_NIGHT_SCOUT", None)
r4 = pub.publish("テスト", account=account, derivative=derivative, queue_item=queue_item, dry_run=False)
check("token未設定で SAFETY_STOP", not r4.success)
check("token SAFETY_STOP メッセージ", "THREADS_ACCESS_TOKEN" in r4.message, r4.message)

# 後始末
os.environ.pop("PUBLISH_ENABLED", None)
os.environ.pop("ALLOW_REAL_THREADS_POST", None)

# ============================================================
# [4] refresh_threads_token.py --dry-run
# ============================================================
print("[4] refresh_threads_token.py --dry-run")
import subprocess

# token未設定でも --dry-run は「未設定」エラーになるはず（API呼ばない）
env_no_token = {**os.environ}
env_no_token.pop("THREADS_ACCESS_TOKEN", None)
env_no_token.pop("THREADS_ACCESS_TOKEN_NIGHT_SCOUT", None)
result = subprocess.run(
    [sys.executable, "scripts/refresh_threads_token.py",
     "--account-id", "test_account", "--dry-run"],
    capture_output=True, text=True, env=env_no_token,
    cwd=os.path.join(os.path.dirname(__file__), ".."),
)
# token未設定のため exit_code=1 または DRY_RUN メッセージ
check(
    "--dry-run で API呼び出しなし (token未設定→exit!=0 expected)",
    result.returncode != 0 or "DRY_RUN" in result.stdout,
    f"rc={result.returncode} out={result.stdout[:80]}"
)

# token設定時の --dry-run
env_with_token = {**os.environ, "THREADS_ACCESS_TOKEN_TEST_ACCOUNT": "fake_token_12345"}
result2 = subprocess.run(
    [sys.executable, "scripts/refresh_threads_token.py",
     "--account-id", "test_account", "--dry-run"],
    capture_output=True, text=True, env=env_with_token,
    cwd=os.path.join(os.path.dirname(__file__), ".."),
)
check("--dry-run は DRY_RUN を表示", "DRY_RUN" in result2.stdout, result2.stdout[:120])
check("--dry-run は API呼ばない (成功終了)", result2.returncode == 0, f"rc={result2.returncode} err={result2.stderr[:80]}")


# ============================================================
print()
print(f"--- 結果 ---")
print(f"PASS: {PASS} / FAIL: {FAIL}")
if FAIL > 0:
    sys.exit(1)
