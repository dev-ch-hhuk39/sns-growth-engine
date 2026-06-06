"""
video_downloader.py - yt-dlp を使った動画ダウンロード基盤（Phase 2.26 / 2.29）

設計:
  - デフォルト: dry_run=True（yt-dlp は実行しない）
  - 実ダウンロードは --download --confirm-download フラグが両方必要
  - yt-dlp が import できない場合はエラーを返す（import 時にはチェックしない）
  - 出力先: downloads/videos/<account_id>/<video_id>.mp4（デフォルト）
  - Phase 2.26: YouTube のみ対応（TikTok は dry-run WARN → 失敗）
  - Phase 2.29: TikTok dry-run planning 対応
      dry_run=True  → TikTok も success=True で planning 結果を返す
      dry_run=False → TikTok は実ダウンロード未対応で失敗

禁止事項（コード実施保証）:
  - --download --confirm-download なしでの実ダウンロード禁止
  - TikTok/YouTube 本番大量取得禁止（1件ずつ限定）
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass
class DownloadResult:
    reference_post_id: str
    success: bool
    local_path: str = ""
    video_id: str = ""
    error: str = ""
    file_size_bytes: int = 0


def _extract_video_id(url: str) -> str:
    """YouTube URL から video_id を抽出する。"""
    import re
    patterns = [
        r"youtube\.com/watch\?v=([A-Za-z0-9_-]{11})",
        r"youtu\.be/([A-Za-z0-9_-]{11})",
        r"youtube\.com/shorts/([A-Za-z0-9_-]{11})",
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return ""


def _extract_tiktok_video_id(url: str) -> str:
    """TikTok URL から video_id を抽出する（dry-run planning 用）。"""
    import re
    m = re.search(r"tiktok\.com/@[^/]+/video/(\d+)", url)
    if m:
        return f"tt_{m.group(1)}"
    m = re.search(r"vm\.tiktok\.com/([A-Za-z0-9]+)", url)
    if m:
        return f"tt_{m.group(1)}"
    return ""


def _build_output_path(output_dir: str, account_id: str, video_id: str) -> str:
    account_dir = os.path.join(output_dir, account_id)
    os.makedirs(account_dir, exist_ok=True)
    fname = f"{video_id}.mp4" if video_id else "video.mp4"
    return os.path.join(account_dir, fname)


def download_video(
    reference_post: dict[str, Any],
    *,
    output_dir: str = "downloads/videos",
    dry_run: bool = True,
    confirm_download: bool = False,
) -> DownloadResult:
    """1件の reference_post の動画を yt-dlp でダウンロードする。

    Args:
        reference_post: reference_posts タブの1行 dict
        output_dir: 出力先ディレクトリ（デフォルト: downloads/videos/）
        dry_run: True の場合は yt-dlp を実行せず結果を返す
        confirm_download: True かつ dry_run=False の場合のみ実際にダウンロード

    Returns:
        DownloadResult
    """
    ref_id = str(reference_post.get("id", reference_post.get("reference_post_id", "unknown")))
    account_id = str(reference_post.get("account_id", "unknown"))
    video_url = str(reference_post.get("video_url", ""))
    platform = str(reference_post.get("platform", "")).lower()

    if not video_url:
        return DownloadResult(ref_id, success=False, error="video_url が空です")

    if platform == "tiktok":
        # Phase 2.29: dry-run mode は planning として success=True を返す
        tiktok_id = _extract_tiktok_video_id(video_url)
        if dry_run or not confirm_download:
            output_path = _build_output_path(output_dir, account_id, tiktok_id or ref_id)
            print(
                f"[video-downloader] [plan] TikTok ref_id={ref_id!r} "
                f"url={video_url[:60]!r} → {output_path} (手動DL要)"
            )
            return DownloadResult(
                ref_id,
                success=True,
                local_path=output_path,
                video_id=tiktok_id,
                error="TikTok: dry-run planning (手動ダウンロードが必要)",
            )
        print(f"[video-downloader] [ERROR] TikTok 実ダウンロードは未対応: {ref_id!r}")
        return DownloadResult(ref_id, success=False, error="TikTok 実ダウンロードは未対応です")

    video_id = _extract_video_id(video_url)
    output_path = _build_output_path(output_dir, account_id, video_id or ref_id)

    if dry_run or not confirm_download:
        mode = "dry-run" if dry_run else "confirm-download未指定"
        print(
            f"[video-downloader] [{mode}] ref_id={ref_id!r} "
            f"url={video_url[:60]!r} → {output_path}"
        )
        return DownloadResult(
            ref_id,
            success=True,
            local_path=output_path,
            video_id=video_id,
        )

    # 実ダウンロード（--download --confirm-download が両方指定された場合のみ）
    try:
        import yt_dlp  # type: ignore[import]
    except ImportError:
        msg = "yt-dlp が見つかりません。pip install yt-dlp でインストールしてください。"
        print(f"[video-downloader] [ERROR] {msg}")
        return DownloadResult(ref_id, success=False, error=msg)

    ydl_opts = {
        "outtmpl": output_path.replace(".mp4", ".%(ext)s"),
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": False,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
        if os.path.isfile(output_path):
            size = os.path.getsize(output_path)
            print(f"[video-downloader] 完了: {output_path} ({size:,} bytes)")
            return DownloadResult(
                ref_id,
                success=True,
                local_path=output_path,
                video_id=video_id,
                file_size_bytes=size,
            )
        return DownloadResult(ref_id, success=False, error="ダウンロード後にファイルが見つかりません")
    except Exception as e:
        msg = f"yt-dlp エラー: {e}"
        print(f"[video-downloader] [ERROR] {msg}")
        return DownloadResult(ref_id, success=False, error=msg)


def download_videos_batch(
    reference_posts: list[dict[str, Any]],
    *,
    output_dir: str = "downloads/videos",
    dry_run: bool = True,
    confirm_download: bool = False,
) -> list[DownloadResult]:
    """複数 reference_post を一括ダウンロードする。"""
    results: list[DownloadResult] = []
    for post in reference_posts:
        result = download_video(
            post,
            output_dir=output_dir,
            dry_run=dry_run,
            confirm_download=confirm_download,
        )
        results.append(result)
    return results
