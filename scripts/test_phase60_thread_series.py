"""
test_phase60_thread_series.py - Phase 6.2 thread_series テスト

thread_series_generator の動作確認・安全ガード・フィクスチャ整合性。
実行方法: python scripts/test_phase60_thread_series.py
"""
from __future__ import annotations

import json
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


print("\n=== Phase 6.2: thread_series テスト ===")


# --------------------------------------------------------
# ファイル存在確認
# --------------------------------------------------------

def t_thread_series_generator_exists():
    p = os.path.join(_V2_ROOT, "src", "generation", "thread_series_generator.py")
    assert os.path.isfile(p), "src/generation/thread_series_generator.py が存在しません"


def t_generate_script_exists():
    p = os.path.join(_V2_ROOT, "scripts", "generate_thread_series.py")
    assert os.path.isfile(p), "scripts/generate_thread_series.py が存在しません"


def t_review_script_exists():
    p = os.path.join(_V2_ROOT, "scripts", "review_thread_series.py")
    assert os.path.isfile(p), "scripts/review_thread_series.py が存在しません"


def t_approve_script_exists():
    p = os.path.join(_V2_ROOT, "scripts", "approve_thread_series.py")
    assert os.path.isfile(p), "scripts/approve_thread_series.py が存在しません"


# --------------------------------------------------------
# フィクスチャ存在確認
# --------------------------------------------------------

def t_fixture_sample_thread_series():
    p = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_thread_series.json")
    assert os.path.isfile(p), "tests/fixtures/sample_thread_series.json が存在しません"


def t_fixture_thread_series_x():
    p = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_thread_series_x.json")
    assert os.path.isfile(p)


def t_fixture_thread_series_threads():
    p = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_thread_series_threads.json")
    assert os.path.isfile(p)


def t_fixture_beauty_thread_series_x():
    p = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_beauty_thread_series_x.json")
    assert os.path.isfile(p)


def t_fixture_beauty_thread_series_threads():
    p = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_beauty_thread_series_threads.json")
    assert os.path.isfile(p)


# --------------------------------------------------------
# フィクスチャ内容確認
# --------------------------------------------------------

def t_fixture_sample_all_waiting_review():
    p = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_thread_series.json")
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    assert d["status"] == "WAITING_REVIEW"
    for post in d["posts"]:
        assert post["status"] == "WAITING_REVIEW", \
            f"投稿[{post['post_index']}] のステータスが WAITING_REVIEW でありません"


def t_fixture_beauty_draft_only_note():
    p = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_beauty_thread_series_x.json")
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    assert d["account_id"] == "beauty_account"
    assert d["status"] == "WAITING_REVIEW"
    notes = d.get("generation_notes", "")
    assert "draft_only" in notes or "_status_note" in d, \
        "beauty_account フィクスチャに draft_only の注記が必要"


# --------------------------------------------------------
# ThreadSeriesGenerator 動作テスト
# --------------------------------------------------------

def t_generate_night_scout_x():
    from generation.thread_series_generator import ThreadSeriesGenerator
    from accounts.account_config import invalidate_cache
    invalidate_cache()
    gen = ThreadSeriesGenerator()
    series = gen.generate(
        account_id="night_scout",
        platform="x",
        theme="夜職で月50万稼ぐ方法",
        post_count=4,
        mock_llm=True,
    )
    assert series.account_id == "night_scout"
    assert series.platform == "x"
    assert series.post_count == 4
    assert series.status == "WAITING_REVIEW"
    assert len(series.posts) == 4


def t_generate_liver_manager_threads():
    from generation.thread_series_generator import ThreadSeriesGenerator
    from accounts.account_config import invalidate_cache
    invalidate_cache()
    gen = ThreadSeriesGenerator()
    series = gen.generate(
        account_id="liver_manager",
        platform="threads",
        theme="TikTokライブ収益化",
        post_count=3,
        mock_llm=True,
    )
    assert series.account_id == "liver_manager"
    assert series.platform == "threads"
    assert series.post_count == 3


def t_generate_beauty_account():
    from generation.thread_series_generator import ThreadSeriesGenerator
    from accounts.account_config import invalidate_cache
    invalidate_cache()
    gen = ThreadSeriesGenerator()
    series = gen.generate(
        account_id="beauty_account",
        platform="x",
        theme="スキンケア上達",
        post_count=4,
        mock_llm=True,
    )
    assert series.account_id == "beauty_account"
    assert series.status == "WAITING_REVIEW"
    # draft_only チェック
    assert "draft_only" in series.generation_notes


def t_all_posts_waiting_review():
    """全投稿のステータスが WAITING_REVIEW であること。"""
    from generation.thread_series_generator import ThreadSeriesGenerator
    from accounts.account_config import invalidate_cache
    invalidate_cache()
    gen = ThreadSeriesGenerator()
    for account_id in ("night_scout", "liver_manager", "beauty_account"):
        series = gen.generate(
            account_id=account_id,
            platform="x",
            theme="テスト",
            post_count=3,
            mock_llm=True,
        )
        for p in series.posts:
            assert p.status == "WAITING_REVIEW", \
                f"{account_id} 投稿[{p.post_index}] のステータスが WAITING_REVIEW でありません: {p.status}"


def t_series_id_format():
    from generation.thread_series_generator import ThreadSeriesGenerator
    from accounts.account_config import invalidate_cache
    invalidate_cache()
    gen = ThreadSeriesGenerator()
    series = gen.generate(account_id="night_scout", platform="x", theme="test", mock_llm=True)
    assert series.series_id.startswith("ts_night_scout_x_"), \
        f"series_id のフォーマットが不正: {series.series_id}"


def t_root_hook_is_first_post():
    from generation.thread_series_generator import ThreadSeriesGenerator
    from accounts.account_config import invalidate_cache
    invalidate_cache()
    gen = ThreadSeriesGenerator()
    series = gen.generate(account_id="night_scout", platform="x", theme="テスト", mock_llm=True)
    assert series.root_hook == series.posts[0].text, "root_hook は最初の投稿テキストのはず"


def t_post_count_respects_limit():
    from generation.thread_series_generator import ThreadSeriesGenerator
    from accounts.account_config import invalidate_cache
    invalidate_cache()
    gen = ThreadSeriesGenerator()
    series = gen.generate(
        account_id="night_scout", platform="x", theme="テスト", post_count=2, mock_llm=True
    )
    assert len(series.posts) <= 2, f"post_count=2 のはずが {len(series.posts)} 投稿"


def t_mock_content_is_account_aware():
    """各アカウントのモックコンテンツが異なること（account-aware）。"""
    from generation.thread_series_generator import ThreadSeriesGenerator
    from accounts.account_config import invalidate_cache
    invalidate_cache()
    gen = ThreadSeriesGenerator()
    ns = gen.generate(account_id="night_scout", platform="x", theme="test", mock_llm=True)
    ba = gen.generate(account_id="beauty_account", platform="x", theme="test", mock_llm=True)
    assert ns.posts[0].text != ba.posts[0].text, \
        "night_scout と beauty_account のモックコンテンツが同じ（account-aware になっていない）"


def t_to_dict_serializable():
    """ThreadSeries.to_dict() が JSON シリアライズ可能か確認。"""
    from generation.thread_series_generator import ThreadSeriesGenerator
    from accounts.account_config import invalidate_cache
    invalidate_cache()
    gen = ThreadSeriesGenerator()
    series = gen.generate(account_id="night_scout", platform="x", theme="テスト", mock_llm=True)
    d = series.to_dict()
    json_str = json.dumps(d, ensure_ascii=False)
    assert len(json_str) > 0


def t_no_real_post_in_generator():
    """generator 内に実投稿コードが存在しないことを確認。"""
    p = os.path.join(_V2_ROOT, "src", "generation", "thread_series_generator.py")
    src = open(p, encoding="utf-8").read()
    assert "ALLOW_REAL_X_POST" not in src, "generator 内に ALLOW_REAL_X_POST の参照は不要"
    assert "ALLOW_REAL_THREADS_POST" not in src, "generator 内に ALLOW_REAL_THREADS_POST の参照は不要"
    assert "publish" not in src.lower() or "publishers" not in src.lower(), \
        "generator が publish 処理を参照してはいけません"


for fn in [
    t_thread_series_generator_exists,
    t_generate_script_exists,
    t_review_script_exists,
    t_approve_script_exists,
    t_fixture_sample_thread_series,
    t_fixture_thread_series_x,
    t_fixture_thread_series_threads,
    t_fixture_beauty_thread_series_x,
    t_fixture_beauty_thread_series_threads,
    t_fixture_sample_all_waiting_review,
    t_fixture_beauty_draft_only_note,
    t_generate_night_scout_x,
    t_generate_liver_manager_threads,
    t_generate_beauty_account,
    t_all_posts_waiting_review,
    t_series_id_format,
    t_root_hook_is_first_post,
    t_post_count_respects_limit,
    t_mock_content_is_account_aware,
    t_to_dict_serializable,
    t_no_real_post_in_generator,
]:
    _test(fn.__name__[2:], fn)


print("\n============================================================")
print(f"  Phase 6.2 テスト結果: PASS={_PASS} / FAIL={_FAIL}")
print("============================================================")

for name, status, msg in _tests:
    icon = {"PASS": "  [PASS]", "FAIL": "  [FAIL]"}[status]
    suffix = f" — {msg}" if msg else ""
    print(f"{icon} {name}{suffix}")

if _FAIL > 0:
    sys.exit(1)
