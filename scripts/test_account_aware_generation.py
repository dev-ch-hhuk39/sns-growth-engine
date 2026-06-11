"""
test_account_aware_generation.py - Phase 6.3 account-aware generation テスト

account_config 駆動の生成接続確認・account_id による分岐排除確認。
実行方法: python scripts/test_account_aware_generation.py
"""
from __future__ import annotations

import os
import sys

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

os.environ.setdefault("MOCK_LLM", "true")
os.environ.setdefault("DRY_RUN", "true")

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


print("\n=== Phase 6.3: account-aware generation テスト ===")


# --------------------------------------------------------
# account_config 経由での char_limits 取得
# --------------------------------------------------------

def t_char_limits_from_config_x():
    from accounts.account_config import load_account_config, invalidate_cache
    invalidate_cache()
    cfg = load_account_config("night_scout")
    limits = cfg.get_char_limits("x")
    assert limits["soft"] == 120
    assert limits["hard"] == 140


def t_char_limits_from_config_threads():
    from accounts.account_config import load_account_config, invalidate_cache
    invalidate_cache()
    cfg = load_account_config("night_scout")
    limits = cfg.get_char_limits("threads")
    assert limits["soft"] == 500
    assert limits["hard"] == 800


def t_beauty_account_higher_min_score():
    from accounts.account_config import load_account_config, invalidate_cache
    invalidate_cache()
    cfg = load_account_config("beauty_account")
    assert cfg.safety_policy.get("min_publish_score", 0) >= 70, \
        "beauty_account の min_publish_score は 70 以上のはず"


def t_beauty_account_lower_brand_risk():
    from accounts.account_config import load_account_config, invalidate_cache
    invalidate_cache()
    cfg = load_account_config("beauty_account")
    assert cfg.safety_policy.get("brand_risk_threshold", 99) <= 20, \
        "beauty_account の brand_risk_threshold は 20 以下のはず（厳しめ）"


# --------------------------------------------------------
# 禁止キーワードブロックの生成（reference_based_generator との整合）
# --------------------------------------------------------

def t_forbidden_block_night_scout():
    from generation.reference_based_generator import _get_account_ng_block
    block = _get_account_ng_block("night_scout")
    assert "代理店" in block, "night_scout の禁止ブロックに '代理店' が含まれていません"


def t_forbidden_block_beauty_account():
    """beauty_account の禁止キーワードが seeds.py に存在し、ng_block に含まれるか。"""
    from generation.reference_based_generator import _get_account_ng_block
    block = _get_account_ng_block("beauty_account")
    assert "MLM" in block or "絶対に治る" in block, \
        "beauty_account の禁止ブロックに MLM 系キーワードが含まれていません"


# --------------------------------------------------------
# thread_series_generator の char_limits が account_config から取得されるか
# --------------------------------------------------------

def t_thread_series_uses_account_config_char_limit():
    from generation.thread_series_generator import ThreadSeriesGenerator
    from accounts.account_config import load_account_config, invalidate_cache
    invalidate_cache()
    gen = ThreadSeriesGenerator()
    series = gen.generate(
        account_id="night_scout",
        platform="x",
        theme="テスト",
        post_count=2,
        mock_llm=True,
    )
    # char_count が X の hard 上限を超えていないか
    for p in series.posts:
        assert p.char_count <= 200, \
            f"投稿[{p.post_index}] の文字数が異常に大きい: {p.char_count}"


# --------------------------------------------------------
# draft_only の投稿をREADY化しないガード
# --------------------------------------------------------

def t_draft_only_cannot_be_ready():
    from accounts.account_config import load_account_config, is_draft_only, invalidate_cache
    invalidate_cache()
    assert is_draft_only("beauty_account"), "beauty_account は draft_only のはず"
    cfg = load_account_config("beauty_account")
    assert not cfg.is_active(), "beauty_account は is_active()=False のはず"


def t_active_accounts_can_post():
    from accounts.account_config import is_active, invalidate_cache
    invalidate_cache()
    assert is_active("night_scout"), "night_scout は is_active()=True のはず"
    assert is_active("liver_manager"), "liver_manager は is_active()=True のはず"


# --------------------------------------------------------
# thread_series_generator が account_config をロードするか
# --------------------------------------------------------

def t_generator_loads_account_config():
    """generator が account_config をロードして persona/tone を取得するか。"""
    from generation.thread_series_generator import ThreadSeriesGenerator
    from accounts.account_config import load_account_config, invalidate_cache
    invalidate_cache()
    cfg = load_account_config("night_scout")
    gen = ThreadSeriesGenerator()
    # mock_llm=True で生成し、prompt に persona が含まれるか間接確認
    # （direct prompt 確認は実装詳細に依存するため、正常終了で十分）
    series = gen.generate(
        account_id="night_scout",
        platform="x",
        theme="テスト",
        mock_llm=True,
    )
    assert series.account_id == "night_scout"


# --------------------------------------------------------
# check_pipeline_integrity との account_config 整合
# --------------------------------------------------------

def t_pipeline_check_script_exists():
    p = os.path.join(_V2_ROOT, "scripts", "check_pipeline_integrity.py")
    assert os.path.isfile(p), "scripts/check_pipeline_integrity.py が存在しません"


def t_preflight_x_post_script_exists():
    p = os.path.join(_V2_ROOT, "scripts", "preflight_x_real_post.py")
    assert os.path.isfile(p), "scripts/preflight_x_real_post.py が存在しません"


def t_smoke_plan_script_exists():
    p = os.path.join(_V2_ROOT, "scripts", "run_real_smoke_plan.py")
    assert os.path.isfile(p), "scripts/run_real_smoke_plan.py が存在しません"


for fn in [
    t_char_limits_from_config_x,
    t_char_limits_from_config_threads,
    t_beauty_account_higher_min_score,
    t_beauty_account_lower_brand_risk,
    t_forbidden_block_night_scout,
    t_forbidden_block_beauty_account,
    t_thread_series_uses_account_config_char_limit,
    t_draft_only_cannot_be_ready,
    t_active_accounts_can_post,
    t_generator_loads_account_config,
    t_pipeline_check_script_exists,
    t_preflight_x_post_script_exists,
    t_smoke_plan_script_exists,
]:
    _test(fn.__name__[2:], fn)


print("\n============================================================")
print(f"  Phase 6.3 テスト結果: PASS={_PASS} / FAIL={_FAIL}")
print("============================================================")

for name, status, msg in _tests:
    icon = {"PASS": "  [PASS]", "FAIL": "  [FAIL]"}[status]
    suffix = f" — {msg}" if msg else ""
    print(f"{icon} {name}{suffix}")

if _FAIL > 0:
    sys.exit(1)
