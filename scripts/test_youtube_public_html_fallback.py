#!/usr/bin/env python3
from discover_approved_source_videos import youtube_public_video_ids


def main() -> int:
    html = (
        '"videoId":"abcdefghijk"'
        '"videoId":"abcdefghijk"'
        '"videoId":"lmnopqrstuv"'
        '"videoId":"wxyzABCDE12"'
    )
    checks = [
        ("dedupes public IDs", youtube_public_video_ids(html, limit=10) == ["abcdefghijk", "lmnopqrstuv", "wxyzABCDE12"]),
        ("respects bounded cap", youtube_public_video_ids(html, limit=2) == ["abcdefghijk", "lmnopqrstuv"]),
        ("supports a bounded later window", youtube_public_video_ids(html, limit=2, start_position=2) == ["lmnopqrstuv", "wxyzABCDE12"]),
        ("does not invent IDs", youtube_public_video_ids("channel page only", limit=3) == []),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
