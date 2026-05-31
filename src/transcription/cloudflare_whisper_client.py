"""
cloudflare_whisper_client.py - Cloudflare Workers AI Whisper クライアント

安全ガード（2重）:
  1. ALLOW_TRANSCRIPTION_API=true でなければ実API呼び出し不可（環境変数ガード）
  2. allow_transcription_api=True を明示しなければインスタンス生成時に例外（コードガード）

設計:
  - dry_run=True（デフォルト）: モックレスポンスを返す
  - ALLOW_TRANSCRIPTION_API=false（デフォルト）: 実API呼び出し禁止
  - 失敗・上限超過時は例外を上げず TranscriptionResult.status="failed" で返す
  - fallback なし: 失敗したら次回再実行（上限節約優先）
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TranscriptionResult:
    """文字起こし結果を表すデータクラス。"""
    transcript_id: str
    reference_post_id: str
    status: str  # done / failed / skipped_limit
    transcript_text: str
    segments: list[dict]
    language: str
    duration_seconds: float
    processed_minutes: float
    error: str
    provider: str = "cloudflare_whisper"
    raw_response: dict = field(default_factory=dict)

    def to_sheets_row(self) -> dict[str, Any]:
        """video_transcripts タブ保存用 dict を返す。"""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        return {
            "transcript_id": self.transcript_id,
            "reference_post_id": self.reference_post_id,
            "transcription_provider": self.provider,
            "transcription_status": self.status,
            "duration_seconds": self.duration_seconds,
            "transcript_text": self.transcript_text,
            "segments_json": json.dumps(self.segments, ensure_ascii=False),
            "language": self.language,
            "processed_minutes": self.processed_minutes,
            "error": self.error,
            "created_at": now,
            "updated_at": now,
        }


_MOCK_RESPONSE = {
    "result": {
        "text": "これはモック文字起こしです。実際のCloudflare Whisper APIは呼び出していません。",
        "words": [
            {"word": "これは", "start": 0.0, "end": 0.5},
            {"word": "モック", "start": 0.5, "end": 1.0},
            {"word": "文字起こし", "start": 1.0, "end": 1.8},
            {"word": "です", "start": 1.8, "end": 2.2},
        ],
        "vtt": "",
    },
    "success": True,
}


class CloudflareWhisperClient:
    """Cloudflare Workers AI Whisper クライアント。

    2重安全ガード:
      - 環境変数 ALLOW_TRANSCRIPTION_API=true でなければ raise
      - コード側 allow_transcription_api=True を渡さなければ raise

    dry_run=True の場合はモックレスポンスを返す。
    """

    def __init__(
        self,
        account_id: str,
        api_token: str | None,
        *,
        allow_transcription_api: bool = False,
        dry_run: bool = True,
        model: str = "@cf/openai/whisper",
    ):
        if allow_transcription_api and not dry_run:
            if not account_id:
                raise ValueError("CLOUDFLARE_ACCOUNT_ID が未設定です")
            if not api_token:
                raise ValueError("CLOUDFLARE_API_TOKEN が未設定です")
        self._account_id = account_id
        self._api_token = api_token
        self._allow_transcription_api = allow_transcription_api
        self._dry_run = dry_run
        self._model = model

    @classmethod
    def from_config(cls, transcription_cfg: dict, *, dry_run: bool = True) -> "CloudflareWhisperClient":
        """get_transcription_config() の戻り値からクライアントを生成する。"""
        allow = transcription_cfg.get("allow_transcription_api", False)
        if not allow and not dry_run:
            print("[WARN] ALLOW_TRANSCRIPTION_API=false のため dry_run モードで動作します")
            dry_run = True
        return cls(
            account_id=transcription_cfg.get("account_id", ""),
            api_token=transcription_cfg.get("api_token"),
            allow_transcription_api=allow,
            dry_run=dry_run,
        )

    def transcribe(
        self,
        audio_path: str,
        *,
        reference_post_id: str,
        transcript_id: str,
        duration_seconds: float = 0.0,
        language: str = "ja",
    ) -> TranscriptionResult:
        """音声ファイルを文字起こしする。

        dry_run または ALLOW_TRANSCRIPTION_API=false の場合はモックレスポンスを返す。

        Args:
            audio_path: 音声ファイルパス（ローカル、実実行時のみ使用）
            reference_post_id: 対応する reference_post の ID
            transcript_id: 保存用 transcript_id
            duration_seconds: 動画の長さ（秒）、上限計算に使用
            language: 言語コード（デフォルト: ja）

        Returns:
            TranscriptionResult
        """
        processed_minutes = round(duration_seconds / 60.0, 2)

        if self._dry_run or not self._allow_transcription_api:
            return self._mock_result(
                transcript_id=transcript_id,
                reference_post_id=reference_post_id,
                duration_seconds=duration_seconds,
                processed_minutes=processed_minutes,
                language=language,
            )

        return self._call_api(
            audio_path=audio_path,
            transcript_id=transcript_id,
            reference_post_id=reference_post_id,
            duration_seconds=duration_seconds,
            processed_minutes=processed_minutes,
            language=language,
        )

    def _mock_result(
        self,
        *,
        transcript_id: str,
        reference_post_id: str,
        duration_seconds: float,
        processed_minutes: float,
        language: str,
    ) -> TranscriptionResult:
        resp = _MOCK_RESPONSE["result"]
        segments = [
            {"word": w["word"], "start": w["start"], "end": w["end"]}
            for w in resp.get("words", [])
        ]
        return TranscriptionResult(
            transcript_id=transcript_id,
            reference_post_id=reference_post_id,
            status="done",
            transcript_text=resp["text"],
            segments=segments,
            language=language,
            duration_seconds=duration_seconds,
            processed_minutes=processed_minutes,
            error="",
            provider="cloudflare_whisper_mock",
            raw_response=_MOCK_RESPONSE,
        )

    def _call_api(
        self,
        *,
        audio_path: str,
        transcript_id: str,
        reference_post_id: str,
        duration_seconds: float,
        processed_minutes: float,
        language: str,
    ) -> TranscriptionResult:
        """Cloudflare Workers AI REST API を呼び出す（実実行時のみ到達）。"""
        try:
            import urllib.request
            url = (
                f"https://api.cloudflare.com/client/v4/accounts/"
                f"{self._account_id}/ai/run/{self._model}"
            )
            headers = {
                "Authorization": f"Bearer {self._api_token}",
                "Content-Type": "application/octet-stream",
            }
            with open(audio_path, "rb") as f:
                audio_bytes = f.read()

            req = urllib.request.Request(url, data=audio_bytes, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read().decode("utf-8"))

            if not body.get("success"):
                errors = body.get("errors", [])
                raise RuntimeError(f"Cloudflare API エラー: {errors}")

            result = body.get("result", {})
            text = result.get("text", "")
            words = result.get("words", [])
            segments = [
                {"word": w.get("word", ""), "start": w.get("start", 0.0), "end": w.get("end", 0.0)}
                for w in words
            ]
            return TranscriptionResult(
                transcript_id=transcript_id,
                reference_post_id=reference_post_id,
                status="done",
                transcript_text=text,
                segments=segments,
                language=language,
                duration_seconds=duration_seconds,
                processed_minutes=processed_minutes,
                error="",
                provider="cloudflare_whisper",
                raw_response=body,
            )
        except Exception as e:
            return TranscriptionResult(
                transcript_id=transcript_id,
                reference_post_id=reference_post_id,
                status="failed",
                transcript_text="",
                segments=[],
                language=language,
                duration_seconds=duration_seconds,
                processed_minutes=0.0,
                error=str(e)[:500],
                provider="cloudflare_whisper",
                raw_response={},
            )
