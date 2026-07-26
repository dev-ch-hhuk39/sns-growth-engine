import urllib.parse
import re
from dataclasses import dataclass
from typing import Literal

IdentityConfidence = Literal["HIGH", "LOW", "NONE"]

@dataclass(frozen=True)
class SourcePostIdentity:
    platform: str
    identity_kind: str
    stable_post_id: str
    confidence: IdentityConfidence

def extract_source_post_identity(
    url: str,
    platform_hint: str = "",
) -> SourcePostIdentity:
    parsed = urllib.parse.urlparse(url)
    netloc = parsed.netloc.lower()
    path = parsed.path
    query = urllib.parse.parse_qs(parsed.query)

    # 1. YouTube
    # youtube.com/watch?v=<video_id>
    # m.youtube.com/watch?v=<video_id>
    # music.youtube.com/watch?v=<video_id>
    # youtube.com/shorts/<video_id>
    # youtube.com/live/<video_id>
    # youtu.be/<video_id>
    if "youtube.com" in netloc or "youtu.be" in netloc:
        if "youtu.be" in netloc:
            # path is /<video_id>
            vid = path.strip("/")
            if vid:
                return SourcePostIdentity("youtube", "youtube_video", vid, "HIGH")
        else:
            if path.startswith("/watch"):
                vid = query.get("v", [""])[0]
                if vid:
                    return SourcePostIdentity("youtube", "youtube_video", vid, "HIGH")
            elif path.startswith("/shorts/"):
                vid = path.split("/")[2]
                if vid:
                    return SourcePostIdentity("youtube", "youtube_video", vid, "HIGH")
            elif path.startswith("/live/"):
                vid = path.split("/")[2]
                if vid:
                    return SourcePostIdentity("youtube", "youtube_video", vid, "HIGH")

    # 2. Threads
    # threads.net/@<user>/post/<shortcode>
    # threads.com/@<user>/post/<shortcode>
    if "threads.net" in netloc or "threads.com" in netloc:
        parts = path.strip("/").split("/")
        if len(parts) >= 3 and parts[0].startswith("@") and parts[1] == "post":
            shortcode = parts[2]
            return SourcePostIdentity("threads", "threads_post", shortcode, "HIGH")

    # 3. TikTok
    # tiktok.com/@<user>/video/<video_id>
    if "tiktok.com" in netloc:
        if netloc in ["vm.tiktok.com", "vt.tiktok.com"]:
            return SourcePostIdentity("", "", "", "NONE")
        parts = path.strip("/").split("/")
        if len(parts) >= 3 and parts[0].startswith("@") and parts[1] == "video":
            video_id = parts[2]
            return SourcePostIdentity("tiktok", "tiktok_video", video_id, "HIGH")

    return SourcePostIdentity("", "", "", "NONE")
