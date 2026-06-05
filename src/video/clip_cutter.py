"""
clip_cutter.py - ffmpeg によるクリップ切り抜き基盤

設計:
  - デフォルト: dry_run=True（ffmpeg は実行しない）
  - 実切り抜きは --cut --confirm-cut フラグが両方必要
  - subprocess で ffmpeg を呼ぶが、import 時には ffmpeg の存在確認はしない
  - ffmpeg が存在しない場合は subprocess 例外を try/except でキャッチしてエラー返却
  - 出力先: clips/<account_id>/<clip_id>.mp4（デフォルト）

ClipCutResult:
  clip_id, success, local_clip_path, error, duration_seconds
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ClipCutResult:
    clip_id: str
    success: bool
    local_clip_path: str = ""
    error: str = ""
    duration_seconds: int = 0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_time_to_seconds(time_str: str) -> int:
    """HH:MM:SS または MM:SS を秒数に変換する。"""
    parts = str(time_str).strip().split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        return int(parts[0])
    except (ValueError, IndexError):
        return 0


def _build_output_path(
    output_dir: str,
    account_id: str,
    clip_id: str,
) -> str:
    """切り抜きファイルの出力パスを返す。"""
    account_dir = os.path.join(output_dir, account_id)
    os.makedirs(account_dir, exist_ok=True)
    return os.path.join(account_dir, f"{clip_id}.mp4")


def cut_clip(
    candidate: dict[str, Any],
    source_video_path: str,
    *,
    output_dir: str = "clips",
    dry_run: bool = True,
    confirm_cut: bool = False,
    reencode: bool = False,
) -> ClipCutResult:
    """1件のクリップ候補を ffmpeg で切り抜く。

    Args:
        candidate: video_clip_candidates の1行 dict
        source_video_path: 切り抜き元のローカル動画ファイルパス
        output_dir: 出力先ディレクトリ（デフォルト: clips/）
        dry_run: True の場合は ffmpeg を実行せず結果を返す
        confirm_cut: True かつ dry_run=False の場合のみ実際に切り抜く
        reencode: True の場合 libx264/aac で再エンコード（デフォルト: -c copy）

    Returns:
        ClipCutResult
    """
    clip_id = str(candidate.get("clip_id", "unknown"))
    account_id = str(candidate.get("account_id", "unknown"))
    start_time = str(candidate.get("start_time", "00:00:00"))
    end_time = str(candidate.get("end_time", "00:00:00"))

    start_sec = _parse_time_to_seconds(start_time)
    end_sec = _parse_time_to_seconds(end_time)
    duration_sec = max(0, end_sec - start_sec)

    output_path = _build_output_path(output_dir, account_id, clip_id)

    if dry_run or not confirm_cut:
        mode = "dry-run" if dry_run else "confirm-cut未指定"
        print(
            f"[clip-cutter] [{mode}] clip_id={clip_id!r} "
            f"start={start_time} end={end_time} dur={duration_sec}s "
            f"→ {output_path}"
        )
        return ClipCutResult(
            clip_id=clip_id,
            success=True,
            local_clip_path=output_path,
            duration_seconds=duration_sec,
        )

    # 実切り抜き（--cut --confirm-cut が両方指定された場合のみ）
    if not os.path.isfile(source_video_path):
        msg = f"source_video_path が存在しません: {source_video_path!r}"
        print(f"[clip-cutter] [ERROR] {msg}")
        return ClipCutResult(clip_id=clip_id, success=False, error=msg)

    if reencode:
        codec_flags = ["-c:v", "libx264", "-c:a", "aac"]
    else:
        codec_flags = ["-c", "copy"]

    cmd = [
        "ffmpeg", "-y",
        "-ss", start_time,
        "-to", end_time,
        "-i", source_video_path,
        *codec_flags,
        "-avoid_negative_ts", "1",
        output_path,
    ]
    print(f"[clip-cutter] 実行: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            error_msg = result.stderr[-500:] if result.stderr else "unknown error"
            print(f"[clip-cutter] [ERROR] ffmpeg 失敗: {error_msg}")
            return ClipCutResult(
                clip_id=clip_id,
                success=False,
                error=error_msg,
                duration_seconds=duration_sec,
            )
        print(f"[clip-cutter] 完了: {output_path}")
        return ClipCutResult(
            clip_id=clip_id,
            success=True,
            local_clip_path=output_path,
            duration_seconds=duration_sec,
        )
    except FileNotFoundError:
        msg = "ffmpeg が見つかりません。インストールされているか確認してください。"
        print(f"[clip-cutter] [ERROR] {msg}")
        return ClipCutResult(clip_id=clip_id, success=False, error=msg)
    except subprocess.TimeoutExpired:
        msg = "ffmpeg タイムアウト（300秒）"
        print(f"[clip-cutter] [ERROR] {msg}")
        return ClipCutResult(clip_id=clip_id, success=False, error=msg)
    except Exception as e:
        msg = f"ffmpeg 実行エラー: {e}"
        print(f"[clip-cutter] [ERROR] {msg}")
        return ClipCutResult(clip_id=clip_id, success=False, error=msg)


def cut_clips_batch(
    candidates: list[dict[str, Any]],
    source_video_map: dict[str, str],
    *,
    output_dir: str = "clips",
    dry_run: bool = True,
    confirm_cut: bool = False,
    reencode: bool = False,
) -> list[ClipCutResult]:
    """複数のクリップ候補を一括切り抜きする。

    Args:
        candidates: video_clip_candidates の dict リスト
        source_video_map: {reference_post_id: local_video_path} のマッピング
        output_dir: 出力先ディレクトリ
        dry_run: True の場合は ffmpeg を実行しない
        confirm_cut: True かつ dry_run=False の場合のみ実際に切り抜く
        reencode: True の場合 libx264/aac で再エンコード（デフォルト: -c copy）

    Returns:
        ClipCutResult のリスト
    """
    results: list[ClipCutResult] = []
    for c in candidates:
        ref_id = str(c.get("reference_post_id", ""))
        source_path = source_video_map.get(ref_id, "")
        result = cut_clip(
            c,
            source_path,
            output_dir=output_dir,
            dry_run=dry_run,
            confirm_cut=confirm_cut,
            reencode=reencode,
        )
        results.append(result)
    return results


def update_cut_status(
    client: Any,
    results: list[ClipCutResult],
    *,
    dry_run: bool = True,
) -> dict[str, int]:
    """切り抜き結果を video_clip_candidates タブに反映する。

    dry_run=True の場合は更新をスキップする。
    """
    updated = skipped = errors = 0
    for r in results:
        fields: dict[str, Any] = {
            "cut_status": "done" if r.success else "failed",
        }
        if r.success and r.local_clip_path:
            fields["local_clip_path"] = r.local_clip_path
        if not r.success and r.error:
            fields["notes"] = r.error[:200]

        if dry_run:
            print(
                f"[dry-run] update_cut_status: clip_id={r.clip_id!r} "
                f"cut_status={fields['cut_status']!r}"
            )
            skipped += 1
            continue
        try:
            ok = client.update_video_clip_candidate(r.clip_id, **fields)
            if ok:
                updated += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"[ERROR] update_cut_status 失敗 (clip_id={r.clip_id!r}): {e}")
            errors += 1

    return {"updated": updated, "skipped": skipped, "errors": errors}
