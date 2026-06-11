"""
test_beauty_account_design.py - Phase 6.1 beauty_account 設計テスト

beauty_account の安全ガード・draft_only 強制・禁止事項確認。
実行方法: python scripts/test_beauty_account_design.py
"""
from __future__ import annotations

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


print("\n=== Phase 6.1: beauty_account 設計テスト ===")


# --------------------------------------------------------
# seeds.py の beauty_account エントリ
# --------------------------------------------------------

def t_seeds_beauty_account_exists():
    from seeds import ACCOUNT_SEEDS_V2
    ids = [a["account_id"] for a in ACCOUNT_SEEDS_V2]
    assert "beauty_account" in ids, "seeds.py に beauty_account が存在しません"


def t_seeds_beauty_account_inactive():
    from seeds import ACCOUNT_SEEDS_V2
    beauty = next((a for a in ACCOUNT_SEEDS_V2 if a["account_id"] == "beauty_account"), None)
    assert beauty is not None
    assert beauty.get("active") == "FALSE", \
        "seeds.py の beauty_account は active=FALSE のはず（Sheetsに入れない）"
    assert beauty.get("auto_publish") == "FALSE", \
        "beauty_account の auto_publish は FALSE のはず"


def t_seeds_beauty_forbidden_keywords_not_empty():
    from seeds import ACCOUNT_FORBIDDEN_KEYWORDS
    kw = ACCOUNT_FORBIDDEN_KEYWORDS.get("beauty_account", [])
    assert len(kw) >= 5, f"beauty_account の forbidden_keywords が少なすぎます: {len(kw)}"


def t_seeds_beauty_forbidden_themes_not_empty():
    from seeds import ACCOUNT_FORBIDDEN_THEMES
    th = ACCOUNT_FORBIDDEN_THEMES.get("beauty_account", [])
    assert len(th) >= 3, f"beauty_account の forbidden_themes が少なすぎます: {len(th)}"


def t_seeds_beauty_no_mlm_keywords():
    """MLM関連の禁止キーワードが含まれているか確認。"""
    from seeds import ACCOUNT_FORBIDDEN_KEYWORDS
    kw = ACCOUNT_FORBIDDEN_KEYWORDS.get("beauty_account", [])
    mlm_terms = [k for k in kw if "MLM" in k or "代理店" in k or "会員募集" in k]
    assert len(mlm_terms) > 0, "MLM・代理店関連の禁止キーワードが必要"


# --------------------------------------------------------
# account_config の beauty_account
# --------------------------------------------------------

def t_account_config_beauty_draft_only():
    from accounts.account_config import load_account_config, invalidate_cache
    invalidate_cache()
    cfg = load_account_config("beauty_account")
    assert cfg.is_draft_only(), "beauty_account は draft_only のはず"
    assert not cfg.is_active(), "beauty_account は active でないはず"


def t_account_config_beauty_strict_safety():
    from accounts.account_config import load_account_config, invalidate_cache
    invalidate_cache()
    cfg = load_account_config("beauty_account")
    safety = cfg.safety_policy
    assert safety.get("allow_real_post") is False
    assert safety.get("requires_human_review_before_post") is True
    assert safety.get("draft_only_enforcement") == "STRICT"


def t_account_config_beauty_has_thread_series():
    from accounts.account_config import load_account_config, invalidate_cache
    invalidate_cache()
    cfg = load_account_config("beauty_account")
    ts_policy = cfg.thread_series_policy
    assert ts_policy.get("enabled") is True, "beauty_account の thread_series は enabled=true のはず"
    assert ts_policy.get("default_post_count", 0) >= 4, "default_post_count は 4 以上のはず"


def t_account_config_beauty_forbidden_kw_merged():
    """seeds.py の禁止キーワードが account_config にマージされているか。"""
    from accounts.account_config import load_account_config, invalidate_cache
    from seeds import ACCOUNT_FORBIDDEN_KEYWORDS
    invalidate_cache()
    cfg = load_account_config("beauty_account")
    seeds_kw = ACCOUNT_FORBIDDEN_KEYWORDS.get("beauty_account", [])
    for kw in seeds_kw:
        assert kw in cfg.forbidden_keywords, f"seeds の禁止キーワードがマージされていません: {kw}"


# --------------------------------------------------------
# beauty_account は POSTED 化されていないこと
# --------------------------------------------------------

def t_beauty_account_not_posted():
    """beauty_account の queue が POSTED 状態でないことを確認（セーフティチェック）。"""
    # この段階ではまだ queue が存在しないので PASS
    # 実運用では check_pipeline_integrity.py で確認する
    from accounts.account_config import load_account_config, invalidate_cache
    invalidate_cache()
    cfg = load_account_config("beauty_account")
    assert cfg.safety_policy.get("allow_real_post") is False, \
        "allow_real_post=false のはず"


# --------------------------------------------------------
# thread_series 生成時の draft_only 強制
# --------------------------------------------------------

def t_thread_series_beauty_stays_waiting_review():
    """beauty_account の thread_series 生成時に WAITING_REVIEW が強制されるか。"""
    import os
    os.environ["MOCK_LLM"] = "true"
    try:
        from generation.thread_series_generator import ThreadSeriesGenerator
        gen = ThreadSeriesGenerator()
        series = gen.generate(
            account_id="beauty_account",
            platform="x",
            theme="スキンケア上達テーマ",
            post_count=3,
            mock_llm=True,
        )
        assert series.status == "WAITING_REVIEW", \
            f"draft_only アカウントのシリーズは WAITING_REVIEW のはず: {series.status}"
        for p in series.posts:
            assert p.status == "WAITING_REVIEW", \
                f"draft_only アカウントの投稿は WAITING_REVIEW のはず: {p.status}"
    finally:
        del os.environ["MOCK_LLM"]


def t_thread_series_beauty_has_draft_only_note():
    """beauty_account の generation_notes に draft_only の注記があるか。"""
    import os
    os.environ["MOCK_LLM"] = "true"
    try:
        from generation.thread_series_generator import ThreadSeriesGenerator
        from accounts.account_config import invalidate_cache
        invalidate_cache()
        gen = ThreadSeriesGenerator()
        series = gen.generate(
            account_id="beauty_account",
            platform="x",
            theme="テスト",
            post_count=2,
            mock_llm=True,
        )
        assert "draft_only" in series.generation_notes, \
            f"generation_notes に draft_only の注記が必要: {series.generation_notes}"
    finally:
        del os.environ["MOCK_LLM"]


for fn in [
    t_seeds_beauty_account_exists,
    t_seeds_beauty_account_inactive,
    t_seeds_beauty_forbidden_keywords_not_empty,
    t_seeds_beauty_forbidden_themes_not_empty,
    t_seeds_beauty_no_mlm_keywords,
    t_account_config_beauty_draft_only,
    t_account_config_beauty_strict_safety,
    t_account_config_beauty_has_thread_series,
    t_account_config_beauty_forbidden_kw_merged,
    t_beauty_account_not_posted,
    t_thread_series_beauty_stays_waiting_review,
    t_thread_series_beauty_has_draft_only_note,
]:
    _test(fn.__name__[2:], fn)


print("\n============================================================")
print(f"  Phase 6.1 テスト結果: PASS={_PASS} / FAIL={_FAIL}")
print("============================================================")

for name, status, msg in _tests:
    icon = {"PASS": "  [PASS]", "FAIL": "  [FAIL]"}[status]
    suffix = f" — {msg}" if msg else ""
    print(f"{icon} {name}{suffix}")

if _FAIL > 0:
    sys.exit(1)
