"""
audio_extractor.py - ffmpeg による音声抽出基盤（Phase 2.26）

設計:
  - デフォルト: dry_run=True（ffmpeg は実行しない）
  - 実抽出は --extract-audio --confirm-extract フラグが両方必要
  - 出力形式: 16kHz mono WAV（Cloudflare Whisper 対応フォーマット）
  - 出力先: downloads/audio/<account_id>/<video_id>.wav（デフォルト）
  - ffmpeg が存在しない場合は subprocess 例外をキャッチしてエラー返却

禁止事項（コード実施保証）:
  - --extract-audio --confirm-extract なしでの実抽出禁止
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Any


@dataclass
class AudioExtractResult:
    reference_post_id: str
    success: bool
    local_audio_path: str = ""
    error: str = ""
    duration_seconds: float = 0.0


def _build_audio_path(output_dir: str, account_id: str, video_id: str) -> str:
    account_dir = os.path.join(output_dir, account_id)
    os.makedirs(account_dir, exist_ok=True)
    fname = f"{video_id}.wav" if video_id else "audio.wav"
    return os.path.join(account_dir, fname)


def extract_audio(
    local_video_path: str,
    reference_post_id: str,
    account_id: str,
    *,
    output_dir: str = "downloads/audio",
    dry_run: bool = True,
    confirm_extract: bool = False,
    sample_rate: int = 16000,
) -> AudioExtractResult:
    """動画ファイルから音声を ffmpeg で抽出する。

    Args:
        local_video_path: ローカル動画ファイルパス
        reference_post_id: reference_posts.id（出力ファイル名に使用）
        account_id: アカウントID
        output_dir: 出力先ディレクトリ（デフォルト: downloads/audio/）
        dry_run: True の場合は ffmpeg を実行せず結果を返す
        confirm_extract: True かつ dry_run=False の場合のみ実際に抽出
        sample_rate: サンプリングレート（デフォルト: 16000）

    Returns:
        AudioExtractResult
    """
    video_id = os.path.splitext(os.path.basename(local_video_path))[0]
    output_path = _build_audio_path(output_dir, account_id, video_id)

    if dry_run or not confirm_extract:
        mode = "dry-run" if dry_run else "confirm-extract未指定"
        print(
            f"[audio-extractor] [{mode}] ref_id={reference_post_id!r} "
            f"input={local_video_path!r} → {output_path}"
        )
        return AudioExtractResult(
            reference_post_id,
            success=True,
            local_audio_path=output_path,
        )

    # 実抽出（--extract-audio --confirm-extract が両方指定された場合のみ）
    if not os.path.isfile(local_video_path):
        msg = f"動画ファイルが存在しません: {local_video_path!r}"
        print(f"[audio-extractor] [ERROR] {msg}")
        return AudioExtractResult(reference_post_id, success=False, error=msg)

    cmd = [
        "ffmpeg", "-y",
        "-i", local_video_path,
        "-vn",                    # 映像を除く
        "-acodec", "pcm_s16le",   # 16bit PCM
        "-ar", str(sample_rate),  # サンプリングレート
        "-ac", "1",               # モノラル
        output_path,
    ]
    print(f"[audio-extractor] 実行: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            error_msg = result.stderr[-500:] if result.stderr else "unknown error"
            print(f"[audio-extractor] [ERROR] ffmpeg 失敗: {error_msg}")
            return AudioExtractResult(reference_post_id, success=False, error=error_msg)
        print(f"[audio-extractor] 完了: {output_path}")
        return AudioExtractResult(
            reference_post_id,
            success=True,
            local_audio_path=output_path,
        )
    except FileNotFoundError:
        msg = "ffmpeg が見つかりません。インストールされているか確認してください。"
        print(f"[audio-extractor] [ERROR] {msg}")
        return AudioExtractResult(reference_post_id, success=False, error=msg)
    except subprocess.TimeoutExpired:
        msg = "ffmpeg タイムアウト（300秒）"
        print(f"[audio-extractor] [ERROR] {msg}")
        return AudioExtractResult(reference_post_id, success=False, error=msg)
    except Exception as e:
        msg = f"ffmpeg 実行エラー: {e}"
        print(f"[audio-extractor] [ERROR] {msg}")
        return AudioExtractResult(reference_post_id, success=False, error=msg)


def extract_audio_batch(
    video_map: list[dict[str, Any]],
    *,
    output_dir: str = "downloads/audio",
    dry_run: bool = True,
    confirm_extract: bool = False,
    sample_rate: int = 16000,
) -> list[AudioExtractResult]:
    """複数動画から音声を一括抽出する。

    Args:
        video_map: [{"reference_post_id": str, "account_id": str, "local_path": str}, ...] のリスト

    Returns:
        AudioExtractResult のリスト
    """
    results: list[AudioExtractResult] = []
    for entry in video_map:
        ref_id = str(entry.get("reference_post_id", ""))
        account_id = str(entry.get("account_id", ""))
        local_path = str(entry.get("local_path", ""))
        result = extract_audio(
            local_path,
            ref_id,
            account_id,
            output_dir=output_dir,
            dry_run=dry_run,
            confirm_extract=confirm_extract,
            sample_rate=sample_rate,
        )
        results.append(result)
    return results
