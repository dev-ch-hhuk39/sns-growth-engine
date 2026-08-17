"""Bounded, anonymous Threads acquisition backed by public OSS surfaces.

The primary adapter invokes tamnd/threads-cli in crawler-only mode.  The
secondary adapter uses the same anonymous profile identity and a logged-out
persisted query.  Neither adapter accepts Threads tokens, cookies or browser
state.  A public Playwright adapter remains the final router fallback.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import (
    NormalizedMediaItem,
    NormalizedSourcePost,
    canonical_url,
    external_post_id,
    stable_content_hash,
    utc_now,
)
from .router import BackendFailure
from .threads_official import canonical_threads_post_url, threads_handle

THREADS_CLI_VERSION = "0.1.1"
THREADS_GRAPHQL_URL = "https://www.threads.com/api/graphql"
THREADS_PROFILE_THREADS_DOC_ID = "33773912952222602"
THREADS_IG_APP_ID = "238260118697367"
MAX_PROFILE_POSTS = 5

CommandRunner = Callable[[list[str], dict[str, str], int], tuple[int, str, str]]
JsonPoster = Callable[[str, dict[str, str], bytes], dict[str, Any]]


def _target_account(source: dict[str, Any]) -> str:
    targets = source.get("target_account_ids") or [source.get("target_account_id")]
    return str(targets[0] if targets else "")


def _default_runner(
    command: list[str], environment: dict[str, str], timeout: int
) -> tuple[int, str, str]:
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=environment,
    )
    return completed.returncode, completed.stdout, completed.stderr


def _anonymous_environment() -> dict[str, str]:
    environment = dict(os.environ)
    # threads-cli supports optional authenticated depth.  This integration is
    # deliberately crawler-only even if unrelated credentials exist at runtime.
    for name in (
        "THREADS_TOKEN",
        "THREADS_SESSION",
        "THREADS_CSRF",
        "THREADS_DISCOVERY_ACCESS_TOKEN",
    ):
        environment.pop(name, None)
    return environment


def _media_kind(parent_type: str, url: str) -> str:
    normalized = parent_type.upper()
    if normalized == "VIDEO" or ".mp4" in url.lower():
        return "video"
    return "image"


def normalize_public_post(
    source: dict[str, Any],
    row: dict[str, Any],
    *,
    backend_name: str,
    backend_version: str,
) -> NormalizedSourcePost:
    """Normalize one exact-author public post and preserve media order."""
    expected_handle = threads_handle(str(source.get("source_url") or ""))
    author_handle = str(row.get("username") or "").lower().lstrip("@")
    if expected_handle and author_handle != expected_handle:
        raise BackendFailure("threads_author_mismatch")

    post_url = canonical_threads_post_url(str(row.get("permalink") or ""))
    if not post_url:
        raise BackendFailure("threads_individual_post_url_required")
    if expected_handle and threads_handle(post_url) != expected_handle:
        raise BackendFailure("threads_permalink_author_mismatch")

    source_id = str(source.get("source_id") or "")
    external = str(row.get("id") or external_post_id(post_url))
    source_post_id = f"sp_{source_id}_{external}"
    parent_type = str(row.get("media_type") or "")
    media_urls = row.get("media_urls") or []
    if not isinstance(media_urls, list):
        media_urls = []

    media: list[NormalizedMediaItem] = []
    # A quoted post's media belongs to another author.  It may inform text
    # analysis, but it cannot be attached to this registered source post.
    if not bool(row.get("is_quote_post")):
        for raw_url in media_urls:
            media_url = canonical_url(str(raw_url or ""))
            if not media_url.startswith("https://"):
                continue
            index = len(media)
            media.append(
                NormalizedMediaItem(
                    source_post_media_id=f"spm_{source_post_id}_{index}",
                    source_post_id=source_post_id,
                    media_index=index,
                    media_type=_media_kind(parent_type, media_url),
                    canonical_post_url=post_url,
                    original_media_url=media_url,
                    resolver_backend=backend_name,
                )
            )

    text = str(row.get("text") or "").strip()
    return NormalizedSourcePost(
        source_post_id=source_post_id,
        source_id=source_id,
        target_account_id=_target_account(source),
        platform="threads",
        profile_url=canonical_url(str(source.get("source_url") or "")),
        canonical_post_url=post_url,
        external_post_id=external,
        original_post_text=text,
        published_at=str(row.get("timestamp") or ""),
        author_handle=author_handle,
        media_items=tuple(media),
        engagement={
            "like_count": int(row.get("like_count") or 0),
            "reply_count": int(row.get("reply_count") or 0),
            "repost_count": int(row.get("repost_count") or 0),
            "quote_count": int(row.get("quote_count") or 0),
        },
        collection_backend=backend_name,
        backend_version=backend_version,
        content_hash=stable_content_hash(
            text, [item.original_media_url for item in media]
        ),
        discovered_at=utc_now(),
        detail_status="PASS" if text else "PARTIAL",
    )


class ThreadsCliPublicAdapter:
    """Read the crawler-rendered Threads surface through pinned threads-cli."""

    backend_name = "threads_cli_public"
    backend_version = f"threads-cli-{THREADS_CLI_VERSION}"

    def __init__(
        self,
        runner: CommandRunner | None = None,
        binary_path: str | None = None,
    ) -> None:
        self._runner = runner or _default_runner
        self._binary_path = binary_path

    def _binary(self) -> str:
        configured = self._binary_path or os.environ.get("THREADS_CLI_PATH", "")
        binary = configured or shutil.which("th") or ""
        if not binary:
            raise BackendFailure("threads_cli_not_installed")
        return binary

    def _invoke(self, arguments: list[str]) -> Any:
        code, stdout, stderr = self._runner(
            [self._binary(), *arguments], _anonymous_environment(), 90
        )
        if code != 0:
            reason = " ".join(str(stderr or "").split())[-240:]
            if code == 4:
                raise BackendFailure("threads_public_login_wall")
            if code == 5:
                raise BackendFailure("threads_rate_limited")
            raise BackendFailure(f"threads_cli_exit_{code}:{reason}")
        if not stdout.strip():
            raise BackendFailure("threads_cli_no_public_posts")
        try:
            return json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise BackendFailure("threads_cli_invalid_json") from exc

    def profile_identity(self, source: dict[str, Any]) -> dict[str, Any]:
        handle = threads_handle(str(source.get("source_url") or ""))
        if not handle:
            raise BackendFailure("threads_profile_handle_required")
        payload = self._invoke(["profile", handle, "-o", "json"])
        if isinstance(payload, list):
            payload = payload[0] if payload else {}
        if not isinstance(payload, dict) or not str(payload.get("id") or ""):
            raise BackendFailure("threads_cli_profile_identity_unavailable")
        actual = str(payload.get("username") or "").lower().lstrip("@")
        if actual != handle:
            raise BackendFailure("threads_profile_identity_mismatch")
        return payload

    def acquire(
        self, source: dict[str, Any], *, limit: int
    ) -> list[NormalizedSourcePost]:
        handle = threads_handle(str(source.get("source_url") or ""))
        if not handle:
            raise BackendFailure("threads_profile_handle_required")
        bounded = min(MAX_PROFILE_POSTS, max(1, int(limit)))
        payload = self._invoke(
            ["profile", handle, "--posts", "-n", str(bounded), "-o", "json"]
        )
        if not isinstance(payload, list):
            raise BackendFailure("threads_cli_posts_payload_invalid")
        posts = [
            normalize_public_post(
                source,
                row,
                backend_name=self.backend_name,
                backend_version=self.backend_version,
            )
            for row in payload[:bounded]
            if isinstance(row, dict) and not bool(row.get("is_reply"))
        ]
        if not posts:
            raise BackendFailure("threads_cli_no_public_posts")
        return posts


def _default_json_poster(
    url: str, headers: dict[str, str], body: bytes
) -> dict[str, Any]:
    request = Request(url, data=body, headers=headers, method="POST")
    with urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise BackendFailure(f"threads_graphql_http_status:{response.status}")
        payload = json.loads(response.read(4_000_000).decode("utf-8"))
    if not isinstance(payload, dict):
        raise BackendFailure("threads_graphql_payload_invalid")
    return payload


def _thread_post_nodes(value: Any, *, depth: int = 0) -> list[dict[str, Any]]:
    if depth > 30:
        return []
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        items = value.get("thread_items")
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and isinstance(item.get("post"), dict):
                    found.append(item["post"])
        for nested in value.values():
            found.extend(_thread_post_nodes(nested, depth=depth + 1))
    elif isinstance(value, list):
        for nested in value:
            found.extend(_thread_post_nodes(nested, depth=depth + 1))
    return found


def _candidate_url(node: dict[str, Any], key: str) -> str:
    values = node.get(key) or []
    if isinstance(values, list):
        for value in values:
            if isinstance(value, dict) and str(value.get("url") or "").startswith(
                "https://"
            ):
                return str(value["url"])
    return ""


def _raw_graph_post(node: dict[str, Any]) -> dict[str, Any]:
    user = node.get("user") if isinstance(node.get("user"), dict) else {}
    caption = node.get("caption") if isinstance(node.get("caption"), dict) else {}
    media_type = int(node.get("media_type") or 0)
    media_urls: list[str] = []
    kind = "TEXT_POST"
    if media_type == 1:
        kind = "IMAGE"
        versions = node.get("image_versions2")
        if isinstance(versions, dict):
            url = _candidate_url(versions, "candidates")
            if url:
                media_urls.append(url)
    elif media_type == 2:
        kind = "VIDEO"
        url = _candidate_url(node, "video_versions")
        if url:
            media_urls.append(url)
    elif media_type == 8:
        kind = "CAROUSEL_ALBUM"
        children = node.get("carousel_media") or []
        for child in children if isinstance(children, list) else []:
            if not isinstance(child, dict):
                continue
            if int(child.get("media_type") or 0) == 2:
                url = _candidate_url(child, "video_versions")
            else:
                versions = child.get("image_versions2")
                url = (
                    _candidate_url(versions, "candidates")
                    if isinstance(versions, dict)
                    else ""
                )
            if url:
                media_urls.append(url)
    handle = str(user.get("username") or "").lower().lstrip("@")
    code = str(node.get("code") or "")
    taken_at = node.get("taken_at")
    timestamp = ""
    try:
        timestamp = datetime.fromtimestamp(
            float(taken_at), tz=timezone.utc
        ).isoformat()
    except (TypeError, ValueError, OSError):
        pass
    app_info = (
        node.get("text_post_app_info")
        if isinstance(node.get("text_post_app_info"), dict)
        else {}
    )
    return {
        "id": str(node.get("pk") or node.get("id") or "").split("_", 1)[0],
        "shortcode": code,
        "text": str(caption.get("text") or ""),
        "media_type": kind,
        "media_urls": media_urls,
        "permalink": (
            f"https://www.threads.com/@{handle}/post/{code}"
            if handle and code
            else ""
        ),
        "username": handle,
        "timestamp": timestamp,
        "like_count": int(node.get("like_count") or 0),
        "reply_count": int(app_info.get("direct_reply_count") or 0),
        "repost_count": int(app_info.get("repost_count") or 0),
        "quote_count": int(app_info.get("quote_count") or 0),
        "is_quote_post": bool(app_info.get("is_quote_post")),
        "is_reply": app_info.get("reply_to_author") is not None,
    }


class ThreadsLoggedOutGraphQLAdapter:
    """Fallback for the bounded logged-out persisted profile query."""

    backend_name = "threads_logged_out_graphql"
    backend_version = f"persisted-{THREADS_PROFILE_THREADS_DOC_ID}"

    def __init__(
        self,
        profile_loader: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        json_poster: JsonPoster | None = None,
    ) -> None:
        self._profile_loader = profile_loader or ThreadsCliPublicAdapter().profile_identity
        self._json_poster = json_poster or _default_json_poster

    def acquire(
        self, source: dict[str, Any], *, limit: int
    ) -> list[NormalizedSourcePost]:
        identity = self._profile_loader(source)
        user_id = str(identity.get("id") or "")
        expected = threads_handle(str(source.get("source_url") or ""))
        actual = str(identity.get("username") or "").lower().lstrip("@")
        if not user_id:
            raise BackendFailure("threads_graphql_user_id_unavailable")
        if expected and actual != expected:
            raise BackendFailure("threads_profile_identity_mismatch")
        bounded = min(MAX_PROFILE_POSTS, max(1, int(limit)))
        variables = {
            "userID": user_id,
            "__relay_internal__pv__BarcelonaIsLoggedInrelayprovider": False,
            "__relay_internal__pv__BarcelonaIsInternalUserrelayprovider": False,
            "__relay_internal__pv__BarcelonaIsCrawlerrelayprovider": True,
            "__relay_internal__pv__BarcelonaOptionalCookiesEnabledrelayprovider": True,
            "__relay_internal__pv__BarcelonaIsLoggedOutrelayprovider": True,
        }
        body = urlencode(
            {
                "lsd": "t",
                "doc_id": THREADS_PROFILE_THREADS_DOC_ID,
                "variables": json.dumps(variables, separators=(",", ":")),
            }
        ).encode("utf-8")
        payload = self._json_poster(
            THREADS_GRAPHQL_URL,
            {
                "User-Agent": (
                    "Mozilla/5.0 (compatible; Googlebot/2.1; "
                    "+http://www.google.com/bot.html)"
                ),
                "Content-Type": "application/x-www-form-urlencoded",
                "X-FB-LSD": "t",
                "X-IG-App-ID": THREADS_IG_APP_ID,
            },
            body,
        )
        nodes = _thread_post_nodes(payload.get("data"))
        posts: list[NormalizedSourcePost] = []
        seen: set[str] = set()
        for node in nodes:
            row = _raw_graph_post(node)
            if row.get("is_reply") or not row.get("id") or row["id"] in seen:
                continue
            seen.add(str(row["id"]))
            posts.append(
                normalize_public_post(
                    source,
                    row,
                    backend_name=self.backend_name,
                    backend_version=self.backend_version,
                )
            )
            if len(posts) >= bounded:
                break
        if not posts:
            raise BackendFailure(
                "threads_logged_out_graphql_no_posts_or_stale_doc_id"
            )
        return posts
