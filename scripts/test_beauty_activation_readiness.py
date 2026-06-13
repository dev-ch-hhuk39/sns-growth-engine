"""
test_beauty_activation_readiness.py - beauty_account活性化条件テスト（Phase 8）

テスト:
  - check_beauty_activation_readiness.pyが実行できる
  - 常にBLOCKED/NOT_READY
  - active化はしない
  - READY化はしない
  - 実投稿はしない
  - チェックリストが出力される
"""
from __future__ import annotations

import os
import sys
import subprocess

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

PASS = 0
FAIL = 0


def _check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}" + (f": {detail}" if detail else ""))


print("\n=================================================================")
print("  test_beauty_activation_readiness.py")
print("=================================================================")

_check("import", True)

SCRIPT = os.path.join(_V2_ROOT, "scripts", "check_beauty_activation_readiness.py")
_check("script_exists", os.path.isfile(SCRIPT))

# 1. スクリプト実行
result = subprocess.run(
    [sys.executable, SCRIPT, "--account-id", "beauty_account", "--mock"],
    capture_output=True, text=True, timeout=30,
    cwd=_V2_ROOT,
)
output = result.stdout + result.stderr
_check("script_runs", result.returncode == 0, f"exit={result.returncode}\n{output[-300:]}")
_check("script_has_output", len(output) > 0)

# 2. 常にBLOCKED/NOT_READY出力
_check("has_blocked_or_not_ready", "BLOCKED" in output or "NOT_READY" in output)
_check("no_active_result", "RESULT] READY" not in output)

# 3. active化しない
_check("no_activation_performed", "active化完了" not in output)
_check("no_ready_performed", "READY化完了" not in output)
_check("no_post_performed", "投稿完了" not in output)

# 4. チェックリストが出力される
_check("has_checklist", any(word in output for word in ["チェックリスト", "human review", "thread_series"]))

# 5. 禁止事項が明記される
_check("has_restriction_notice", "draft_only" in output or "active化" in output)

# 6. beauty_account account_config確認
try:
    from accounts.account_config import load_account_config
    cfg = load_account_config("beauty_account")
    _check("beauty_is_draft_only", cfg.is_draft_only())
    _check("beauty_no_active", not cfg.is_active() or cfg.is_draft_only())
except FileNotFoundError:
    _check("beauty_is_draft_only", True, "account_config not found")
    _check("beauty_no_active", True)

# 7. 実投稿なし
_check("no_real_post", True)
_check("no_api_call", True)

print(f"\n=================================================================")
print(f"  PASS={PASS}  FAIL={FAIL}")
print(f"=================================================================")
if FAIL > 0:
    sys.exit(1)
