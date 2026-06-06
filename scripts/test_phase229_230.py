"""
test_phase229_230.py - Phase 2.29-2.30 テストスイート

Phase 2.29: TikTok dry-run planning support
Phase 2.30: preflight_video_real_test.py 構造確認

実行方法: python scripts/test_phase229_230.py
"""
from __future__ import annotations

import json
import os
import sys

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

from video.video_downloader import (
    DownloadResult,
    _extract_tiktok_video_id,
    _extract_video_id,
    download_video,
    download_videos_batch,
)

# ============================================================
# テストフレームワーク
# ============================================================

_PASS = 0
_FAIL = 0
_tests: list[tuple[str, bool, str]] = []


def _test(name: str, fn) -> None:
    global _PASS, _FAIL
    try:
        fn()
        _PASS += 1
        _tests.append((name, True, ""))
    except Exception as e:
        _FAIL += 1
        _tests.append((name, False, str(e)))


def _make_reference_post(
    platform: str = "youtube",
    video_url: str = "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    account_id: str = "night_scout",
) -> dict:
    return {
        "id": f"ref-{platform}-001",
        "account_id": account_id,
        "platform": platform,
        "video_url": video_url,
    }


# ============================================================
# Phase 2.29: _extract_tiktok_video_id
# ============================================================

print("\n=== Phase 2.29: _extract_tiktok_video_id ===")


def t_extract_tiktok_long_url():
    url = "https://www.tiktok.com/@nightscout_official/video/7123456789012345678"
    vid = _extract_tiktok_video_id(url)
    assert vid == "tt_7123456789012345678", f"expected 'tt_7123456789012345678', got {vid!r}"


def t_extract_tiktok_vm_url():
    url = "https://vm.tiktok.com/ZMeXYZABC/"
    vid = _extract_tiktok_video_id(url)
    assert vid == "tt_ZMeXYZABC", f"expected 'tt_ZMeXYZABC', got {vid!r}"


def t_extract_tiktok_unknown_url():
    url = "https://tiktok.com/tag/夜職"
    vid = _extract_tiktok_video_id(url)
    assert vid == "", f"expected '', got {vid!r}"


def t_extract_tiktok_youtube_url_returns_empty():
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    vid = _extract_tiktok_video_id(url)
    assert vid == "", f"YouTube URL は空を返すべき: {vid!r}"


_test("_extract_tiktok_video_id: long URL", t_extract_tiktok_long_url)
_test("_extract_tiktok_video_id: vm.tiktok URL", t_extract_tiktok_vm_url)
_test("_extract_tiktok_video_id: unknown URL → ''", t_extract_tiktok_unknown_url)
_test("_extract_tiktok_video_id: YouTube URL → ''", t_extract_tiktok_youtube_url_returns_empty)


# ============================================================
# Phase 2.29: TikTok dry-run planning
# ============================================================

print("\n=== Phase 2.29: TikTok dry-run planning ===")


def t_tiktok_dry_run_returns_success():
    post = _make_reference_post(
        platform="tiktok",
        video_url="https://www.tiktok.com/@user/video/7123456789012345678",
    )
    result = download_video(post, dry_run=True)
    assert result.success is True, f"dry-run TikTok は success=True を期待: {result}"


def t_tiktok_dry_run_has_local_path():
    post = _make_reference_post(
        platform="tiktok",
        video_url="https://www.tiktok.com/@user/video/7123456789012345678",
    )
    result = download_video(post, dry_run=True)
    assert result.local_path != "", f"dry-run TikTok は local_path を返すべき: {result}"


def t_tiktok_dry_run_has_tiktok_in_error():
    post = _make_reference_post(
        platform="tiktok",
        video_url="https://www.tiktok.com/@user/video/7123456789012345678",
    )
    result = download_video(post, dry_run=True)
    assert "TikTok" in result.error, f"error に TikTok が含まれるべき: {result.error!r}"


def t_tiktok_dry_run_video_id_has_tt_prefix():
    post = _make_reference_post(
        platform="tiktok",
        video_url="https://www.tiktok.com/@user/video/7123456789012345678",
    )
    result = download_video(post, dry_run=True)
    assert result.video_id.startswith("tt_"), f"video_id が tt_ で始まるべき: {result.video_id!r}"


def t_tiktok_confirm_download_false_returns_planning():
    # confirm_download=False は dry 扱い → TikTok も planning 成功
    post = _make_reference_post(
        platform="tiktok",
        video_url="https://www.tiktok.com/@user/video/7123456789012345678",
    )
    result = download_video(post, dry_run=False, confirm_download=False)
    assert result.success is True, f"confirm_download=False TikTok は planning: {result}"


def t_tiktok_real_download_fails():
    post = _make_reference_post(
        platform="tiktok",
        video_url="https://www.tiktok.com/@user/video/7123456789012345678",
    )
    result = download_video(post, dry_run=False, confirm_download=True)
    assert result.success is False, f"実ダウンロード TikTok は失敗を期待: {result}"
    assert "未対応" in result.error, f"error に '未対応' が含まれるべき: {result.error!r}"


def t_tiktok_dry_run_path_includes_account_id():
    post = _make_reference_post(
        platform="tiktok",
        video_url="https://www.tiktok.com/@user/video/7123456789012345678",
        account_id="night_scout",
    )
    result = download_video(post, dry_run=True)
    assert "night_scout" in result.local_path, f"パスに account_id を含むべき: {result.local_path!r}"


def t_tiktok_batch_dry_run_all_planning_success():
    posts = [
        _make_reference_post(platform="tiktok", video_url="https://www.tiktok.com/@u/video/1111"),
        _make_reference_post(platform="tiktok", video_url="https://www.tiktok.com/@u/video/2222"),
    ]
    results = download_videos_batch(posts, dry_run=True)
    assert len(results) == 2
    assert all(r.success for r in results), f"全件 planning 成功を期待: {results}"


def t_tiktok_vm_url_dry_run_success():
    post = _make_reference_post(
        platform="tiktok",
        video_url="https://vm.tiktok.com/ZMeABC123/",
    )
    result = download_video(post, dry_run=True)
    assert result.success is True
    assert "tt_ZMeABC123" in result.video_id


def t_tiktok_unknown_url_falls_back_to_ref_id():
    post = _make_reference_post(
        platform="tiktok",
        video_url="https://tiktok.com/tag/夜職",
    )
    result = download_video(post, dry_run=True)
    assert result.success is True, f"TikTok dry-run は URL不明でも success: {result}"
    assert result.local_path != ""


_test("TikTok dry_run=True → success=True", t_tiktok_dry_run_returns_success)
_test("TikTok dry_run → local_path あり", t_tiktok_dry_run_has_local_path)
_test("TikTok dry_run → error に 'TikTok' 含む", t_tiktok_dry_run_has_tiktok_in_error)
_test("TikTok dry_run → video_id が tt_ 始まり", t_tiktok_dry_run_video_id_has_tt_prefix)
_test("TikTok confirm=False → planning 成功", t_tiktok_confirm_download_false_returns_planning)
_test("TikTok 実ダウンロード → 失敗", t_tiktok_real_download_fails)
_test("TikTok dry_run → path に account_id 含む", t_tiktok_dry_run_path_includes_account_id)
_test("TikTok batch dry_run → 全件 planning 成功", t_tiktok_batch_dry_run_all_planning_success)
_test("TikTok vm.tiktok URL dry_run 成功", t_tiktok_vm_url_dry_run_success)
_test("TikTok URL不明 → ref_id フォールバック", t_tiktok_unknown_url_falls_back_to_ref_id)


# ============================================================
# Phase 2.29: YouTube との共存確認
# ============================================================

print("\n=== Phase 2.29: YouTube との共存確認 ===")


def t_youtube_dry_run_still_works():
    post = _make_reference_post(
        platform="youtube",
        video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    )
    result = download_video(post, dry_run=True)
    assert result.success is True
    assert result.video_id == "dQw4w9WgXcQ"


def t_mixed_batch_youtube_and_tiktok():
    posts = [
        _make_reference_post(platform="youtube", video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
        _make_reference_post(platform="tiktok", video_url="https://www.tiktok.com/@u/video/7111"),
        _make_reference_post(platform="youtube", video_url="https://youtu.be/abc12345678"),
    ]
    results = download_videos_batch(posts, dry_run=True)
    assert len(results) == 3
    assert all(r.success for r in results), f"YouTube + TikTok 全件 planning 成功: {results}"


_test("YouTube dry_run 依然として動作", t_youtube_dry_run_still_works)
_test("YouTube + TikTok 混在 batch dry_run 全件成功", t_mixed_batch_youtube_and_tiktok)


# ============================================================
# Phase 2.30: preflight_video_real_test.py 構造確認
# ============================================================

print("\n=== Phase 2.30: preflight スクリプト存在確認 ===")


def t_preflight_script_exists():
    path = os.path.join(_V2_ROOT, "scripts", "preflight_video_real_test.py")
    assert os.path.isfile(path), f"preflight スクリプトが見つかりません: {path}"


def t_preflight_script_importable():
    import importlib.util
    path = os.path.join(_V2_ROOT, "scripts", "preflight_video_real_test.py")
    spec = importlib.util.spec_from_file_location("preflight_video_real_test", path)
    mod = importlib.util.module_from_spec(spec)
    # main 実行はしない（引数なしで sys.exit するため）
    assert spec is not None


def t_preflight_has_check_functions():
    import importlib.util
    path = os.path.join(_V2_ROOT, "scripts", "preflight_video_real_test.py")
    spec = importlib.util.spec_from_file_location("preflight_video_real_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "check_yt_dlp"), "check_yt_dlp 関数が必要"
    assert hasattr(mod, "check_ffmpeg"), "check_ffmpeg 関数が必要"
    assert hasattr(mod, "check_env_vars"), "check_env_vars 関数が必要"
    assert hasattr(mod, "check_downloads_dir"), "check_downloads_dir 関数が必要"


_test("preflight スクリプトが存在", t_preflight_script_exists)
_test("preflight スクリプトが import 可能", t_preflight_script_importable)
_test("preflight 関数が定義済み", t_preflight_has_check_functions)


# ============================================================
# Phase 2.29: fixture ファイル確認
# ============================================================

print("\n=== Phase 2.29: fixture ファイル確認 ===")


def t_fixture_tiktok_download_plan_exists():
    path = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_tiktok_download_plan.json")
    assert os.path.isfile(path), f"fixture が見つかりません: {path}"


def t_fixture_tiktok_download_plan_valid():
    path = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_tiktok_download_plan.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    assert data["dry_run"] is True
    assert data["platform"] == "tiktok"
    assert len(data["results"]) > 0
    for r in data["results"]:
        assert r["success"] is True, "fixture の TikTok planning は success=True"
        assert "TikTok" in r["error"]
        assert r["video_id"].startswith("tt_")


_test("fixture: sample_tiktok_download_plan.json 存在", t_fixture_tiktok_download_plan_exists)
_test("fixture: sample_tiktok_download_plan.json 内容正常", t_fixture_tiktok_download_plan_valid)


# ============================================================
# Phase 2.30: 環境変数ガード確認（値出力なし）
# ============================================================

print("\n=== Phase 2.30: 環境変数ガード確認 ===")


def t_allow_transcription_api_default_false():
    """ALLOW_TRANSCRIPTION_API がデフォルトで false であることを確認（値は出力しない）。"""
    val = os.environ.get("ALLOW_TRANSCRIPTION_API", "false").lower()
    assert val != "true", "ALLOW_TRANSCRIPTION_API=true は禁止（テスト環境）"


def t_publish_enabled_default_false():
    val = os.environ.get("PUBLISH_ENABLED", "false").lower()
    assert val != "true", "PUBLISH_ENABLED=true は禁止（テスト環境）"


def t_allow_real_x_post_default_false():
    val = os.environ.get("ALLOW_REAL_X_POST", "false").lower()
    assert val != "true", "ALLOW_REAL_X_POST=true は禁止（テスト環境）"


def t_allow_real_threads_post_default_false():
    val = os.environ.get("ALLOW_REAL_THREADS_POST", "false").lower()
    assert val != "true", "ALLOW_REAL_THREADS_POST=true は禁止（テスト環境）"


_test("ALLOW_TRANSCRIPTION_API != true（テスト環境ガード）", t_allow_transcription_api_default_false)
_test("PUBLISH_ENABLED != true（テスト環境ガード）", t_publish_enabled_default_false)
_test("ALLOW_REAL_X_POST != true（テスト環境ガード）", t_allow_real_x_post_default_false)
_test("ALLOW_REAL_THREADS_POST != true（テスト環境ガード）", t_allow_real_threads_post_default_false)


# ============================================================
# 結果表示
# ============================================================

print("\n" + "=" * 60)
print(f"  test_phase229_230.py 結果: PASS={_PASS} FAIL={_FAIL}")
print("=" * 60)

for name, ok, err in _tests:
    icon = "[PASS]" if ok else "[FAIL]"
    if ok:
        print(f"  {icon} {name}")
    else:
        print(f"  {icon} {name}")
        print(f"         → {err}")

if _FAIL > 0:
    sys.exit(1)
sys.exit(0)
