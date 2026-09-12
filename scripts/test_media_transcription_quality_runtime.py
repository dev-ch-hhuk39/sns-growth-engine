#!/usr/bin/env python3
"""Runtime wiring tests, not a claim of speech-recognition accuracy."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from media.direct_content_understanding import transcribe_video  # noqa: E402
from ingest_direct_reference_media import media_understanding_needs_refresh  # noqa: E402


class TranscriptionQualityRuntimeTests(unittest.TestCase):
    def test_direct_model_is_small_with_unchanged_cpu_and_duration_bound(self):
        calls = {}
        class Model:
            def __init__(self, name, **options):
                calls["name"], calls["options"] = name, options
            def transcribe(self, path, **options):
                calls["transcribe"] = options
                return iter([SimpleNamespace(text="fixture speech")]), SimpleNamespace(language="ja")
        with patch.dict("os.environ", {"ALLOW_LOCAL_TRANSCRIPTION": "true"}), \
             patch.dict(sys.modules, {"faster_whisper": SimpleNamespace(WhisperModel=Model)}):
            result = transcribe_video(Path("fixture.mp4"), max_seconds=60)
        self.assertEqual(calls["name"], "small")
        self.assertEqual(calls["options"], {"device": "cpu", "compute_type": "int8", "cpu_threads": 1, "num_workers": 1})
        self.assertEqual(calls["transcribe"]["clip_timestamps"], "0,60")
        self.assertEqual(calls["transcribe"]["language"], "ja")
        self.assertEqual(result["provider"], "faster_whisper_small")

    def test_disabled_does_not_load_model(self):
        def forbidden(*_, **__):
            raise AssertionError("model must not load")
        with patch.dict("os.environ", {"ALLOW_LOCAL_TRANSCRIPTION": "false"}), \
             patch.dict(sys.modules, {"faster_whisper": SimpleNamespace(WhisperModel=forbidden)}):
            self.assertEqual(transcribe_video(Path("fixture.mp4"))["status"], "DISABLED")

    def test_model_failure_remains_unavailable(self):
        def failed(*_, **__):
            raise RuntimeError("unavailable")
        with patch.dict("os.environ", {"ALLOW_LOCAL_TRANSCRIPTION": "true"}), \
             patch.dict(sys.modules, {"faster_whisper": SimpleNamespace(WhisperModel=failed)}):
            result = transcribe_video(Path("fixture.mp4"))
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertEqual(result["text"], "")

    def test_clip_workflow_preserves_budgets_and_no_publish(self):
        workflow = (ROOT / ".github/workflows/approved-source-clip-preparation.yml").read_text()
        self.assertIn("--model-size small --max-audio-seconds 900 --cpu-threads 1", workflow)
        self.assertIn("--limit 2", workflow)
        self.assertIn('ALLOW_REAL_THREADS_POST: "false"', workflow)
        self.assertIn('ALLOW_TRANSCRIPTION_API: "false"', workflow)

    def test_tiny_evidence_refreshed_once_only_after_stored_video_gate(self):
        media = {"media_type": "video", "cloudinary_status": "UPLOADED", "storage_url": "https://example.com/asset.mp4"}
        evidence = {"status": "PASS", "transcript_status": "PASS", "transcript_hash": "old",
                    "transcription_provider": "faster_whisper_tiny"}
        with patch.dict("os.environ", {"ALLOW_LOCAL_TRANSCRIPTION": "true"}):
            self.assertTrue(media_understanding_needs_refresh(media, evidence))
            self.assertFalse(media_understanding_needs_refresh(media, {**evidence, "transcription_provider": "faster_whisper_small"}))
            self.assertFalse(media_understanding_needs_refresh(media, {**evidence, "status": "BLOCKED"}))
            self.assertFalse(media_understanding_needs_refresh({**media, "cloudinary_status": "PENDING"}, evidence))
        with patch.dict("os.environ", {"ALLOW_LOCAL_TRANSCRIPTION": "false"}):
            self.assertFalse(media_understanding_needs_refresh(media, evidence))


if __name__ == "__main__":
    unittest.main()
