"""
test_end_to_end_publish_preflight.py - end_to_end_publish_preflight テスト（Phase 7.D）

実投稿なし / X APIなし / Threads APIなし / secret表示なし。
"""
from __future__ import annotations

import os
import sys

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))
sys.path.insert(0, os.path.join(_V2_ROOT, "scripts"))

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


def _reset_counters():
    """テスト前にグローバルカウンタをリセット。"""
    import preflight_end_to_end_publish as mod
    mod.RESULTS = []
    mod.PASS_COUNT = 0
    mod.FAIL_COUNT = 0
    mod.WARN_COUNT = 0
    mod.BLOCKED_COUNT = 0


def test_import():
    """preflight_end_to_end_publish がインポートできる。"""
    import preflight_end_to_end_publish
    assert hasattr(preflight_end_to_end_publish, "run_preflight")


def test_x_single_post_preflight():
    """X / single_post のプレフライトが実行できる。"""
    import preflight_end_to_end_publish as mod
    _reset_counters()
    result = mod.run_preflight(
        account_id="night_scout",
        platform="x",
        post_type="single_post",
        mock=True,
    )
    assert result["status"] in ("READY", "WARN", "NOT_READY")
    assert result["blocked"] == 0, f"night_scout が BLOCKED になった: {result}"


def test_x_thread_series_preflight():
    """X / thread_series のプレフライトが実行できる。"""
    import preflight_end_to_end_publish as mod
    _reset_counters()
    result = mod.run_preflight(
        account_id="night_scout",
        platform="x",
        post_type="thread_series",
        series_id="ts_night_scout_x_abc123",
        mock=True,
    )
    assert result["status"] in ("READY", "WARN", "NOT_READY")
    assert result["blocked"] == 0


def test_threads_single_post_preflight():
    """Threads / single_post のプレフライトが実行できる。"""
    import preflight_end_to_end_publish as mod
    _reset_counters()
    result = mod.run_preflight(
        account_id="night_scout",
        platform="threads",
        post_type="single_post",
        mock=True,
    )
    assert result["status"] in ("READY", "WARN", "NOT_READY")
    assert result["blocked"] == 0


def test_threads_thread_series_preflight():
    """Threads / thread_series のプレフライトが実行できる。"""
    import preflight_end_to_end_publish as mod
    _reset_counters()
    result = mod.run_preflight(
        account_id="night_scout",
        platform="threads",
        post_type="thread_series",
        series_id="ts_night_scout_threads_abc456",
        mock=True,
    )
    assert result["status"] in ("READY", "WARN", "NOT_READY")


def test_draft_only_blocked():
    """draft_only アカウントは BLOCKED になる。"""
    import preflight_end_to_end_publish as mod
    _reset_counters()
    result = mod.run_preflight(
        account_id="beauty_account",
        platform="x",
        post_type="single_post",
        mock=True,
    )
    assert result["status"] == "BLOCKED", (
        f"beauty_account が BLOCKED でない: {result['status']}"
    )


def test_beauty_account_blocked_all_types():
    """beauty_account は全 post_type で BLOCKED になる。"""
    import preflight_end_to_end_publish as mod
    for post_type in ["single_post", "thread_series", "media_post", "video_clip_post"]:
        _reset_counters()
        result = mod.run_preflight(
            account_id="beauty_account",
            platform="x",
            post_type=post_type,
            mock=True,
        )
        assert result["status"] == "BLOCKED", (
            f"beauty_account / {post_type} が BLOCKED でない: {result['status']}"
        )


def test_publish_flag_false_pass():
    """PUBLISH_ENABLED=false / ALLOW_REAL_X_POST=false の場合は安全フラグが PASS。"""
    original_publish = os.environ.get("PUBLISH_ENABLED", "false")
    original_x = os.environ.get("ALLOW_REAL_X_POST", "false")
    os.environ["PUBLISH_ENABLED"] = "false"
    os.environ["ALLOW_REAL_X_POST"] = "false"

    import preflight_end_to_end_publish as mod
    _reset_counters()
    mod.check_publish_flags("x")

    flag_results = [(lv, label, msg) for lv, label, msg in mod.RESULTS
                    if label in ("PUBLISH_ENABLED", "ALLOW_REAL_X_POST")]
    for lv, label, _ in flag_results:
        assert lv == "PASS", f"{label} が PASS でない: {lv}"

    os.environ["PUBLISH_ENABLED"] = original_publish
    os.environ["ALLOW_REAL_X_POST"] = original_x


def test_no_secret_in_output():
    """secret が出力されないことを確認（インポートのみ）。"""
    import preflight_end_to_end_publish as mod
    _reset_counters()
    # check_account_status は secret を出力しない
    mod.check_account_status("night_scout")
    for _, label, msg in mod.RESULTS:
        assert "api_key" not in msg.lower(), f"secret が表示されています: {msg}"
        assert "token" not in msg.lower() or "設定" in msg, f"token 値が表示されています: {msg}"


def test_fixture_exists():
    """sample_end_to_end_preflight.json が存在する。"""
    path = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_end_to_end_preflight.json")
    assert os.path.isfile(path), "fixture が見つかりません"


if __name__ == "__main__":
    print("=" * 65)
    print("  test_end_to_end_publish_preflight.py")
    print("=" * 65)

    _test("import", test_import)
    _test("x_single_post_preflight", test_x_single_post_preflight)
    _test("x_thread_series_preflight", test_x_thread_series_preflight)
    _test("threads_single_post_preflight", test_threads_single_post_preflight)
    _test("threads_thread_series_preflight", test_threads_thread_series_preflight)
    _test("draft_only_blocked", test_draft_only_blocked)
    _test("beauty_account_blocked_all_types", test_beauty_account_blocked_all_types)
    _test("publish_flag_false_pass", test_publish_flag_false_pass)
    _test("no_secret_in_output", test_no_secret_in_output)
    _test("fixture_exists", test_fixture_exists)

    print(f"\n{'=' * 65}")
    print(f"  PASS={_PASS}  FAIL={_FAIL}")
    print("=" * 65)
    if _FAIL > 0:
        sys.exit(1)
