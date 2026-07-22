#!/usr/bin/env python3
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acquisition.enrichment import YouTubeTranscriptProvider
from acquisition.models import SourcePostBundle


class Item:
    def __init__(self, text, start, duration):
        self.text, self.start, self.duration = text, start, duration


class Transcript(list):
    language_code = "ja"
    is_generated = False


class API:
    def fetch(self, video_id, languages):
        return Transcript([Item("最初に話題を伝える", 0, 3), Item("コメントしやすくなる", 3, 3)])


module = types.ModuleType("youtube_transcript_api")
module.YouTubeTranscriptApi = API
sys.modules["youtube_transcript_api"] = module
post = SourcePostBundle(
    source_post_id="sp_yt", source_id="src", target_account_id="liver_manager", platform="youtube",
    profile_url="https://youtube.com/@example", canonical_post_url="https://youtube.com/watch?v=abcdefghijk",
    external_post_id="abcdefghijk", original_post_text="配信の入口", published_at="",
)
result = YouTubeTranscriptProvider().fetch_transcript(post)
checks = [
    ("official caption provider returns PASS", result.status == "PASS"),
    ("segments retain timestamps", bool(result.data and result.data["segments"][1]["start"] == 3)),
    ("provider result carries no secret material", not result.metadata),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
failed = [name for name, ok in checks if not ok]
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
