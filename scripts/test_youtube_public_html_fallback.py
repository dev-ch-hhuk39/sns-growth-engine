#!/usr/bin/env python3
from unittest.mock import patch

from discover_approved_source_videos import (
    discover_youtube_public_html,
    is_persistable_source_video,
    youtube_public_video_entries,
    youtube_public_video_ids,
)


class FakeResponse:
    def __init__(self, value: str):
        self.value = value.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit: int):
        return self.value


def main() -> int:
    html = (
        '"videoId":"abcdefghijk"'
        '"videoId":"abcdefghijk"'
        '"videoId":"lmnopqrstuv"'
        '"videoId":"wxyzABCDE12"'
    )
    structured = '''<script>var ytInitialData = {"contents":{"items":[
      {"videoRenderer":{"videoId":"abcdefghijk","title":{"runs":[{"text":"公開動画A"}]},"lengthText":{"simpleText":"1:14"},"publishedTimeText":{"simpleText":"2 days ago"}}},
      {"videoRenderer":{"videoId":"lmnopqrstuv","title":{"simpleText":"公開動画B"},"lengthText":{"simpleText":"1:02:03"}}}
    ]}};</script>'''
    entries = youtube_public_video_entries(structured)
    source = {
        "source_id": "src_beauty_public_channel",
        "source_platform": "youtube",
        "source_type": "channel",
        "source_url": "https://www.youtube.com/@beauty_public_channel",
        "source_handle": "beauty_public_channel",
        "target_account_id": "beauty_account",
        "rights_status": "approved_creator_clip",
        "permission_status": "approved",
    }
    with (
        patch("discover_approved_source_videos.urlopen", return_value=FakeResponse(structured)),
        patch("discover_approved_source_videos.importlib.util.find_spec", return_value=None),
    ):
        rows, status = discover_youtube_public_html(
            source,
            {"max_videos_per_source_scan": 12, "max_new_videos_per_source_per_run": 3},
            {"scan_limit": 12, "per_source_new_limit": 3, "start_position": 1, "mode": "initial"},
        )
    checks = [
        ("dedupes public IDs", youtube_public_video_ids(html, limit=10) == ["abcdefghijk", "lmnopqrstuv", "wxyzABCDE12"]),
        ("respects bounded cap", youtube_public_video_ids(html, limit=2) == ["abcdefghijk", "lmnopqrstuv"]),
        ("supports a bounded later window", youtube_public_video_ids(html, limit=2, start_position=2) == ["lmnopqrstuv", "wxyzABCDE12"]),
        ("does not invent IDs", youtube_public_video_ids("channel page only", limit=3) == []),
        ("parses structured public titles", [row["title"] for row in entries] == ["公開動画A", "公開動画B"]),
        ("parses structured public durations", [row["duration"] for row in entries] == [74, 3723]),
        ("does not parse malformed assignments", youtube_public_video_entries("var ytInitialData = {broken") == []),
        ("structured metadata survives without yt-dlp detail", status == "YOUTUBE_PUBLIC_HTML_FALLBACK" and len(rows) == 2),
        ("structured rows are real and persistable", all(is_persistable_source_video(row) for row in rows)),
        ("fallback remains bounded", [row["video_id"] for row in rows] == ["abcdefghijk", "lmnopqrstuv"]),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
