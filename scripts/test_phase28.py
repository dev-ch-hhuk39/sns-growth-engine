"""
test_phase28.py — Phase 2.8 動作確認テスト

テスト項目:
  1. TAB_DEFINITIONS に Phase 2.8 追加タブが存在する
  2. 追加タブの必須カラムが含まれる
  3. text_policy.py の文字数ポリシー判定
  4. generation_planner.py の build_generation_job
  5. スタブ import の確認（collectors / analyzers / media）
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sheets_client import TAB_DEFINITIONS
from text_policy import check_text_policy, get_platform_limits
from generation.generation_planner import build_generation_job, plan_daily_counts
from collectors import x_reference_collector as xrc
from analyzers import reference_post_analyzer as rpa
from media import cloudinary_client as cc

_PASS = 0
_FAIL = 0


def ok(name: str) -> None:
    global _PASS
    _PASS += 1
    print(f"  [PASS] {name}")


def fail(name: str, reason: str) -> None:
    global _FAIL
    _FAIL += 1
    print(f"  [FAIL] {name}: {reason}")


# ------------------------------------------------------------------ #
# 1. TAB_DEFINITIONS に Phase 2.8 追加タブが存在する
# ------------------------------------------------------------------ #

def test_tab_definitions_phase28() -> None:
    print("\n[Test 1] TAB_DEFINITIONS Phase 2.8 タブ存在確認")

    new_tabs = ["media_assets", "reference_post_scores", "generation_jobs"]
    for tab in new_tabs:
        if tab in TAB_DEFINITIONS:
            ok(f"TAB_DEFINITIONS['{tab}'] 存在")
        else:
            fail(f"TAB_DEFINITIONS['{tab}'] 存在", "タブが定義されていません")


# ------------------------------------------------------------------ #
# 2. 追加タブの必須カラム確認
# ------------------------------------------------------------------ #

def test_tab_required_columns() -> None:
    print("\n[Test 2] 必須カラム確認")

    checks = {
        "media_assets": [
            "media_id", "account_id", "reference_post_id",
            "storage_url", "media_type", "reuse_status", "imitation_risk",
        ],
        "reference_post_scores": [
            "score_id", "reference_post_id", "account_id",
            "performance_score", "buzz_score",
            "hook_style", "content_angle", "analyzed_at",
        ],
        "generation_jobs": [
            "job_id", "account_id", "platform",
            "generation_mode", "reference_based_ratio", "original_hypothesis_ratio",
            "daily_target_count", "active",
        ],
    }

    for tab, required_cols in checks.items():
        cols = TAB_DEFINITIONS.get(tab, [])
        for col in required_cols:
            if col in cols:
                ok(f"'{tab}' に '{col}' カラム")
            else:
                fail(f"'{tab}' に '{col}' カラム", f"定義なし。実際: {cols}")


# ------------------------------------------------------------------ #
# 3. text_policy 文字数ポリシー判定
# ------------------------------------------------------------------ #

def test_text_policy() -> None:
    print("\n[Test 3] text_policy 文字数ポリシー")

    # X: 120字以内 → OK
    short_x = "あ" * 100
    r = check_text_policy(short_x, "x")
    if r.status == "OK":
        ok("X: 100字 → OK")
    else:
        fail("X: 100字 → OK", f"status={r.status}")

    # X: 121〜140字 → WARN
    warn_x = "あ" * 130
    r = check_text_policy(warn_x, "x")
    if r.status == "WARN":
        ok("X: 130字 → WARN")
    else:
        fail("X: 130字 → WARN", f"status={r.status}")

    # X: 141字以上 → FAIL
    fail_x = "あ" * 141
    r = check_text_policy(fail_x, "x")
    if r.status == "FAIL":
        ok("X: 141字 → FAIL")
    else:
        fail("X: 141字 → FAIL", f"status={r.status}")

    # Threads: 600字以内 → OK
    short_th = "あ" * 500
    r = check_text_policy(short_th, "threads")
    if r.status == "OK":
        ok("Threads: 500字 → OK")
    else:
        fail("Threads: 500字 → OK", f"status={r.status}")

    # Threads: 601〜800字 → WARN
    warn_th = "あ" * 700
    r = check_text_policy(warn_th, "threads")
    if r.status == "WARN":
        ok("Threads: 700字 → WARN")
    else:
        fail("Threads: 700字 → WARN", f"status={r.status}")

    # Threads: 801字以上 → FAIL
    fail_th = "あ" * 801
    r = check_text_policy(fail_th, "threads")
    if r.status == "FAIL":
        ok("Threads: 801字 → FAIL")
    else:
        fail("Threads: 801字 → FAIL", f"status={r.status}")

    # 未知プラットフォーム → ValueError
    try:
        check_text_policy("test", "note")
        fail("未知プラットフォーム → ValueError", "例外が発生しませんでした")
    except ValueError:
        ok("未知プラットフォーム → ValueError")

    # get_platform_limits
    limits = get_platform_limits("x")
    if limits["soft_limit"] == 120 and limits["hard_limit"] == 140:
        ok("get_platform_limits(x) 値確認")
    else:
        fail("get_platform_limits(x) 値確認", str(limits))


# ------------------------------------------------------------------ #
# 4. generation_planner build_generation_job
# ------------------------------------------------------------------ #

def test_generation_planner() -> None:
    print("\n[Test 4] generation_planner")

    job = build_generation_job(
        account_id="night_scout",
        platform="x",
        daily_target_count=3,
    )

    required_keys = [
        "job_id", "account_id", "platform",
        "generation_mode", "reference_based_ratio", "original_hypothesis_ratio",
        "daily_target_count", "active",
    ]
    for key in required_keys:
        if key in job:
            ok(f"build_generation_job: '{key}' キー存在")
        else:
            fail(f"build_generation_job: '{key}' キー存在", f"実際: {list(job.keys())}")

    if job["account_id"] == "night_scout":
        ok("build_generation_job: account_id 値確認")
    else:
        fail("build_generation_job: account_id 値確認", str(job["account_id"]))

    if job["reference_based_ratio"] == 0.8:
        ok("build_generation_job: 8:2 比率デフォルト (0.8)")
    else:
        fail("build_generation_job: 8:2 比率デフォルト", str(job["reference_based_ratio"]))

    # plan_daily_counts
    ref, orig = plan_daily_counts(daily_target=10, ratio=0.8)
    if ref == 8 and orig == 2:
        ok("plan_daily_counts: 10件×0.8 → (8, 2)")
    else:
        fail("plan_daily_counts: 10件×0.8", f"({ref}, {orig})")

    ref3, orig3 = plan_daily_counts(daily_target=3, ratio=0.8)
    if ref3 + orig3 == 3:
        ok("plan_daily_counts: 合計が daily_target と一致")
    else:
        fail("plan_daily_counts: 合計確認", f"({ref3}, {orig3})")


# ------------------------------------------------------------------ #
# 5. スタブ import 確認（NotImplementedError が出ること）
# ------------------------------------------------------------------ #

def test_stub_imports() -> None:
    print("\n[Test 5] スタブ import 確認")

    # x_reference_collector（Phase 2.10 スタブ）
    try:
        xrc.fetch_account_posts("user", "token")
        fail("xrc.fetch_account_posts → NotImplementedError", "例外なし")
    except NotImplementedError:
        ok("x_reference_collector: fetch_account_posts → NotImplementedError")

    try:
        xrc.fetch_keyword_posts("kw", "token")
        fail("xrc.fetch_keyword_posts → NotImplementedError", "例外なし")
    except NotImplementedError:
        ok("x_reference_collector: fetch_keyword_posts → NotImplementedError")

    # reference_post_analyzer (Phase 2.11 で本実装済み → NotImplementedError は出ない)
    try:
        result = rpa.calculate_performance_score({"likes": 100, "reposts": 10, "reply_count": 5, "bookmark_count": 2, "impressions": 1000})
        ok(f"reference_post_analyzer: calculate_performance_score → {result:.1f}")
    except Exception as e:
        fail("reference_post_analyzer: calculate_performance_score", str(e))

    try:
        angle = rpa.detect_content_angle("テスト")
        ok(f"reference_post_analyzer: detect_content_angle → {angle!r}")
    except Exception as e:
        fail("reference_post_analyzer: detect_content_angle", str(e))

    # cloudinary_client
    try:
        cc.download_media("https://example.com/image.jpg")
        fail("cc.download_media → NotImplementedError", "例外なし")
    except NotImplementedError:
        ok("cloudinary_client: download_media → NotImplementedError")


# ------------------------------------------------------------------ #
# エントリーポイント
# ------------------------------------------------------------------ #

def main() -> None:
    print("=" * 60)
    print("Phase 2.8 テスト開始")
    print("=" * 60)

    test_tab_definitions_phase28()
    test_tab_required_columns()
    test_text_policy()
    test_generation_planner()
    test_stub_imports()

    print("\n" + "=" * 60)
    print(f"結果: {_PASS} PASS / {_FAIL} FAIL")
    print("=" * 60)

    if _FAIL > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
