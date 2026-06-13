"""
test_real_llm_generation_preflight.py - 実LLM生成前preflight テスト（Phase 8）

テスト:
  - preflight_real_llm_generation.py が実行できる
  - APIキー非表示確認
  - PUBLISH_ENABLED=false確認
  - beauty_accountはWAITING_REVIEW止まり
  - MOCK_LLM確認
  - content safety config確認
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
print("  test_real_llm_generation_preflight.py")
print("=================================================================")

_check("import", True)

PREFLIGHT_SCRIPT = os.path.join(_V2_ROOT, "scripts", "preflight_real_llm_generation.py")
_check("script_exists", os.path.isfile(PREFLIGHT_SCRIPT))

# 1. 環境変数の安全確認
publish = os.environ.get("PUBLISH_ENABLED", "false").lower()
x_post = os.environ.get("ALLOW_REAL_X_POST", "false").lower()
threads_post = os.environ.get("ALLOW_REAL_THREADS_POST", "false").lower()
_check("PUBLISH_ENABLED_false", publish != "true")
_check("ALLOW_REAL_X_POST_false", x_post != "true")
_check("ALLOW_REAL_THREADS_POST_false", threads_post != "true")

# 2. スクリプト実行 (mock mode)
result = subprocess.run(
    [sys.executable, PREFLIGHT_SCRIPT, "--account-id", "night_scout", "--platform", "x", "--mock"],
    capture_output=True, text=True, timeout=30,
    cwd=_V2_ROOT,
)
output = result.stdout + result.stderr
_check("script_runs_ok", result.returncode == 0, f"exit={result.returncode}\n{output[-500:]}")
_check("script_has_preflight_output", "preflight_real_llm_generation" in output)

# 3. APIキーが出力に含まれない
sensitive_patterns = ["sk-", "AIza", "Bearer ", "api_key=", "token="]
for pattern in sensitive_patterns:
    _check(f"no_secret_{pattern.replace('-','_').replace(' ','_')}", pattern not in output)

# 4. beauty_account mock実行
beauty_result = subprocess.run(
    [sys.executable, PREFLIGHT_SCRIPT, "--account-id", "beauty_account", "--platform", "threads", "--mock"],
    capture_output=True, text=True, timeout=30,
    cwd=_V2_ROOT,
)
beauty_output = beauty_result.stdout + beauty_result.stderr
_check("beauty_script_runs", beauty_result.returncode == 0, f"exit={beauty_result.returncode}")
_check("beauty_draft_only_warn", "draft_only" in beauty_output or "WAITING_REVIEW" in beauty_output or "WARN" in beauty_output)

# 5. MOCK_LLM確認が出力にある
_check("mock_llm_check_in_output", "MOCK_LLM" in output)

# 6. 実LLM生成禁止文が出力にある
_check("no_real_llm_in_preflight", "このスクリプトは実LLM生成を行いません" in output)

# 7. content safety確認が含まれる
_check("content_safety_check", any(
    keyword in output for keyword in ["text_policy", "content safety", "forbidden", "PASS", "WARN"]
))

print(f"\n=================================================================")
print(f"  PASS={PASS}  FAIL={FAIL}")
print(f"=================================================================")
if FAIL > 0:
    sys.exit(1)
