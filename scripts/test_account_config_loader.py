"""
test_account_config_loader.py - Phase 6.0 account_config ローダーテスト

実行方法: python scripts/test_account_config_loader.py
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


print("\n=== Phase 6.0: account_config ローダーテスト ===")

# --------------------------------------------------------
# account_config.py 存在確認
# --------------------------------------------------------

def t_account_config_module_exists():
    p = os.path.join(_V2_ROOT, "src", "accounts", "account_config.py")
    assert os.path.isfile(p), "src/accounts/account_config.py が存在しません"


def t_accounts_init_exists():
    p = os.path.join(_V2_ROOT, "src", "accounts", "__init__.py")
    assert os.path.isfile(p), "src/accounts/__init__.py が存在しません"


# --------------------------------------------------------
# config JSON 存在確認
# --------------------------------------------------------

def t_night_scout_json_exists():
    p = os.path.join(_V2_ROOT, "config", "accounts", "night_scout.json")
    assert os.path.isfile(p), "config/accounts/night_scout.json が存在しません"


def t_liver_manager_json_exists():
    p = os.path.join(_V2_ROOT, "config", "accounts", "liver_manager.json")
    assert os.path.isfile(p), "config/accounts/liver_manager.json が存在しません"


def t_beauty_account_json_exists():
    p = os.path.join(_V2_ROOT, "config", "accounts", "beauty_account.json")
    assert os.path.isfile(p), "config/accounts/beauty_account.json が存在しません"


def t_base_template_json_exists():
    p = os.path.join(_V2_ROOT, "config", "account_templates", "base_account.json")
    assert os.path.isfile(p), "config/account_templates/base_account.json が存在しません"


# --------------------------------------------------------
# JSON バリデーション
# --------------------------------------------------------

def t_night_scout_json_valid():
    p = os.path.join(_V2_ROOT, "config", "accounts", "night_scout.json")
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    assert d["account_id"] == "night_scout", "account_id が night_scout でありません"
    assert d["status"] == "active", "night_scout は active のはず"
    assert isinstance(d["platforms"], list), "platforms はリストのはず"
    assert "forbidden_keywords" in d, "forbidden_keywords が必要"
    assert "safety_policy" in d, "safety_policy が必要"


def t_liver_manager_json_valid():
    p = os.path.join(_V2_ROOT, "config", "accounts", "liver_manager.json")
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    assert d["account_id"] == "liver_manager"
    assert d["status"] == "active"
    assert "thread_series_policy" in d


def t_beauty_account_json_draft_only():
    p = os.path.join(_V2_ROOT, "config", "accounts", "beauty_account.json")
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    assert d["account_id"] == "beauty_account"
    assert d["status"] == "draft_only", f"beauty_account は draft_only のはず。実際: {d['status']}"
    assert d["safety_policy"].get("allow_real_post") is False, "allow_real_post は false のはず"


def t_beauty_account_forbidden_keywords():
    p = os.path.join(_V2_ROOT, "config", "accounts", "beauty_account.json")
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    kw = d.get("forbidden_keywords", [])
    assert len(kw) > 0, "beauty_account の forbidden_keywords が空"
    assert "MLM" in kw or "絶対に治る" in kw, "expected forbidden keywords not found"


# --------------------------------------------------------
# account_config ローダー動作テスト
# --------------------------------------------------------

def t_load_night_scout_config():
    from accounts.account_config import load_account_config, invalidate_cache
    invalidate_cache()
    cfg = load_account_config("night_scout")
    assert cfg.account_id == "night_scout"
    assert cfg.status == "active"
    assert cfg.is_active()
    assert not cfg.is_draft_only()
    assert len(cfg.forbidden_keywords) > 0


def t_load_liver_manager_config():
    from accounts.account_config import load_account_config, invalidate_cache
    invalidate_cache()
    cfg = load_account_config("liver_manager")
    assert cfg.account_id == "liver_manager"
    assert cfg.status == "active"
    assert cfg.is_active()


def t_load_beauty_account_config():
    from accounts.account_config import load_account_config, invalidate_cache
    invalidate_cache()
    cfg = load_account_config("beauty_account")
    assert cfg.account_id == "beauty_account"
    assert cfg.status == "draft_only"
    assert cfg.is_draft_only()
    assert not cfg.is_active()


def t_beauty_account_allow_real_post_false():
    from accounts.account_config import load_account_config, invalidate_cache
    invalidate_cache()
    cfg = load_account_config("beauty_account")
    assert cfg.safety_policy.get("allow_real_post") is False


def t_seeds_forbidden_merge():
    """seeds.py の禁止キーワードが account_config にマージされているか確認。"""
    from accounts.account_config import load_account_config, invalidate_cache
    from seeds import ACCOUNT_FORBIDDEN_KEYWORDS
    invalidate_cache()
    cfg = load_account_config("night_scout")
    seeds_kw = ACCOUNT_FORBIDDEN_KEYWORDS.get("night_scout", [])
    for kw in seeds_kw:
        assert kw in cfg.forbidden_keywords, f"seeds の禁止キーワードがマージされていません: {kw}"


def t_get_all_account_ids():
    from accounts.account_config import get_all_account_ids
    ids = get_all_account_ids()
    assert "night_scout" in ids, "night_scout が account_ids に含まれていません"
    assert "liver_manager" in ids, "liver_manager が account_ids に含まれていません"
    assert "beauty_account" in ids, "beauty_account が account_ids に含まれていません"


def t_is_draft_only_function():
    from accounts.account_config import is_draft_only, invalidate_cache
    invalidate_cache()
    assert is_draft_only("beauty_account"), "beauty_account は draft_only のはず"
    assert not is_draft_only("night_scout"), "night_scout は draft_only でないはず"


def t_is_active_function():
    from accounts.account_config import is_active, invalidate_cache
    invalidate_cache()
    assert is_active("night_scout"), "night_scout は active のはず"
    assert not is_active("beauty_account"), "beauty_account は active でないはず"


def t_get_char_limits():
    from accounts.account_config import load_account_config, invalidate_cache
    invalidate_cache()
    cfg = load_account_config("night_scout")
    limits_x = cfg.get_char_limits("x")
    assert limits_x["soft"] == 120
    assert limits_x["hard"] == 140
    limits_th = cfg.get_char_limits("threads")
    assert limits_th["soft"] == 500
    assert limits_th["hard"] == 800


def t_nonexistent_account_raises():
    from accounts.account_config import load_account_config, invalidate_cache
    invalidate_cache()
    try:
        load_account_config("nonexistent_account_xyz")
        assert False, "FileNotFoundError が発生するはず"
    except FileNotFoundError:
        pass


# --------------------------------------------------------
# seeds.py に beauty_account が追加されているか
# --------------------------------------------------------

def t_seeds_has_beauty_account():
    from seeds import ACCOUNT_SEEDS_V2
    ids = [a["account_id"] for a in ACCOUNT_SEEDS_V2]
    assert "beauty_account" in ids, "seeds.py に beauty_account が追加されていません"


def t_seeds_beauty_forbidden_keywords():
    from seeds import ACCOUNT_FORBIDDEN_KEYWORDS
    assert "beauty_account" in ACCOUNT_FORBIDDEN_KEYWORDS
    assert len(ACCOUNT_FORBIDDEN_KEYWORDS["beauty_account"]) > 0


def t_seeds_beauty_forbidden_themes():
    from seeds import ACCOUNT_FORBIDDEN_THEMES
    assert "beauty_account" in ACCOUNT_FORBIDDEN_THEMES
    assert len(ACCOUNT_FORBIDDEN_THEMES["beauty_account"]) > 0


for fn in [
    t_account_config_module_exists,
    t_accounts_init_exists,
    t_night_scout_json_exists,
    t_liver_manager_json_exists,
    t_beauty_account_json_exists,
    t_base_template_json_exists,
    t_night_scout_json_valid,
    t_liver_manager_json_valid,
    t_beauty_account_json_draft_only,
    t_beauty_account_forbidden_keywords,
    t_load_night_scout_config,
    t_load_liver_manager_config,
    t_load_beauty_account_config,
    t_beauty_account_allow_real_post_false,
    t_seeds_forbidden_merge,
    t_get_all_account_ids,
    t_is_draft_only_function,
    t_is_active_function,
    t_get_char_limits,
    t_nonexistent_account_raises,
    t_seeds_has_beauty_account,
    t_seeds_beauty_forbidden_keywords,
    t_seeds_beauty_forbidden_themes,
]:
    _test(fn.__name__[2:], fn)


print("\n============================================================")
print(f"  Phase 6.0 テスト結果: PASS={_PASS} / FAIL={_FAIL}")
print("============================================================")

for name, status, msg in _tests:
    icon = {"PASS": "  [PASS]", "FAIL": "  [FAIL]"}[status]
    suffix = f" — {msg}" if msg else ""
    print(f"{icon} {name}{suffix}")

if _FAIL > 0:
    sys.exit(1)
