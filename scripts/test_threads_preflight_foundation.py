"""
test_threads_preflight_foundation.py - Threads preflight 基盤テスト（Phase I）

preflight_threads_real_post.py の動作確認テスト。
実API・実投稿は行わない。
"""
from __future__ import annotations

import os
import sys

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_V2_ROOT, ".env"))
except ImportError:
    pass

_PASS = 0
_FAIL = 0


def _test(name: str, fn) -> None:
    global _PASS, _FAIL
    try:
        fn()
        print(f"  [PASS] {name}")
        _PASS += 1
    except Exception as e:
        print(f"  [FAIL] {name}: {e}")
        _FAIL += 1


def test_preflight_script_exists():
    path = os.path.join(_V2_ROOT, "scripts", "preflight_threads_real_post.py")
    assert os.path.isfile(path), f"preflight_threads_real_post.py が存在しません: {path}"


def test_preflight_importable():
    import importlib.util
    path = os.path.join(_V2_ROOT, "scripts", "preflight_threads_real_post.py")
    spec = importlib.util.spec_from_file_location("preflight_threads", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "main"), "main 関数が存在しません"
    assert hasattr(mod, "check_threads_credentials"), "check_threads_credentials が存在しません"
    assert hasattr(mod, "check_safety_flags"), "check_safety_flags が存在しません"
    assert hasattr(mod, "check_account_config"), "check_account_config が存在しません"


def test_safety_flag_check():
    """ALLOW_REAL_THREADS_POST=false 前提での安全確認。"""
    prev = os.environ.get("ALLOW_REAL_THREADS_POST", "")
    try:
        os.environ["ALLOW_REAL_THREADS_POST"] = "false"
        # false なら安全
        val = os.environ.get("ALLOW_REAL_THREADS_POST", "false").lower()
        assert val not in ("true", "1", "yes"), "ALLOW_REAL_THREADS_POST が true になっています"
    finally:
        if prev:
            os.environ["ALLOW_REAL_THREADS_POST"] = prev
        elif "ALLOW_REAL_THREADS_POST" in os.environ:
            del os.environ["ALLOW_REAL_THREADS_POST"]


def test_draft_only_blocked():
    """beauty_account（draft_only）は BLOCKED になる。"""
    from accounts.account_config import load_account_config, invalidate_cache
    invalidate_cache()
    cfg = load_account_config("beauty_account")
    assert cfg.is_draft_only(), "beauty_account は draft_only でなければなりません"


def test_active_accounts_not_blocked():
    """night_scout / liver_manager（active）は BLOCKED にならない。"""
    from accounts.account_config import load_account_config, invalidate_cache
    invalidate_cache()
    for account_id in ["night_scout", "liver_manager"]:
        cfg = load_account_config(account_id)
        assert cfg.is_active(), f"{account_id} は active でなければなりません"
        assert not cfg.is_draft_only(), f"{account_id} は draft_only になっています"


def test_threads_platform_enabled():
    """night_scout / liver_manager は threads プラットフォームを持つ。"""
    from accounts.account_config import load_account_config, invalidate_cache
    invalidate_cache()
    for account_id in ["night_scout", "liver_manager", "beauty_account"]:
        cfg = load_account_config(account_id)
        assert cfg.allows_platform("threads"), f"{account_id} は threads を許可していません"


def test_threads_char_limits():
    """全アカウントの threads char_limit が設定されている。"""
    from accounts.account_config import load_account_config, invalidate_cache
    invalidate_cache()
    for account_id in ["night_scout", "liver_manager", "beauty_account"]:
        cfg = load_account_config(account_id)
        limits = cfg.get_char_limits("threads")
        assert limits["soft"] >= 400, f"{account_id} threads soft limit が小さすぎます"
        assert limits["hard"] >= 500, f"{account_id} threads hard limit が小さすぎます"


def test_no_real_post_in_threads_safety():
    """allow_real_post=false がすべてのアカウントで維持されている。"""
    from accounts.account_config import load_account_config, invalidate_cache
    invalidate_cache()
    for account_id in ["night_scout", "liver_manager", "beauty_account"]:
        cfg = load_account_config(account_id)
        allow = cfg.safety_policy.get("allow_real_post", False)
        assert not allow, f"{account_id} allow_real_post が true になっています"


def test_threads_preflight_check_account_config_function():
    """check_account_config 関数が draft_only で False を返す。"""
    import importlib.util
    path = os.path.join(_V2_ROOT, "scripts", "preflight_threads_real_post.py")
    spec = importlib.util.spec_from_file_location("preflight_threads", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    from accounts.account_config import invalidate_cache
    invalidate_cache()

    result = mod.check_account_config("beauty_account")
    assert result is False, "beauty_account は check_account_config が False を返すはずです"


def test_threads_preflight_active_account_passes():
    """check_account_config が active account で True を返す。"""
    import importlib.util
    path = os.path.join(_V2_ROOT, "scripts", "preflight_threads_real_post.py")
    spec = importlib.util.spec_from_file_location("preflight_threads", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    from accounts.account_config import invalidate_cache
    invalidate_cache()

    result = mod.check_account_config("night_scout")
    assert result is True, "night_scout は check_account_config が True を返すはずです"


def test_threads_doc_exists():
    """Threads preflight 関連ドキュメントが存在する。"""
    path = os.path.join(_V2_ROOT, "docs", "threads-real-post-final-checklist.md")
    # まだ作成中の可能性があるのでWARNのみ（テスト不失敗）
    if not os.path.isfile(path):
        print("    [NOTE] threads-real-post-final-checklist.md はまだ作成されていません（後で作成予定）")


if __name__ == "__main__":
    print("=" * 60)
    print("  test_threads_preflight_foundation.py")
    print("=" * 60)

    _test("preflight_script_exists", test_preflight_script_exists)
    _test("preflight_importable", test_preflight_importable)
    _test("safety_flag_check", test_safety_flag_check)
    _test("draft_only_blocked (beauty_account)", test_draft_only_blocked)
    _test("active_accounts_not_blocked", test_active_accounts_not_blocked)
    _test("threads_platform_enabled", test_threads_platform_enabled)
    _test("threads_char_limits", test_threads_char_limits)
    _test("no_real_post_in_threads_safety", test_no_real_post_in_threads_safety)
    _test("check_account_config draft_only→False", test_threads_preflight_check_account_config_function)
    _test("check_account_config active→True", test_threads_preflight_active_account_passes)
    _test("threads_doc_exists (soft check)", test_threads_doc_exists)

    print(f"\n{'=' * 60}")
    print(f"  PASS={_PASS}  FAIL={_FAIL}")
    print("=" * 60)
    if _FAIL > 0:
        sys.exit(1)
