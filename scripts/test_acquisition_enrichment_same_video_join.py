#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from acquisition.contracts import ProviderResult
from acquisition.models import SourceMediaItem, SourcePostBundle
from acquire_approved_source_posts import enrich_posts


class Detail:
    provider_name, provider_version = "detail_fixture", "1"

    def fetch_post_detail(self, post):
        return ProviderResult(self.provider_name, self.provider_version, "PASS", data=post)


class Comments:
    provider_name, provider_version = "comment_fixture", "1"

    def fetch_comments(self, post, *, limit):
        return ProviderResult(self.provider_name, self.provider_version, "PASS", data=[{"comment_id": "c1", "text": "初見でも入りやすい", "author": "viewer"}])


class Transcript:
    provider_name, provider_version = "transcript_fixture", "1"

    def fetch_transcript(self, post):
        return ProviderResult(self.provider_name, self.provider_version, "PASS", data={"text": "今の話題を伝える", "segments": [{"text": "今の話題を伝える", "start": 0, "duration": 3}], "language": "ja"})


post_id = "sp_src_lm_abcdefghijk"
post = SourcePostBundle(
    source_post_id=post_id,
    source_id="src_lm_yt",
    target_account_id="liver_manager",
    platform="youtube",
    profile_url="https://youtube.com/@example",
    canonical_post_url="https://youtube.com/watch?v=abcdefghijk",
    external_post_id="abcdefghijk",
    original_post_text="初見が参加しやすい配信の入口",
    published_at="",
    media_items=(SourceMediaItem(
        source_post_media_id=f"spm_{post_id}_0", source_post_id=post_id, media_index=0,
        media_type="video", canonical_post_url="https://youtube.com/watch?v=abcdefghijk",
        original_media_url="https://youtube.com/watch?v=abcdefghijk", resolver_backend="fixture",
        duration_seconds="60",
    ),),
)
source = {
    "source_id": "src_lm_yt", "source_platform": "youtube", "source_type": "channel",
    "source_url": "https://youtube.com/@example", "target_account_id": "liver_manager",
    "target_account_ids": ["liver_manager"], "rights_status": "approved_creator_clip",
    "permission_status": "approved",
}
providers = {
    "yt_dlp_post_detail": Detail(),
    "youtube_comment_downloader": Comments(),
    "threads_public_comments": Comments(),
    "youtube_transcript_api": Transcript(),
}
posts, videos, transcripts, runs = enrich_posts(source, [post], {"allow_transcription": "true"}, providers)
checks = [
    ("comments remain on the same source post", posts[0].source_post_id == post_id and posts[0].comments[0]["comment_id"] == "c1"),
    ("one discovered post creates one source video", len(videos) == 1 and videos[0]["video_id"] == "abcdefghijk"),
    ("transcript joins the discovered source video", len(transcripts) == 1 and transcripts[0]["source_video_id"] == videos[0]["source_video_id"]),
    ("provider runs are observable without source bodies", len(runs) == 3 and all("original_post_text" not in row for row in runs)),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
failed = [name for name, ok in checks if not ok]
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
