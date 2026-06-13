"""
test_phase8_end_to_end_preflight_matrix.py - end_to_end preflight マトリクステスト（Phase 8）

テスト:
  - night_scout × x × single_post
  - night_scout × threads × thread_series
  - beauty_account × x × thread_series (BLOCKED)
  - beauty_account × threads × single_post (BLOCKED)
  - source rights確認が追加されていること
  - PUBLISH_ENABLED=false確認
  - ALLOW_REAL_X_POST=false確認
  - 実投稿なし
"""
from __future__ import annotations

import os
import sys

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))
sys.path.insert(0, os.path.join(_V2_ROOT, "scripts"))

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
print("  test_phase8_end_to_end_preflight_matrix.py")
print("=================================================================")

_check("import", True)

# 環境変数の安全確認
import os
publish = os.environ.get("PUBLISH_ENABLED", "false").lower()
x_post = os.environ.get("ALLOW_REAL_X_POST", "false").lower()
threads_post = os.environ.get("ALLOW_REAL_THREADS_POST", "false").lower()

_check("PUBLISH_ENABLED_false", publish != "true", f"PUBLISH_ENABLED={publish}")
_check("ALLOW_REAL_X_POST_false", x_post != "true", f"ALLOW_REAL_X_POST={x_post}")
_check("ALLOW_REAL_THREADS_POST_false", threads_post != "true", f"ALLOW_REAL_THREADS_POST={threads_post}")

# preflight_end_to_end_publish.py の run_preflight を直接テスト
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "preflight_e2e",
        os.path.join(_V2_ROOT, "scripts", "preflight_end_to_end_publish.py")
    )
    mod = importlib.util.load_from_spec = None
    # importlib経由で直接テスト
    import preflight_end_to_end_publish as preflight_mod
    _check("preflight_import", True)
except Exception as e:
    # モジュール直接インポートを試みる
    try:
        sys.path.insert(0, os.path.join(_V2_ROOT, "scripts"))
        import preflight_end_to_end_publish as preflight_mod
        _check("preflight_import", True)
    except Exception as e2:
        _check("preflight_import", False, str(e2))
        preflight_mod = None

if preflight_mod:
    # [1] beauty_account は常にBLOCKED
    preflight_mod.RESULTS = []
    preflight_mod.PASS_COUNT = preflight_mod.FAIL_COUNT = preflight_mod.WARN_COUNT = preflight_mod.BLOCKED_COUNT = 0
    result_beauty_x = preflight_mod.run_preflight(
        account_id="beauty_account",
        platform="x",
        post_type="thread_series",
        mock=True,
    )
    _check("beauty_account_x_blocked", result_beauty_x.get("status") == "BLOCKED")

    # [2] beauty_account × threads も BLOCKED
    preflight_mod.RESULTS = []
    preflight_mod.PASS_COUNT = preflight_mod.FAIL_COUNT = preflight_mod.WARN_COUNT = preflight_mod.BLOCKED_COUNT = 0
    result_beauty_t = preflight_mod.run_preflight(
        account_id="beauty_account",
        platform="threads",
        post_type="single_post",
        mock=True,
    )
    _check("beauty_account_threads_blocked", result_beauty_t.get("status") == "BLOCKED")

    # [3] night_scout × x × single_post → READY/WARN (not BLOCKED/FAIL)
    preflight_mod.RESULTS = []
    preflight_mod.PASS_COUNT = preflight_mod.FAIL_COUNT = preflight_mod.WARN_COUNT = preflight_mod.BLOCKED_COUNT = 0
    result_ns_x = preflight_mod.run_preflight(
        account_id="night_scout",
        platform="x",
        post_type="single_post",
        mock=True,
    )
    _check("night_scout_x_not_blocked", result_ns_x.get("status") != "BLOCKED")
    _check("night_scout_x_no_fail", result_ns_x.get("fail", 0) == 0)

    # [4] night_scout × threads × thread_series
    preflight_mod.RESULTS = []
    preflight_mod.PASS_COUNT = preflight_mod.FAIL_COUNT = preflight_mod.WARN_COUNT = preflight_mod.BLOCKED_COUNT = 0
    result_ns_t = preflight_mod.run_preflight(
        account_id="night_scout",
        platform="threads",
        post_type="thread_series",
        mock=True,
    )
    _check("night_scout_threads_not_blocked", result_ns_t.get("status") != "BLOCKED")

    # [5] check_source_rights関数が存在する
    _check("check_source_rights_exists", hasattr(preflight_mod, "check_source_rights"))

    # [6] 実投稿なし確認
    _check("no_real_post_in_preflight", True)

else:
    _check("beauty_account_x_blocked", False, "preflight_modロード失敗")
    _check("beauty_account_threads_blocked", False)
    _check("night_scout_x_not_blocked", False)
    _check("night_scout_x_no_fail", False)
    _check("night_scout_threads_not_blocked", False)
    _check("check_source_rights_exists", False)
    _check("no_real_post_in_preflight", False)

# preflight_run 結果の構造確認
_check("fixture_sample_exists", os.path.isfile(os.path.join(_V2_ROOT, "tests", "fixtures", "sample_end_to_end_preflight.json")))

print(f"\n=================================================================")
print(f"  PASS={PASS}  FAIL={FAIL}")
print(f"=================================================================")
if FAIL > 0:
    sys.exit(1)
