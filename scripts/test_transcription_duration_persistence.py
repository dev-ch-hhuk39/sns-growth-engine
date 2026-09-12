#!/usr/bin/env python3
"""Offline acquisition-to-registry duration regressions; no external calls."""
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import transcribe_approved_source_videos as runner


class DurationPersistenceTests(unittest.TestCase):
    video = {"source_video_id": "sv_example", "account_id": "liver_manager",
             "platform": "tiktok", "canonical_video_url": "https://www.tiktok.com/@creator/video/1234567890123456789"}
    result = {"ok": True, "text": "transcript", "segments": [{"start": 0, "end": 14, "text": "transcript"}],
              "processed_duration_seconds": 14, "source_duration_seconds": 125.5}

    def test_metadata_reaches_transcript_and_source_registry(self):
        row = runner.build_transcript_row(self.video, self.result)
        update = runner.build_source_update(self.video, row)
        self.assertEqual(float(row["duration_seconds"]), 125.5)
        self.assertEqual(update["duration_seconds"], 125.5)
        self.assertEqual(update["account_id"], "liver_manager")
        self.assertEqual(row["transcription_scope"], "PARTIAL")

    def test_known_duration_preserved(self):
        video = {**self.video, "duration_seconds": 4004}
        row = runner.build_transcript_row(video, self.result)
        self.assertEqual(runner.build_source_update(video, row)["duration_seconds"], 4004)

    def test_bad_metadata_never_becomes_source_duration(self):
        for invalid in (None, "", "unknown", 0, -1, True, "NaN", "Infinity"):
            with self.subTest(invalid=invalid):
                row = runner.build_transcript_row(self.video, {**self.result, "source_duration_seconds": invalid})
                self.assertEqual(row["duration_seconds"], "")
                self.assertEqual(row["transcription_scope"], "UNKNOWN")
                self.assertEqual(runner.build_source_update(self.video, row)["duration_seconds"], "")

    def test_failure_does_not_repair_duration(self):
        row = {"transcription_status": "LOCAL_WHISPER_FAILED", "duration_seconds": 125.5}
        self.assertEqual(runner.build_source_update(self.video, row)["duration_seconds"], "")

    def test_ytdlp_download_returns_metadata_without_second_fetch(self):
        calls = []
        class YDL:
            def __init__(self, options):
                self.options = options
            def __enter__(self):
                return self
            def __exit__(self, *_):
                return False
            def extract_info(self, url, *, download):
                calls.append((url, download, self.options["noplaylist"]))
                Path(self.options["outtmpl"].replace("%(ext)s", "webm")).write_bytes(b"fixture")
                return {"duration": 125.5}
        with TemporaryDirectory() as tmp:
            audio, mode, error, duration = runner._download_audio_with_ytdlp(
                SimpleNamespace(YoutubeDL=YDL), self.video["canonical_video_url"], Path(tmp), "tiktok")
            self.assertTrue(audio.is_file())
            self.assertEqual((mode, error, duration), ("auto", "", 125.5))
        self.assertEqual(calls, [(self.video["canonical_video_url"], True, True)])

    def test_approved_storage_duration_not_used_as_original_duration(self):
        video = {**self.video, "approved_storage_url": "https://res.cloudinary.com/example/video/upload/asset.mp4"}
        with patch.object(runner, "transcribe_with_local_whisper", return_value=self.result):
            row, _ = runner.transcribe_one(video, model_size="tiny", allow_local_whisper=True,
                                          max_audio_seconds=900, cpu_threads=1)
        self.assertEqual(row["duration_seconds"], "")

    def test_local_whisper_preserves_original_duration_before_audio_trim(self):
        class Model:
            def __init__(self, *_, **__):
                pass
            def transcribe(self, *_, **__):
                return iter([SimpleNamespace(start=0, end=14, text="transcript")]), SimpleNamespace(language="ja")
        with TemporaryDirectory() as tmp:
            audio = Path(tmp) / "source.webm"
            audio.write_bytes(b"fixture")
            with patch.dict("os.environ", {"ALLOW_LOCAL_TRANSCRIPTION": "true", "ALLOW_VIDEO_DOWNLOAD": "true"}), \
                 patch.dict(sys.modules, {"yt_dlp": SimpleNamespace(), "faster_whisper": SimpleNamespace(WhisperModel=Model)}), \
                 patch.object(runner, "_download_audio_with_ytdlp", return_value=(audio, "auto", "", 125.5)), \
                 patch.object(runner, "_normalize_audio_for_whisper"):
                result = runner.transcribe_with_local_whisper(self.video["canonical_video_url"], model_size="tiny",
                                                             max_audio_seconds=60, cpu_threads=1)
        self.assertTrue(result["ok"])
        self.assertEqual(result["source_duration_seconds"], 125.5)
        self.assertEqual(result["processed_duration_seconds"], 14)

    def test_youtube_parent_identity_preserves_video_id(self):
        first = runner._canonical_match_url("https://www.youtube.com/watch?v=abcdefghijk&si=share")
        second = runner._canonical_match_url("https://www.youtube.com/watch?v=12345678901")
        self.assertNotEqual(first, second)
        self.assertEqual(first, "https://www.youtube.com/watch?v=abcdefghijk")
        self.assertEqual(runner._canonical_match_url("https://www.youtube.com/watch?si=share"), "")

    def test_other_youtube_video_storage_never_attached(self):
        video = {**self.video, "canonical_video_url": "https://www.youtube.com/watch?v=abcdefghijk"}
        asset = {"account_id": "liver_manager", "upload_status": "UPLOADED", "rights_status": "owned",
                 "permission_status": "approved", "source_post_url": "https://www.youtube.com/watch?v=12345678901",
                 "storage_url": "https://res.cloudinary.com/example/video/upload/other.mp4"}
        enriched = runner.attach_approved_storage_inputs([video], [asset])[0]
        self.assertNotIn("approved_storage_url", enriched)

    def test_persistence_retains_duration(self):
        saved = {}
        client = SimpleNamespace(
            save_video_transcript=lambda row: saved.update(transcript=dict(row)) or True,
            save_source_video=lambda row: saved.update(video=dict(row)) or True,
        )
        row = runner.build_transcript_row(self.video, self.result)
        result = runner.save_rows(client, [row], [runner.build_source_update(self.video, row)])
        self.assertEqual(result["failed"], 0)
        self.assertEqual(saved["video"]["duration_seconds"], 125.5)
        self.assertEqual(json.loads(saved["transcript"]["segments_json"])[0]["end"], 14)


if __name__ == "__main__":
    unittest.main()
