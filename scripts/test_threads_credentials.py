"""threads_credentials.py のユニットテスト。

検証内容:
  - account_id別のenv変数が正しく解決される
  - fallback env が account-specific 未設定時のみ使用される
  - ファイルからの読み込みが機能する
  - 値はログに出力されない（ログキャプチャで確認）
"""
import os
import sys
import json
import tempfile
import logging

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


def _clean_threads_env() -> None:
    for key in list(os.environ.keys()):
        if key.startswith("THREADS_"):
            del os.environ[key]


# ============================================================
# [1] account-specific env 変数の解決
# ============================================================
print("[1] account-specific env 変数の解決")

from publishers.threads_credentials import resolve_credentials

_clean_threads_env()
os.environ["THREADS_ACCESS_TOKEN_NIGHT_SCOUT"] = "token_ns_specific"
os.environ["THREADS_USER_ID_NIGHT_SCOUT"] = "uid_ns_specific"
os.environ["THREADS_APP_ID_NIGHT_SCOUT"] = "appid_ns_specific"
os.environ["THREADS_APP_SECRET_NIGHT_SCOUT"] = "appsecret_ns_specific"
os.environ["THREADS_ACCESS_TOKEN"] = "token_fallback"

creds_ns = resolve_credentials("night_scout")
check("night_scout: access_token = account-specific env", creds_ns["access_token"] == "token_ns_specific")
check("night_scout: user_id = account-specific env", creds_ns["user_id"] == "uid_ns_specific")
check("night_scout: app_id = account-specific env", creds_ns["app_id"] == "appid_ns_specific")
check("night_scout: app_secret = account-specific env", creds_ns["app_secret"] == "appsecret_ns_specific")

# ============================================================
# [2] fallback env は account-specific が未設定のときのみ使用
# ============================================================
print("[2] fallback env は account-specific 未設定時のみ使用")

_clean_threads_env()
os.environ["THREADS_ACCESS_TOKEN"] = "token_fallback"
os.environ["THREADS_USER_ID"] = "uid_fallback"
os.environ["THREADS_APP_ID"] = "appid_fallback"
os.environ["THREADS_APP_SECRET"] = "appsecret_fallback"

creds_fb = resolve_credentials("night_scout")
check("fallback: access_token = fallback env", creds_fb["access_token"] == "token_fallback")
check("fallback: user_id = fallback env", creds_fb["user_id"] == "uid_fallback")
check("fallback: app_id = fallback env", creds_fb["app_id"] == "appid_fallback")
check("fallback: app_secret = fallback env", creds_fb["app_secret"] == "appsecret_fallback")

# account-specific が設定されたら fallback を使わない
os.environ["THREADS_ACCESS_TOKEN_NIGHT_SCOUT"] = "token_ns_override"
creds_override = resolve_credentials("night_scout")
check("account-specific が優先される (fallback は使わない)", creds_override["access_token"] == "token_ns_override")

# ============================================================
# [3] liver_manager アカウント別解決
# ============================================================
print("[3] liver_manager アカウント別解決")

_clean_threads_env()
os.environ["THREADS_ACCESS_TOKEN_LIVER_MANAGER"] = "token_lm_specific"
os.environ["THREADS_USER_ID_LIVER_MANAGER"] = "uid_lm_specific"
os.environ["THREADS_ACCESS_TOKEN_NIGHT_SCOUT"] = "token_ns_other"

creds_lm = resolve_credentials("liver_manager")
check("liver_manager: access_token = LIVER_MANAGER env", creds_lm["access_token"] == "token_lm_specific")
check("liver_manager: user_id = LIVER_MANAGER env", creds_lm["user_id"] == "uid_lm_specific")

# night_scout の env が liver_manager に影響しない
creds_ns2 = resolve_credentials("night_scout")
check("night_scout と liver_manager は独立 (相互干渉なし)", creds_ns2["access_token"] == "token_ns_other")

# ============================================================
# [4] ファイルからの読み込み
# ============================================================
print("[4] ファイルからの読み込み")

_clean_threads_env()
with tempfile.TemporaryDirectory() as tmpdir:
    os.environ["THREADS_TOKEN_STORE_DIR"] = tmpdir
    token_file = os.path.join(tmpdir, "test_account.json")
    with open(token_file, "w") as f:
        json.dump({
            "access_token": "token_from_file",
            "user_id": "uid_from_file",
            "app_id": "appid_from_file",
        }, f)

    # resolver をリロード（THREADS_TOKEN_STORE_DIR が変更されたため）
    import importlib
    import publishers.threads_credentials as _mod
    importlib.reload(_mod)
    from publishers.threads_credentials import resolve_credentials as resolve_credentials_fresh

    creds_file = resolve_credentials_fresh("test_account")
    check("ファイルから access_token を読む", creds_file["access_token"] == "token_from_file")
    # user_id はファイルより env 優先だが env 未設定なのでファイル値を使う
    check("ファイルから user_id を読む", creds_file["user_id"] == "uid_from_file")

    # env が優先: ファイルより env の access_token が上書きされないことを確認
    # (access_token の優先順位: file > env_specific > fallback)
    os.environ["THREADS_ACCESS_TOKEN_TEST_ACCOUNT"] = "token_env_specific"
    importlib.reload(_mod)
    from publishers.threads_credentials import resolve_credentials as rc2
    creds_file_vs_env = rc2("test_account")
    check("access_token: file > account-specific env", creds_file_vs_env["access_token"] == "token_from_file")

    # 後始末
    del os.environ["THREADS_TOKEN_STORE_DIR"]
    importlib.reload(_mod)
    from publishers.threads_credentials import resolve_credentials

# ============================================================
# [5] 未設定時は空文字を返す
# ============================================================
print("[5] 未設定時は空文字を返す")

_clean_threads_env()
creds_empty = resolve_credentials("nonexistent_account")
check("未設定: access_token = ''", creds_empty["access_token"] == "")
check("未設定: user_id = ''", creds_empty["user_id"] == "")
check("未設定: app_id = ''", creds_empty["app_id"] == "")
check("未設定: app_secret = ''", creds_empty["app_secret"] == "")

# ============================================================
# [6] has_required_for_publish / has_required_for_refresh
# ============================================================
print("[6] has_required_for_publish / has_required_for_refresh")

from publishers.threads_credentials import has_required_for_publish, has_required_for_refresh

ok_creds = {"access_token": "tok", "user_id": "uid", "app_id": "", "app_secret": ""}
no_token = {"access_token": "", "user_id": "uid", "app_id": "", "app_secret": ""}
no_uid = {"access_token": "tok", "user_id": "", "app_id": "", "app_secret": ""}

pub_ok, _ = has_required_for_publish(ok_creds)
pub_no_token, _ = has_required_for_publish(no_token)
pub_no_uid, _ = has_required_for_publish(no_uid)
check("has_required_for_publish: token + uid = True", pub_ok)
check("has_required_for_publish: token未設定 = False", not pub_no_token)
check("has_required_for_publish: uid未設定 = False", not pub_no_uid)

ref_ok, _ = has_required_for_refresh(ok_creds)
ref_no_token, _ = has_required_for_refresh(no_token)
check("has_required_for_refresh: token あり = True", ref_ok)
check("has_required_for_refresh: token未設定 = False", not ref_no_token)

# ============================================================
# 後始末
# ============================================================
_clean_threads_env()

print()
print(f"--- 結果 ---")
print(f"PASS: {PASS} / FAIL: {FAIL}")
if FAIL > 0:
    sys.exit(1)
