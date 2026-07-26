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
    if not url:
        return SourcePostIdentity("", "", "", "NONE")
        
    raw = str(url).strip()
    if "://" not in raw:
        raw = "https://" + raw.lstrip("/")
        
    parsed = urllib.parse.urlparse(raw)
    netloc = parsed.netloc.lower()
    path = parsed.path
    query = urllib.parse.parse_qs(parsed.query)

    youtube_hosts = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
    youtu_be_hosts = {"youtu.be", "www.youtu.be"}
    threads_hosts = {"threads.net", "www.threads.net", "threads.com", "www.threads.com"}
    tiktok_hosts = {"tiktok.com", "www.tiktok.com", "m.tiktok.com"}
    tiktok_short_hosts = {"vm.tiktok.com", "vt.tiktok.com"}

    if netloc in youtu_be_hosts:
        parts = [p for p in path.strip("/").split("/") if p]
        if len(parts) == 1:
            vid = parts[0]
            if vid:
                return SourcePostIdentity("youtube", "youtube_video", vid, "HIGH")
                
    if netloc in youtube_hosts:
        if path == "/watch":
            vid = query.get("v", [""])[0]
            if vid:
                return SourcePostIdentity("youtube", "youtube_video", vid, "HIGH")
        elif path.startswith("/shorts/"):
            parts = [p for p in path.strip("/").split("/") if p]
            if len(parts) == 2 and parts[0] == "shorts":
                vid = parts[1]
                if vid:
                    return SourcePostIdentity("youtube", "youtube_video", vid, "HIGH")
        elif path.startswith("/live/"):
            parts = [p for p in path.strip("/").split("/") if p]
            if len(parts) == 2 and parts[0] == "live":
                vid = parts[1]
                if vid:
                    return SourcePostIdentity("youtube", "youtube_video", vid, "HIGH")

    if netloc in threads_hosts:
        parts = [p for p in path.strip("/").split("/") if p]
        if len(parts) >= 3 and parts[0].startswith("@") and parts[1] == "post":
            shortcode = parts[2]
            return SourcePostIdentity("threads", "threads_post", shortcode, "HIGH")

    if netloc in tiktok_hosts:
        parts = [p for p in path.strip("/").split("/") if p]
        if len(parts) >= 3 and parts[0].startswith("@") and parts[1] == "video":
            video_id = parts[2]
            return SourcePostIdentity("tiktok", "tiktok_video", video_id, "HIGH")

    if netloc in tiktok_short_hosts:
        return SourcePostIdentity("", "", "", "NONE")

    return SourcePostIdentity("", "", "", "NONE")
