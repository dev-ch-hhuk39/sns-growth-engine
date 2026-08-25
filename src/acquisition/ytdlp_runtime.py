"""Safe, consistent yt-dlp runtime options for metadata-only operations.

Every caller explicitly enables Node. YouTube alone may enable the official
yt-dlp EJS remote component fallback; TikTok never receives that option.
"""
from __future__ import annotations

import os
import shutil
from typing import Any


NODE_RUNTIME_ENV = "SNS_YTDLP_NODE_PATH"
YOUTUBE_EJS_COMPONENT = "ejs:github"
YOUTUBE_POT_PLAYER_FALLBACK = "mweb"
YOUTUBE_PUBLIC_PLAYER_FALLBACK = "web_embedded"
YOUTUBE_BOUNDED_AV_FORMAT = (
    "bestvideo[height<=720][filesize<230M][ext=mp4]+"
    "bestaudio[filesize<70M][ext=m4a]/"
    "best[height<=720][filesize<290M][ext=mp4]/"
    "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/"
    "best[height<=480][ext=mp4]"
)


def configured_node_runtime() -> str:
    """Return an explicit Node binary path without exposing environment data."""
    return str(os.environ.get(NODE_RUNTIME_ENV) or shutil.which("node") or "node")


def metadata_options(platform: str, options: dict[str, Any] | None = None, **overrides: Any) -> dict[str, Any]:
    """Build bounded yt-dlp options for a platform's metadata route.

    Callers remain responsible for playlist, retry, and download limits. The
    helper only owns the runtime and YouTube-only EJS settings.
    """
    configured = dict(options or {})
    configured.update(overrides)
    configured["js_runtimes"] = {"node": {"path": configured_node_runtime()}}
    if str(platform).lower() == "youtube":
        configured["remote_components"] = [YOUTUBE_EJS_COMPONENT]
    return configured


def physical_download_option_attempts(
    platform: str,
    options: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return bounded physical-download attempts without credentials.

    The default YouTube client is tried first. Public videos that hit a runner
    IP bot challenge get bounded fallbacks through the mweb client backed by
    yt-dlp's PO Token Provider framework and then the public embedded client.
    Both fallbacks keep source geometry and prefer 720p while bounding the
    selected streams; long-form media can step down to 480p to stay inside the
    engine's 300 MiB download budget.
    """

    primary = metadata_options(platform, options)
    if str(platform).lower() != "youtube":
        return [primary]

    def player_attempt(player_client: str) -> dict[str, Any]:
        fallback_options = dict(options or {})
        extractor_args = {
            key: dict(value)
            for key, value in dict(fallback_options.get("extractor_args") or {}).items()
        }
        youtube_args = dict(extractor_args.get("youtube") or {})
        youtube_args["player_client"] = [player_client]
        extractor_args["youtube"] = youtube_args
        fallback_options["extractor_args"] = extractor_args
        fallback_options["format"] = YOUTUBE_BOUNDED_AV_FORMAT
        return metadata_options(platform, fallback_options)

    return [
        primary,
        player_attempt(YOUTUBE_POT_PLAYER_FALLBACK),
        player_attempt(YOUTUBE_PUBLIC_PLAYER_FALLBACK),
    ]
