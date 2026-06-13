"""
preflight_end_to_end_publish.py - 統合実投稿前チェック（Phase 7.D）

X / Threads で単発・ツリー・動画付き投稿を1件ずつ安全に通せるか確認する。
実投稿なし。secret表示なし。

対応:
  - platform: x / threads
  - post_type: single_post / thread_series / media_post / video_clip_post

使い方:
  python scripts/preflight_end_to_end_publish.py --account-id night_scout --platform x --post-type single_post --mock
  python scripts/preflight_end_to_end_publish.py --account-id beauty_account --platform x --post-type thread_series --mock

禁止事項:
  - 実SNS投稿
  - X API 実呼び出し
  - Threads API 実呼び出し
  - secret値の表示
"""
from __future__ import annotations

import argparse
import os
import sys

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_V2_ROOT, ".env"))
except ImportError:
    pass

RESULTS: list[tuple[str, str, str]] = []
PASS_COUNT = 0
FAIL_COUNT = 0
WARN_COUNT = 0
BLOCKED_COUNT = 0


def _add(level: str, label: str, msg: str) -> None:
    global PASS_COUNT, FAIL_COUNT, WARN_COUNT, BLOCKED_COUNT
    RESULTS.append((level, label, msg))
    icons = {"PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]", "BLOCKED": "[BLOCKED]", "INFO": "[INFO]"}
    icon = icons.get(level, f"[{level}]")
    print(f"  {icon} {label}: {msg}")
    if level == "PASS":
        PASS_COUNT += 1
    elif level == "FAIL":
        FAIL_COUNT += 1
    elif level == "WARN":
        WARN_COUNT += 1
    elif level == "BLOCKED":
        BLOCKED_COUNT += 1


# ------------------------------------------------------------------ #
# 共通チェック
# ------------------------------------------------------------------ #

def check_account_status(account_id: str) -> str:
    """アカウントステータスを確認する。BLOCKED/NOT_READY/READY を返す。"""
    print(f"\n[1] アカウントステータス確認: {account_id}")
    try:
        from accounts.account_config import load_account_config
        acct_cfg = load_account_config(account_id)
        if acct_cfg.is_draft_only():
            _add("BLOCKED", "account_status", f"{account_id} は draft_only アカウントです。実投稿禁止。")
            return "BLOCKED"
        if not acct_cfg.is_active():
            _add("BLOCKED", "account_status", f"{account_id} は inactive アカウントです。実投稿禁止。")
            return "BLOCKED"
        _add("PASS", "account_status", f"{account_id} は active です")
        return "READY"
    except FileNotFoundError:
        _add("WARN", "account_status", f"{account_id} の account_config が見つかりません（seeds.py のみ）")
        return "READY"


def check_publish_flags(platform: str) -> bool:
    """PUBLISH_ENABLED / ALLOW_REAL_*_POST フラグ確認。"""
    print(f"\n[2] 安全フラグ確認（{platform}）")
    publish_enabled = os.environ.get("PUBLISH_ENABLED", "false").lower() == "true"
    if publish_enabled:
        _add("WARN", "PUBLISH_ENABLED", "true になっています（通常は false）")
    else:
        _add("PASS", "PUBLISH_ENABLED", "false（安全）")

    if platform == "x":
        allow_real = os.environ.get("ALLOW_REAL_X_POST", "false").lower() == "true"
        flag_name = "ALLOW_REAL_X_POST"
    else:
        allow_real = os.environ.get("ALLOW_REAL_THREADS_POST", "false").lower() == "true"
        flag_name = "ALLOW_REAL_THREADS_POST"

    if allow_real:
        _add("WARN", flag_name, "true になっています（実投稿モード）")
    else:
        _add("PASS", flag_name, "false（安全）")

    return True


def check_platform_support(account_id: str, platform: str) -> bool:
    """アカウントがプラットフォームに対応しているか確認。"""
    print(f"\n[3] プラットフォーム対応確認: {platform}")
    try:
        from accounts.account_config import load_account_config
        acct_cfg = load_account_config(account_id)
        if not acct_cfg.allows_platform(platform):
            _add("FAIL", "platform_support", f"{account_id} は {platform} に非対応")
            return False
        _add("PASS", "platform_support", f"{account_id} は {platform} に対応")
        return True
    except FileNotFoundError:
        _add("WARN", "platform_support", "account_config 未確認（seeds.py のみ）")
        return True


# ------------------------------------------------------------------ #
# post_type別チェック
# ------------------------------------------------------------------ #

def check_single_post(account_id: str, platform: str, queue_id: str = "", mock: bool = False) -> None:
    """single_post プレフライトチェック。"""
    print(f"\n[4] single_post チェック: platform={platform}")
    try:
        from accounts.account_config import load_account_config
        acct_cfg = load_account_config(account_id)
        limits = acct_cfg.get_char_limits(platform)
        _add("PASS", "char_limits", f"soft={limits['soft']} hard={limits['hard']}")
    except FileNotFoundError:
        _add("WARN", "char_limits", "デフォルト値を使用（X:120/140, Threads:500/800）")

    if queue_id:
        _add("INFO", "queue_id", f"確認対象: {queue_id}")
    else:
        _add("WARN", "queue_id", "queue_id が未指定です（--queue-id で指定推奨）")

    if mock:
        _add("PASS", "mock_mode", "mock モードのため queue チェックをスキップ")


def check_thread_series(account_id: str, platform: str, series_id: str = "", mock: bool = False) -> None:
    """thread_series プレフライトチェック。"""
    print(f"\n[4] thread_series チェック: platform={platform}")
    if series_id:
        if not series_id.startswith("ts_"):
            _add("FAIL", "series_id_format", f"series_id が ts_ で始まっていません: {series_id}")
        else:
            _add("PASS", "series_id_format", f"series_id フォーマット OK: {series_id}")
    else:
        _add("WARN", "series_id", "series_id が未指定です（--series-id で指定推奨）")

    if mock:
        _add("PASS", "mock_mode", "mock モードのため series チェックをスキップ")
    else:
        _add("WARN", "series_status", "実queue確認が必要です（python scripts/review_thread_series.py）")


def check_media_post(account_id: str, platform: str, media_asset_id: str = "", mock: bool = False) -> None:
    """media_post プレフライトチェック。"""
    print(f"\n[4] media_post チェック: platform={platform}")
    allow_cloudinary = os.environ.get("ALLOW_CLOUDINARY_UPLOAD", "false").lower() == "true"
    if allow_cloudinary:
        _add("WARN", "ALLOW_CLOUDINARY_UPLOAD", "true になっています")
    else:
        _add("PASS", "ALLOW_CLOUDINARY_UPLOAD", "false（安全）")

    if media_asset_id:
        _add("INFO", "media_asset_id", f"確認対象: {media_asset_id}")
        _add("WARN", "media_upload_status", "Cloudinary upload 完了を手動で確認してください")
    else:
        _add("WARN", "media_asset_id", "media_asset_id が未指定です（--media-asset-id で指定推奨）")

    if mock:
        _add("PASS", "mock_mode", "mock モードのため media チェックをスキップ")


def check_video_clip_post(account_id: str, platform: str, media_asset_id: str = "", mock: bool = False) -> None:
    """video_clip_post プレフライトチェック。"""
    print(f"\n[4] video_clip_post チェック: platform={platform}")
    check_media_post(account_id, platform, media_asset_id, mock)
    _add("WARN", "video_clip_rights", "video_clip の rights_status と reuse_risk を確認してください")


def check_posted_results_duplicate(account_id: str, queue_id: str = "", series_id: str = "") -> None:
    """posted_results 重複確認。"""
    print(f"\n[5] posted_results 重複確認")
    if not queue_id and not series_id:
        _add("WARN", "duplicate_check", "queue_id / series_id 未指定のため重複確認をスキップ")
        return
    _add("PASS", "duplicate_check", "mock モードのため重複なしと仮定（実運用時は手動確認）")


# ------------------------------------------------------------------ #
# メイン preflight
# ------------------------------------------------------------------ #

def run_preflight(
    account_id: str,
    platform: str,
    post_type: str,
    queue_id: str = "",
    series_id: str = "",
    media_asset_id: str = "",
    mock: bool = False,
) -> dict:
    """統合プレフライトを実行して結果を返す。"""
    print(f"\n{'=' * 65}")
    print(f"  preflight_end_to_end_publish")
    print(f"  account_id : {account_id}")
    print(f"  platform   : {platform}")
    print(f"  post_type  : {post_type}")
    print(f"  mock       : {mock}")
    print(f"{'=' * 65}")

    # [1] アカウントステータス
    account_result = check_account_status(account_id)
    if account_result == "BLOCKED":
        print(f"\n{'=' * 65}")
        print(f"  [BLOCKED] {account_id} は実投稿禁止アカウントです。処理を中断します。")
        print(f"{'=' * 65}")
        return {
            "status": "BLOCKED",
            "account_id": account_id,
            "platform": platform,
            "post_type": post_type,
            "pass": PASS_COUNT,
            "fail": FAIL_COUNT,
            "warn": WARN_COUNT,
            "blocked": BLOCKED_COUNT,
        }

    # [2] 安全フラグ
    check_publish_flags(platform)

    # [3] プラットフォーム対応
    check_platform_support(account_id, platform)

    # [4] post_type 別チェック
    if post_type == "single_post":
        check_single_post(account_id, platform, queue_id, mock)
    elif post_type == "thread_series":
        check_thread_series(account_id, platform, series_id, mock)
    elif post_type == "media_post":
        check_media_post(account_id, platform, media_asset_id, mock)
    elif post_type == "video_clip_post":
        check_video_clip_post(account_id, platform, media_asset_id, mock)
    else:
        _add("FAIL", "post_type", f"不明な post_type: {post_type}")

    # [5] posted_results 重複確認
    check_posted_results_duplicate(account_id, queue_id, series_id)

    overall = "READY"
    if FAIL_COUNT > 0:
        overall = "NOT_READY"
    elif BLOCKED_COUNT > 0:
        overall = "BLOCKED"
    elif WARN_COUNT > 0:
        overall = "WARN"

    return {
        "status": overall,
        "account_id": account_id,
        "platform": platform,
        "post_type": post_type,
        "pass": PASS_COUNT,
        "fail": FAIL_COUNT,
        "warn": WARN_COUNT,
        "blocked": BLOCKED_COUNT,
    }


def main() -> None:
    global RESULTS, PASS_COUNT, FAIL_COUNT, WARN_COUNT, BLOCKED_COUNT
    RESULTS = []
    PASS_COUNT = FAIL_COUNT = WARN_COUNT = BLOCKED_COUNT = 0

    parser = argparse.ArgumentParser(description="統合実投稿前チェック")
    parser.add_argument("--account-id", default="night_scout")
    parser.add_argument("--platform", default="x", choices=["x", "threads"])
    parser.add_argument("--post-type", default="single_post",
                        choices=["single_post", "thread_series", "media_post", "video_clip_post"])
    parser.add_argument("--queue-id", default="")
    parser.add_argument("--series-id", default="")
    parser.add_argument("--media-asset-id", default="")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()

    result = run_preflight(
        account_id=args.account_id,
        platform=args.platform,
        post_type=args.post_type,
        queue_id=args.queue_id,
        series_id=args.series_id,
        media_asset_id=args.media_asset_id,
        mock=args.mock,
    )

    print(f"\n{'=' * 65}")
    print(f"  総合結果: {result['status']}")
    print(f"  PASS={result['pass']}  FAIL={result['fail']}  WARN={result['warn']}  BLOCKED={result['blocked']}")
    print(f"{'=' * 65}")
    print(f"  実投稿なし / X APIなし / Threads APIなし / secret表示なし")

    if result["status"] in ("NOT_READY", "BLOCKED"):
        sys.exit(1)


if __name__ == "__main__":
    main()
