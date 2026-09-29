#!/usr/bin/env python3
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from media import direct_content_understanding as understanding
from media import gemini_vision
from gemini_hybrid_client import GeminiHybridClient
from sheets_client import TAB_DEFINITIONS

source = inspect.getsource(understanding)
headers = TAB_DEFINITIONS["source_media_understanding"]
checks = [
    ("representative frames are bounded", understanding._frame_timestamps(100) == [15.0, 50.0, 85.0]),
    ("image OCR wired", "tesseract" in source and "jpn+eng" in source),
    ("local Whisper bounded", "faster_whisper" in source and "clip_timestamps" in source),
    ("Gemini Vision wired", "GeminiVisionProvider().understand" in source
     and "generate_multimodal_json" in inspect.getsource(gemini_vision)
     and "inlineData" in inspect.getsource(GeminiHybridClient.generate_multimodal_json)),
    ("retired Vision endpoint removed", "models.github.ai" not in source and "GITHUB_TOKEN" not in source),
    ("no subtitle burn", "subtitles" not in source and "drawtext" not in source),
    ("full evidence schema", {"ocr_text", "transcript_text", "visual_summary", "representative_frame_timestamps_json"} <= set(headers)),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(ok for _, ok in checks) else 1)
