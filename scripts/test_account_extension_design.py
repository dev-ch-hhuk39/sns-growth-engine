"""
test_account_extension_design.py - Phase 6.0 アカウント拡張設計テスト

設計・ドキュメント・フィクスチャの整合性確認。
実行方法: python scripts/test_account_extension_design.py
"""
from __future__ import annotations

import json
import os
import sys

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

_PASS = 0
_FAIL = 0
_tests: list[tuple[str, str, str]] = []


def _test(name: str, fn) -> None:
    global _PASS, _FAIL
    try:
        fn()
        _PASS += 1
        _tests.append((name, "PASS", ""))
    except AssertionError as e:
        _FAIL += 1
        _tests.append((name, "FAIL", str(e)))
    except Exception as e:
        _FAIL += 1
        _tests.append((name, "FAIL", f"{type(e).__name__}: {e}"))


print("\n=== Phase 6.0: アカウント拡張設計テスト ===")


# --------------------------------------------------------
# config/ ディレクトリ構造
# --------------------------------------------------------

def t_config_accounts_dir_exists():
    p = os.path.join(_V2_ROOT, "config", "accounts")
    assert os.path.isdir(p), "config/accounts/ ディレクトリが存在しません"


def t_config_account_templates_dir_exists():
    p = os.path.join(_V2_ROOT, "config", "account_templates")
    assert os.path.isdir(p), "config/account_templates/ ディレクトリが存在しません"


def t_three_account_configs_exist():
    accounts_dir = os.path.join(_V2_ROOT, "config", "accounts")
    json_files = [f for f in os.listdir(accounts_dir) if f.endswith(".json")]
    assert len(json_files) >= 3, f"config/accounts/ に3件以上のJSONが必要。現在: {len(json_files)}"


# --------------------------------------------------------
# フィクスチャ確認
# --------------------------------------------------------

def t_sample_account_extension_fixture():
    p = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_account_extension_config.json")
    assert os.path.isfile(p), "tests/fixtures/sample_account_extension_config.json が存在しません"
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    assert "account_id" in d
    assert "status" in d
    assert "safety_policy" in d


def t_sample_beauty_account_fixture():
    p = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_beauty_account_config.json")
    assert os.path.isfile(p), "tests/fixtures/sample_beauty_account_config.json が存在しません"
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    assert d.get("account_id") == "beauty_account"
    assert d.get("status") == "draft_only"


# --------------------------------------------------------
# gitignore: config/accounts/*.json が git 管理対象か
# --------------------------------------------------------

def t_gitignore_allows_account_json():
    gitignore_path = os.path.join(_V2_ROOT, ".gitignore")
    assert os.path.isfile(gitignore_path), ".gitignore が存在しません"
    content = open(gitignore_path, encoding="utf-8").read()
    assert "!config/accounts/*.json" in content, \
        ".gitignore に !config/accounts/*.json が必要（現在 *.json ルールで除外される）"


def t_gitignore_allows_account_templates_json():
    gitignore_path = os.path.join(_V2_ROOT, ".gitignore")
    content = open(gitignore_path, encoding="utf-8").read()
    assert "!config/account_templates/*.json" in content, \
        ".gitignore に !config/account_templates/*.json が必要"


# --------------------------------------------------------
# account_config の account_id 整合性
# --------------------------------------------------------

def t_all_configs_account_id_matches_filename():
    accounts_dir = os.path.join(_V2_ROOT, "config", "accounts")
    for filename in os.listdir(accounts_dir):
        if not filename.endswith(".json"):
            continue
        expected_id = filename[:-5]
        p = os.path.join(accounts_dir, filename)
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        actual_id = d.get("account_id", "")
        assert actual_id == expected_id, \
            f"{filename}: account_id({actual_id}) がファイル名({expected_id})と一致しません"


# --------------------------------------------------------
# status 整合性: beauty_account は draft_only
# --------------------------------------------------------

def t_beauty_account_is_draft_only():
    p = os.path.join(_V2_ROOT, "config", "accounts", "beauty_account.json")
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    assert d["status"] == "draft_only", f"beauty_account は draft_only のはず。実際: {d['status']}"


def t_existing_accounts_not_draft_only():
    for account_id in ("night_scout", "liver_manager"):
        p = os.path.join(_V2_ROOT, "config", "accounts", f"{account_id}.json")
        if not os.path.isfile(p):
            continue
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        assert d["status"] == "active", \
            f"{account_id} は active のはず。実際: {d['status']}"


# --------------------------------------------------------
# thread_series_policy の存在
# --------------------------------------------------------

def t_all_configs_have_thread_series_policy():
    accounts_dir = os.path.join(_V2_ROOT, "config", "accounts")
    for filename in os.listdir(accounts_dir):
        if not filename.endswith(".json"):
            continue
        p = os.path.join(accounts_dir, filename)
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        assert "thread_series_policy" in d, \
            f"{filename}: thread_series_policy が必要"


# --------------------------------------------------------
# safety_policy.allow_real_post チェック
# --------------------------------------------------------

def t_all_configs_allow_real_post_false():
    accounts_dir = os.path.join(_V2_ROOT, "config", "accounts")
    for filename in os.listdir(accounts_dir):
        if not filename.endswith(".json"):
            continue
        p = os.path.join(accounts_dir, filename)
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        safety = d.get("safety_policy", {})
        assert safety.get("allow_real_post") is False, \
            f"{filename}: safety_policy.allow_real_post は false のはず"


for fn in [
    t_config_accounts_dir_exists,
    t_config_account_templates_dir_exists,
    t_three_account_configs_exist,
    t_sample_account_extension_fixture,
    t_sample_beauty_account_fixture,
    t_gitignore_allows_account_json,
    t_gitignore_allows_account_templates_json,
    t_all_configs_account_id_matches_filename,
    t_beauty_account_is_draft_only,
    t_existing_accounts_not_draft_only,
    t_all_configs_have_thread_series_policy,
    t_all_configs_allow_real_post_false,
]:
    _test(fn.__name__[2:], fn)


print("\n============================================================")
print(f"  Phase 6.0 拡張設計テスト結果: PASS={_PASS} / FAIL={_FAIL}")
print("============================================================")

for name, status, msg in _tests:
    icon = {"PASS": "  [PASS]", "FAIL": "  [FAIL]"}[status]
    suffix = f" — {msg}" if msg else ""
    print(f"{icon} {name}{suffix}")

if _FAIL > 0:
    sys.exit(1)
