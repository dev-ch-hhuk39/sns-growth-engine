"""
transcription_limiter.py - 文字起こし日次上限管理（120分/日）

設計:
  - 起動時に transcription_runs タブから当日の使用量を読み込む
  - 実行中はインメモリで累積（per-call Sheets 読み取りは行わない）
  - flush() で Sheets に書き戻す（実行終了時に1回だけ）
  - 上限超過分はスキップして skipped_daily_limit_count を増やす
  - client パラメータで MockSheetsClient も使える（テスト可能）
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_uuid() -> str:
    return str(uuid.uuid4())[:8]


class TranscriptionLimiter:
    """日次文字起こし上限を管理するクラス。

    使用方法:
        limiter = TranscriptionLimiter(client, date_str, limit_minutes=120)
        if limiter.can_process(duration_seconds=300.0):
            result = whisper_client.transcribe(...)
            limiter.record(duration_seconds=300.0, status="done")
        else:
            limiter.record_skip()
        limiter.flush()  # 実行終了時に1回呼ぶ
    """

    def __init__(
        self,
        client: Any,
        date_str: str | None = None,
        *,
        limit_minutes: float = 120.0,
        provider: str = "cloudflare_whisper",
        dry_run: bool = True,
    ):
        self._client = client
        self._date = date_str or _today_str()
        self._limit_minutes = limit_minutes
        self._provider = provider
        self._dry_run = dry_run

        existing = client.get_transcription_run_by_date(self._date, provider)
        if existing:
            self._run_id = str(existing.get("run_id", f"tr-{_short_uuid()}"))
            self._used_minutes = float(existing.get("used_minutes", 0.0) or 0.0)
            self._processed_count = int(existing.get("processed_count", 0) or 0)
            self._skipped_count = int(existing.get("skipped_daily_limit_count", 0) or 0)
            self._failed_count = int(existing.get("failed_count", 0) or 0)
        else:
            self._run_id = f"tr-{_short_uuid()}"
            self._used_minutes = 0.0
            self._processed_count = 0
            self._skipped_count = 0
            self._failed_count = 0

        self._flushed = False

    @property
    def remaining_minutes(self) -> float:
        return max(0.0, self._limit_minutes - self._used_minutes)

    @property
    def used_minutes(self) -> float:
        return self._used_minutes

    def can_process(self, duration_seconds: float) -> bool:
        """指定秒数の動画を処理できるか（上限内に収まるか）を返す。"""
        needed = duration_seconds / 60.0
        return self.remaining_minutes >= needed

    def record(self, duration_seconds: float, status: str = "done") -> None:
        """処理済み動画の時間を累積する。status は done / failed。"""
        minutes = duration_seconds / 60.0
        if status == "done":
            self._used_minutes += minutes
            self._processed_count += 1
        elif status == "failed":
            self._failed_count += 1
        print(
            f"[limiter] {status}: +{minutes:.1f}min  "
            f"used={self._used_minutes:.1f}/{self._limit_minutes}min  "
            f"remaining={self.remaining_minutes:.1f}min"
        )

    def record_skip(self) -> None:
        """上限超過によりスキップした動画を記録する。"""
        self._skipped_count += 1
        print(
            f"[limiter] skipped (daily limit): "
            f"used={self._used_minutes:.1f}/{self._limit_minutes}min"
        )

    def flush(self) -> bool:
        """現在の集計を transcription_runs タブに書き戻す。dry_run 時は False を返す。"""
        if self._flushed:
            return False
        self._flushed = True
        remaining = self.remaining_minutes
        status = "completed" if self._processed_count > 0 else "no_work"
        run = {
            "run_id": self._run_id,
            "date": self._date,
            "provider": self._provider,
            "daily_limit_minutes": self._limit_minutes,
            "used_minutes": round(self._used_minutes, 2),
            "remaining_minutes": round(remaining, 2),
            "processed_count": self._processed_count,
            "skipped_daily_limit_count": self._skipped_count,
            "failed_count": self._failed_count,
            "status": status,
            "created_at": _now(),
            "notes": "",
        }
        if self._dry_run:
            print(f"[dry-run][limiter] flush: {run}")
            return False
        self._client.save_transcription_run(run)
        print(
            f"[limiter] flush: date={self._date} used={self._used_minutes:.1f}min "
            f"processed={self._processed_count} skipped={self._skipped_count} failed={self._failed_count}"
        )
        return True

    def summary(self) -> dict:
        """現在の集計サマリーを返す。"""
        return {
            "run_id": self._run_id,
            "date": self._date,
            "provider": self._provider,
            "daily_limit_minutes": self._limit_minutes,
            "used_minutes": round(self._used_minutes, 2),
            "remaining_minutes": round(self.remaining_minutes, 2),
            "processed_count": self._processed_count,
            "skipped_daily_limit_count": self._skipped_count,
            "failed_count": self._failed_count,
        }
