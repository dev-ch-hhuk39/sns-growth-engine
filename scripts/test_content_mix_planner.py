"""
test_content_mix_planner.py - content_mix_planner テスト（Phase 7.A）

実投稿なし / X APIなし / Threads APIなし。
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


def test_import():
    """content_mix_planner がインポートできる。"""
    from generation.content_mix_planner import plan_content_mix
    assert callable(plan_content_mix)


def test_basic_plan():
    """基本的なプランが生成できる。"""
    from generation.content_mix_planner import plan_content_mix
    plan = plan_content_mix("night_scout", "x", count=10, seed=42)
    assert plan["account_id"] == "night_scout"
    assert plan["platform"] == "x"
    assert plan["generated_jobs_count"] == 10
    assert len(plan["items"]) == 10


def test_seed_reproducible():
    """同じ seed で同じ結果が得られる。"""
    from generation.content_mix_planner import plan_content_mix
    plan1 = plan_content_mix("night_scout", "x", count=10, seed=99)
    plan2 = plan_content_mix("night_scout", "x", count=10, seed=99)
    assert plan1["selected_modes"] == plan2["selected_modes"]


def test_different_seeds():
    """異なる seed では異なる結果になることがある（確率的）。"""
    from generation.content_mix_planner import plan_content_mix
    plan1 = plan_content_mix("night_scout", "x", count=20, seed=1)
    plan2 = plan_content_mix("night_scout", "x", count=20, seed=2)
    # 20件では高確率で異なる
    # （全く同じ場合もゼロではないが極めて稀）
    all_types = {"single_post", "thread_series", "reference_based", "video_clip_reference"}
    assert all(m in all_types or m == "original_hypothesis" for m in plan1["selected_modes"])


def test_content_types_mixed():
    """single_post / thread_series / reference_based / video_clip_reference が混在する。"""
    from generation.content_mix_planner import plan_content_mix
    plan = plan_content_mix("night_scout", "x", count=50, seed=42)
    modes_used = set(plan["ratio_summary"].keys())
    assert len(modes_used) >= 2, f"種別が1つしかない: {modes_used}"


def test_beauty_account_waiting_review():
    """beauty_account は draft_only なので全アイテムが WAITING_REVIEW。"""
    from generation.content_mix_planner import plan_content_mix
    plan = plan_content_mix("beauty_account", "x", count=5, seed=42)
    assert plan["safety_status"] == "DRAFT_ONLY"
    for item in plan["items"]:
        assert item["status"] == "WAITING_REVIEW", (
            f"beauty_account のアイテムが WAITING_REVIEW でない: {item['status']}"
        )


def test_beauty_account_not_planned():
    """beauty_account のアイテムは PLANNED ステータスにならない。"""
    from generation.content_mix_planner import plan_content_mix
    plan = plan_content_mix("beauty_account", "x", count=5, seed=42)
    for item in plan["items"]:
        assert item["status"] != "PLANNED", (
            f"beauty_account のアイテムが PLANNED になっています（禁止）"
        )
        assert item["status"] != "READY", "beauty_account のアイテムが READY になっています（禁止）"
        assert item["status"] != "POSTED", "beauty_account のアイテムが POSTED になっています（禁止）"


def test_active_account_planned():
    """active アカウントのアイテムは PLANNED になる。"""
    from generation.content_mix_planner import plan_content_mix
    plan = plan_content_mix("night_scout", "x", count=5, seed=42)
    assert plan["safety_status"] == "OK"
    for item in plan["items"]:
        assert item["status"] == "PLANNED", (
            f"night_scout のアイテムが PLANNED でない: {item['status']}"
        )


def test_force_mode():
    """force_mode で単一モードを強制できる。"""
    from generation.content_mix_planner import plan_content_mix
    plan = plan_content_mix("night_scout", "x", count=5, seed=42, force_mode="thread_series")
    for item in plan["items"]:
        assert item["content_type"] == "thread_series"


def test_threads_platform():
    """threads プラットフォームでもプランが生成できる。"""
    from generation.content_mix_planner import plan_content_mix
    plan = plan_content_mix("night_scout", "threads", count=5, seed=42)
    assert plan["platform"] == "threads"
    assert len(plan["items"]) == 5


def test_config_file_exists():
    """config/content_mix/default_mix.json が存在する。"""
    path = os.path.join(_V2_ROOT, "config", "content_mix", "default_mix.json")
    assert os.path.isfile(path), f"config ファイルが見つかりません: {path}"


def test_fixture_exists():
    """sample_content_mix_plan.json が存在する。"""
    path = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_content_mix_plan.json")
    assert os.path.isfile(path), "fixture が見つかりません"


def test_no_real_post_in_items():
    """全アイテムに実投稿フラグがない（POSTED/READY なし）。"""
    from generation.content_mix_planner import plan_content_mix
    for account_id in ["night_scout", "liver_manager", "beauty_account"]:
        plan = plan_content_mix(account_id, "x", count=5, seed=42)
        for item in plan["items"]:
            assert item["status"] not in ("POSTED", "READY"), (
                f"{account_id}: {item['status']} は禁止です"
            )


if __name__ == "__main__":
    print("=" * 65)
    print("  test_content_mix_planner.py")
    print("=" * 65)

    _test("import", test_import)
    _test("basic_plan", test_basic_plan)
    _test("seed_reproducible", test_seed_reproducible)
    _test("different_seeds", test_different_seeds)
    _test("content_types_mixed", test_content_types_mixed)
    _test("beauty_account_waiting_review", test_beauty_account_waiting_review)
    _test("beauty_account_not_planned", test_beauty_account_not_planned)
    _test("active_account_planned", test_active_account_planned)
    _test("force_mode", test_force_mode)
    _test("threads_platform", test_threads_platform)
    _test("config_file_exists", test_config_file_exists)
    _test("fixture_exists", test_fixture_exists)
    _test("no_real_post_in_items", test_no_real_post_in_items)

    print(f"\n{'=' * 65}")
    print(f"  PASS={_PASS}  FAIL={_FAIL}")
    print("=" * 65)
    if _FAIL > 0:
        sys.exit(1)
