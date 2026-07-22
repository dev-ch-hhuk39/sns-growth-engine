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
