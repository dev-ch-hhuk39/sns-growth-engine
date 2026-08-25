"""Cookie-free, serial public Threads profile and post adapters.

This deliberately avoids private GraphQL calls, token capture, stealth plugins,
stored browser state and CAPTCHA workarounds.  It reads only public HTML from
one browser context at a time and reports an ordinary backend failure when a
profile no longer exposes post links.
"""

from __future__ import annotations

import base64
import html
import json
import os
import re
from typing import Any, Callable
from urllib.parse import urljoin

from .contracts import ProviderResult
from .models import (
    NormalizedMediaItem,
    NormalizedSourcePost,
    canonical_url,
    external_post_id,
    stable_content_hash,
    utc_now,
)
from .router import BackendFailure

POST_HREF = re.compile(r"/(?:@[^/]+/)?post/[A-Za-z0-9_-]+")
META = re.compile(
    r"<meta[^>]+(?:property|name)=[\"'](?P<key>[^\"']+)[\"'][^>]+content=[\"'](?P<value>[^\"']+)[\"'][^>]*>",
    re.I,
)


def _meta_values(page_html: str, key: str) -> list[str]:
    values = []
    for match in META.finditer(page_html):
        if match.group("key").lower() == key.lower():
            values.append(html.unescape(match.group("value")))
    return list(dict.fromkeys(values))


def _json_scripts(page_html: str):
    for payload in re.findall(r"<script[^>]*>(.*?)</script>", page_html, flags=re.I | re.S):
        candidate = html.unescape(payload.strip())
        if not candidate or candidate[0] not in "[{":
            continue
        try:
            yield json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _walk(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk(nested)


def _https(value: Any) -> str:
    candidate = html.unescape(str(value or "")).replace("\\/", "/")
    return candidate if candidate.startswith("https://") else ""


def _media_from_node(node: dict[str, Any]) -> tuple[str, str] | None:
    video_candidates = node.get("video_versions") or node.get("video_candidates") or []
    if isinstance(video_candidates, list):
        for candidate in video_candidates:
            if isinstance(candidate, dict):
                url = _https(candidate.get("url") or candidate.get("src"))
                if url:
                    return "video", url
    for key in ("video_url", "video_src", "playback_url"):
        url = _https(node.get(key))
        if url:
            return "video", url

    image_versions = node.get("image_versions2") or node.get("image_versions") or {}
    if isinstance(image_versions, dict):
        image_candidates = image_versions.get("candidates") or []
        if isinstance(image_candidates, list):
            for candidate in image_candidates:
                if isinstance(candidate, dict):
                    url = _https(candidate.get("url") or candidate.get("src"))
                    if url:
                        return "image", url
    for key in ("image_url", "display_url", "image_src"):
        url = _https(node.get(key))
        if url:
            return "image", url
    return None


def extract_ordered_post_media(page_html: str) -> list[tuple[str, str]]:
    """Extract ordered carousel children from public embedded post JSON.

    Only explicit carousel-like arrays are accepted.  Generic hydration lists
    are intentionally ignored so profile avatars and recommended posts cannot
    be attached to the selected source post.
    """
    carousel_keys = ("carousel_media", "carousel_media_items", "carousel_items", "children")
    for payload in _json_scripts(page_html):
        for node in _walk(payload):
            for key in carousel_keys:
                children = node.get(key)
                if not isinstance(children, list) or not children:
                    continue
                ordered: list[tuple[str, str]] = []
                for child in children:
                    if not isinstance(child, dict):
                        continue
                    found = _media_from_node(child)
                    if found and found not in ordered:
                        ordered.append(found)
                if ordered:
                    return ordered
    return []


def extract_profile_post_urls(page_html: str, profile_url: str, *, limit: int) -> list[str]:
    """Extract stable public post paths that belong to the requested profile."""
    expected_handle = _profile_handle(profile_url)
    paths = []
    for match in POST_HREF.finditer(page_html):
        path = match.group(0)
        value = canonical_url(urljoin(profile_url, path))
        if expected_handle and _post_handle(value) != expected_handle:
            continue
        if value not in paths:
            paths.append(value)
        if len(paths) >= limit:
            break
    return paths


def _profile_handle(profile_url: str) -> str:
    match = re.search(r"/@([^/?#]+)", canonical_url(profile_url))
    return match.group(1).lower() if match else ""


def _post_handle(post_url: str) -> str:
    match = re.search(r"/@([^/]+)/post/", canonical_url(post_url))
    return match.group(1).lower() if match else ""


_THREADS_UI_LINES = {
    "log in",
    "login",
    "sign up",
    "continue with instagram",
    "threadsを始める",
    "ログイン",
    "登録",
}


def _usable_rendered_text(candidates: list[str], handle: str) -> str:
    """Select source text from rendered post-scoped DOM candidates."""
    cleaned: list[str] = []
    normalized_handle = handle.lower().lstrip("@")
    for value in candidates:
        lines = []
        for raw_line in str(value or "").splitlines():
            line = " ".join(raw_line.split()).strip()
            lowered = line.lower()
            if not line or lowered in _THREADS_UI_LINES:
                continue
            if normalized_handle and lowered.lstrip("@") == normalized_handle:
                continue
            if "log in to see" in lowered or "threadsでさらに" in line:
                continue
            if re.fullmatch(r"[\d,.]+(?:[kKmM万])?", line):
                continue
            lines.append(line)
        candidate = "\n".join(lines).strip()
        if len(candidate) >= 8 and candidate not in cleaned:
            cleaned.append(candidate)
    return max(cleaned, key=len, default="")


def normalized_post_from_rendered(
    source: dict[str, Any],
    post_url: str,
    rendered: dict[str, Any],
    *,
    backend_name: str,
    backend_version: str,
) -> NormalizedSourcePost:
    """Build one post bundle from a single rendered post root.

    The caller must scope every text/media candidate to the same individual
    post container. This helper preserves DOM media order and rejects profile
    pages, blob URLs, avatars and unrelated recommendation cards.
    """
    canonical_post = canonical_url(post_url)
    external = external_post_id(canonical_post)
    if "/post/" not in canonical_post:
        raise BackendFailure("threads_individual_post_url_required")
    handle = _post_handle(canonical_post)
    original_text = _usable_rendered_text(
        [str(value) for value in rendered.get("text_candidates", [])], handle
    )
    media: list[NormalizedMediaItem] = []
    seen_urls: set[str] = set()
    source_id = str(source.get("source_id") or "")
    post_id = f"sp_{source_id}_{external}"
    for item in rendered.get("media", []):
        if not isinstance(item, dict):
            continue
        media_type = str(item.get("media_type") or "").lower()
        media_url = canonical_url(str(item.get("url") or ""))
        if media_type not in {"image", "video"} or not media_url.startswith("https://"):
            continue
        lowered = media_url.lower()
        if media_url in seen_urls or any(
            marker in lowered
            for marker in ("profile_pic", "/t51.82787-19/", "/t51.2885-19/")
        ):
            continue
        width = str(item.get("width") or "")
        height = str(item.get("height") or "")
        try:
            if media_type == "image" and int(width or 0) < 180 and int(height or 0) < 180:
                continue
        except ValueError:
            pass
        seen_urls.add(media_url)
        media.append(
            NormalizedMediaItem(
                source_post_media_id=f"spm_{post_id}_{len(media)}",
                source_post_id=post_id,
                media_index=len(media),
                media_type=media_type,
                canonical_post_url=canonical_post,
                original_media_url=media_url,
                resolver_backend=backend_name,
                width=width,
                height=height,
                duration_seconds=str(item.get("duration_seconds") or ""),
                thumbnail_url=canonical_url(str(item.get("poster") or "")),
            )
        )
    account_id = str(
        (source.get("target_account_ids") or [source.get("target_account_id")])[0]
        or ""
    )
    return NormalizedSourcePost(
        source_post_id=post_id,
        source_id=source_id,
        target_account_id=account_id,
        platform="threads",
        profile_url=canonical_url(str(source.get("source_url") or "")),
        canonical_post_url=canonical_post,
        external_post_id=external,
        original_post_text=original_text,
        published_at=str(rendered.get("published_at") or ""),
        author_name=str(rendered.get("author_name") or ""),
        author_handle=handle,
        media_items=tuple(media),
        engagement={},
        collection_backend=backend_name,
        backend_version=backend_version,
        content_hash=stable_content_hash(
            original_text, [item.original_media_url for item in media]
        ),
        discovered_at=utc_now(),
        detail_status="PASS" if original_text else "PARTIAL",
    )


def extract_profile_post_urls_from_hrefs(
    hrefs: list[str], profile_url: str, *, limit: int
) -> list[str]:
    """Normalize bounded visible-anchor results from a rendered public page.

    This is intentionally separate from raw HTML parsing: Threads often adds
    post anchors after the initial document response.  Only anchors for the
    requested profile are accepted, so recommendation cards cannot become a
    source post.
    """
    expected_handle = _profile_handle(profile_url)
    urls: list[str] = []
    for href in hrefs:
        value = canonical_url(urljoin(profile_url, str(href or "")))
        if not expected_handle or _post_handle(value) != expected_handle:
            continue
        if value not in urls:
            urls.append(value)
        if len(urls) >= max(1, int(limit)):
            break
    return urls


def bounded_profile_scroll_attempts(requested_posts: int) -> int:
    """Scale profile discovery while keeping every scan strictly bounded."""
    requested = max(1, int(requested_posts))
    return min(12, max(3, (requested + 3) // 4))


def parse_public_post_html(
    source: dict[str, Any],
    post_url: str,
    page_html: str,
    *,
    backend_name: str = "threads_public_playwright",
    backend_version: str = "public-html-v1",
) -> NormalizedSourcePost:
    """Normalize one public post page without retaining the raw HTML."""
    canonical_post = canonical_url(post_url)
    external = external_post_id(canonical_post)
    source_id = str(source["source_id"])
    post_id = f"sp_{source_id}_{external}"
    description = _meta_values(page_html, "og:description") or _meta_values(
        page_html, "description"
    )
    original_text = description[0] if description else ""
    author = _meta_values(page_html, "og:title")
    image_urls = _meta_values(page_html, "og:image")
    video_urls = _meta_values(page_html, "og:video") + _meta_values(
        page_html, "og:video:secure_url"
    )
    media: list[NormalizedMediaItem] = []
    ordered = extract_ordered_post_media(page_html)
    # An OG image on a Threads page can be the account avatar or a generic
    # share card.  It is useful as a thumbnail but is not evidence that the
    # asset belongs to this individual post.  Never promote it to a reusable
    # media child without an explicit post-bound structured media record.
    if not ordered:
        ordered = [("video", url) for url in video_urls]
    for index, (media_type, media_url) in enumerate(dict.fromkeys(ordered)):
        media.append(
            NormalizedMediaItem(
                source_post_media_id=f"spm_{post_id}_{index}",
                source_post_id=post_id,
                media_index=index,
                media_type=media_type,
                canonical_post_url=canonical_post,
                original_media_url=canonical_url(media_url),
                resolver_backend=backend_name,
                thumbnail_url=image_urls[0] if media_type == "video" and image_urls else "",
            )
        )
    account_id = str(
        (source.get("target_account_ids") or [source.get("target_account_id")])[0] or ""
    )
    handle = ""
    match = re.search(r"/@([^/]+)/post/", canonical_post)
    if match:
        handle = match.group(1)
    return NormalizedSourcePost(
        source_post_id=post_id,
        source_id=source_id,
        target_account_id=account_id,
        platform="threads",
        profile_url=canonical_url(str(source.get("source_url") or "")),
        canonical_post_url=canonical_post,
        external_post_id=external,
        original_post_text=original_text,
        published_at="",
        author_name=author[0] if author else "",
        author_handle=handle,
        media_items=tuple(media),
        engagement={},
        collection_backend=backend_name,
        backend_version=backend_version,
        content_hash=stable_content_hash(
            original_text, [item.original_media_url for item in media]
        ),
        discovered_at=utc_now(),
    )


class ThreadsPublicProfileAdapter:
    backend_name = "threads_public_playwright"
    backend_version = "public-html-v1"

    def __init__(self, html_loader: Callable[[str], str] | None = None):
        self._html_loader = html_loader

    def _load(self, url: str) -> str:
        if self._html_loader:
            return self._html_loader(url)
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise BackendFailure("playwright_not_installed") from exc
        try:
            with sync_playwright() as browser_api:
                browser = browser_api.chromium.launch(headless=True)
                context = browser.new_context()  # No cookies, storage state or shared profile.
                page = context.new_page()
                page.set_default_timeout(30_000)
                page.goto(url, wait_until="domcontentloaded")
                content = page.content()
                context.close()
                browser.close()
                return content
        except Exception as exc:
            raise BackendFailure(f"threads_public_page_failed:{type(exc).__name__}") from exc

    def acquire_post(
        self,
        source: dict[str, Any],
        post_url: str,
    ) -> NormalizedSourcePost:
        """Resolve one exact public post without traversing another profile."""
        canonical_post = canonical_url(post_url)
        expected_handle = _profile_handle(str(source.get("source_url") or ""))
        if "/post/" not in canonical_post:
            raise BackendFailure("threads_individual_post_url_required")
        if expected_handle and _post_handle(canonical_post) != expected_handle:
            raise BackendFailure("threads_post_author_mismatch")
        page_html = self._load(canonical_post)
        if "Barcelona404ErrorRoot" in page_html:
            raise BackendFailure("threads_post_application_404")
        post = parse_public_post_html(
            source,
            canonical_post,
            page_html,
            backend_name=self.backend_name,
            backend_version=self.backend_version,
        )
        if post.canonical_post_url != canonical_post:
            raise BackendFailure("threads_post_parent_mismatch")
        return post

    def acquire(
        self,
        source: dict[str, Any],
        *,
        limit: int,
    ) -> list[NormalizedSourcePost]:
        profile_url = canonical_url(str(source.get("source_url") or ""))

        if not profile_url.startswith("https://www.threads.com/@"):
            raise BackendFailure("threads_profile_url_required")

        try:
            start_position = max(
                1,
                int(
                    source.get(
                        "_discovery_start_position",
                        1,
                    )
                ),
            )
        except (TypeError, ValueError):
            start_position = 1

        bounded = max(
            1,
            int(limit),
        )

        requested = start_position - 1 + bounded

        profile_html = self._load(profile_url)

        if "Barcelona404ErrorRoot" in profile_html:
            handle = _profile_handle(profile_url)
            raise BackendFailure(f"threads_profile_application_404:{handle}")

        discovered_urls = extract_profile_post_urls(
            profile_html,
            profile_url,
            limit=requested,
        )

        post_urls = discovered_urls[start_position - 1 : start_position - 1 + bounded]

        if not post_urls:
            raise BackendFailure("threads_profile_post_links_unavailable")

        posts = []

        for post_url in post_urls:
            try:
                posts.append(self.acquire_post(source, post_url))
            except BackendFailure:
                continue

        if not posts:
            raise BackendFailure("threads_post_detail_unavailable")

        return posts

    def discover_profile(
        self, source: dict[str, Any], *, limit: int
    ) -> ProviderResult[list[NormalizedSourcePost]]:
        try:
            posts = self.acquire(source, limit=limit)
            return ProviderResult(self.backend_name, self.backend_version, "PASS", data=posts)
        except Exception as exc:
            return ProviderResult(
                self.backend_name,
                self.backend_version,
                "FAILED",
                reason=str(exc) or f"{type(exc).__name__}:threads_profile_discovery_failed",
                retryable=True,
            )


class ThreadsPublicHttpAdapter(ThreadsPublicProfileAdapter):
    """Lightweight fallback for public pages when Chromium is unavailable."""

    backend_name = "threads_public_http"
    backend_version = "public-http-v1"

    def _load(self, url: str) -> str:
        if self._html_loader:
            return self._html_loader(url)
        try:
            from urllib.request import Request, urlopen

            request = Request(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 Chrome/126 Safari/537.36"
                    ),
                    "Accept-Language": "ja,en-US;q=0.8,en;q=0.6",
                },
            )
            with urlopen(request, timeout=20) as response:
                if response.status != 200:
                    raise BackendFailure(f"threads_http_status:{response.status}")
                return response.read(2_000_000).decode("utf-8", errors="replace")
        except BackendFailure:
            raise
        except Exception as exc:
            raise BackendFailure(f"threads_public_http_failed:{type(exc).__name__}") from exc


class ThreadsPublicScreenAdapter(ThreadsPublicProfileAdapter):
    """Bounded rendered-screen fallback for public Threads profile discovery.

    It uses the same cookie-free Playwright dependency as the existing public
    adapter, but reads visible post anchors after a short, bounded render and
    scroll sequence.  There is no login, storage state, stealth layer, proxy,
    private endpoint, or CAPTCHA handling.
    """

    backend_name = "threads_public_screen"
    backend_version = "public-screen-v1"

    def __init__(
        self,
        html_loader: Callable[[str], str] | None = None,
        href_loader: Callable[[str, int], list[str]] | None = None,
    ):
        super().__init__(html_loader=html_loader)
        self._href_loader = href_loader

    def _visible_hrefs(self, profile_url: str, *, limit: int) -> list[str]:
        if self._href_loader:
            return self._href_loader(profile_url, limit)
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise BackendFailure("playwright_not_installed") from exc
        try:
            with sync_playwright() as browser_api:
                browser = browser_api.chromium.launch(headless=True)
                context = browser.new_context()
                page = context.new_page()
                page.set_default_timeout(30_000)
                page.goto(profile_url, wait_until="domcontentloaded")
                page.wait_for_timeout(1_500)
                hrefs: list[str] = []
                for _ in range(bounded_profile_scroll_attempts(limit)):
                    visible = page.locator("a[href*='/post/']").evaluate_all(
                        "elements => elements.map(element => element.getAttribute('href') || '')"
                    )
                    hrefs.extend(str(value) for value in visible)
                    if len(extract_profile_post_urls_from_hrefs(hrefs, profile_url, limit=limit)) >= limit:
                        break
                    page.mouse.wheel(0, 900)
                    page.wait_for_timeout(700)
                context.close()
                browser.close()
                return hrefs
        except BackendFailure:
            raise
        except Exception as exc:
            raise BackendFailure(f"threads_public_screen_failed:{type(exc).__name__}") from exc

    def acquire(
        self, source: dict[str, Any], *, limit: int
    ) -> list[NormalizedSourcePost]:
        profile_url = canonical_url(str(source.get("source_url") or ""))
        if not profile_url.startswith("https://www.threads.com/@"):
            raise BackendFailure("threads_profile_url_required")
        try:
            start_position = max(1, int(source.get("_discovery_start_position", 1)))
        except (TypeError, ValueError):
            start_position = 1
        bounded = max(1, int(limit))
        requested = start_position - 1 + bounded
        urls = extract_profile_post_urls_from_hrefs(
            self._visible_hrefs(profile_url, limit=requested), profile_url, limit=requested
        )
        post_urls = urls[start_position - 1 : start_position - 1 + bounded]
        if not post_urls:
            raise BackendFailure("threads_visible_post_links_unavailable")
        posts: list[NormalizedSourcePost] = []
        for post_url in post_urls:
            try:
                posts.append(
                    parse_public_post_html(
                        source,
                        post_url,
                        self._load(post_url),
                        backend_name=self.backend_name,
                        backend_version=self.backend_version,
                    )
                )
            except BackendFailure:
                continue
        if not posts:
            raise BackendFailure("threads_visible_post_detail_unavailable")
        return posts


class ThreadsBrowserSessionAdapter:
    """Bounded rendered-DOM acquisition using an optional browser session.

    This is the production fallback for public Threads pages that render only
    login boilerplate. Session material is supplied at runtime, never logged or
    persisted by this adapter. Every media child is read from the same rendered
    individual-post root as its caption.
    """

    backend_name = "threads_browser_session"
    backend_version = "rendered-dom-v1"

    def __init__(
        self,
        render_loader: Callable[[dict[str, Any], int], list[dict[str, Any]]] | None = None,
    ):
        self._render_loader = render_loader

    @staticmethod
    def _storage_state() -> dict[str, Any] | str:
        path = os.environ.get("THREADS_BROWSER_STORAGE_STATE_PATH", "").strip()
        if path:
            return path
        encoded = os.environ.get("THREADS_BROWSER_STORAGE_STATE_B64", "").strip()
        if not encoded:
            raise BackendFailure("threads_browser_session_not_configured")
        try:
            value = json.loads(base64.b64decode(encoded).decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BackendFailure("threads_browser_session_invalid") from exc
        if not isinstance(value, dict):
            raise BackendFailure("threads_browser_session_invalid")
        return value

    @staticmethod
    def _rendered_post(page: Any, post_url: str) -> dict[str, Any]:
        external = external_post_id(post_url)
        roots = page.locator("article")
        root = None
        for index in range(roots.count()):
            candidate = roots.nth(index)
            hrefs = candidate.locator("a[href*='/post/']").evaluate_all(
                "els => els.map(el => el.href || el.getAttribute('href') || '')"
            )
            if any(external_post_id(str(href)) == external for href in hrefs):
                root = candidate
                break
        if root is None:
            root = page.locator("main").first
        payload = root.evaluate(
            """root => {
              const visible = el => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
              };
              const textCandidates = [...root.querySelectorAll("div[dir='auto'], span[dir='auto']")]
                .filter(visible).map(el => (el.innerText || el.textContent || '').trim()).filter(Boolean);
              const media = [];
              for (const el of root.querySelectorAll('video, img')) {
                if (!visible(el)) continue;
                if (el.tagName.toLowerCase() === 'video') {
                  const source = el.currentSrc || el.src || el.querySelector('source')?.src || '';
                  if (source && source.startsWith('https://')) media.push({
                    media_type: 'video', url: source, poster: el.poster || '',
                    width: String(el.videoWidth || el.clientWidth || ''),
                    height: String(el.videoHeight || el.clientHeight || ''),
                    duration_seconds: Number.isFinite(el.duration) ? String(el.duration) : ''
                  });
                } else {
                  const source = el.currentSrc || el.src || '';
                  if (source && source.startsWith('https://')) media.push({
                    media_type: 'image', url: source,
                    width: String(el.naturalWidth || el.clientWidth || ''),
                    height: String(el.naturalHeight || el.clientHeight || '')
                  });
                }
              }
              return {
                text_candidates: textCandidates,
                media,
                published_at: root.querySelector('time')?.dateTime || '',
                author_name: ''
              };
            }"""
        )
        return dict(payload or {})

    def _render(self, source: dict[str, Any], limit: int) -> list[dict[str, Any]]:
        if self._render_loader:
            return self._render_loader(source, limit)
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise BackendFailure("playwright_not_installed") from exc
        profile_url = canonical_url(str(source.get("source_url") or ""))
        if not profile_url.startswith("https://www.threads.com/@"):
            raise BackendFailure("threads_profile_url_required")
        try:
            start_position = max(
                1,
                int(source.get("_discovery_start_position", 1)),
            )
        except (TypeError, ValueError):
            start_position = 1
        bounded = max(1, int(limit))
        requested = start_position - 1 + bounded
        try:
            with sync_playwright() as browser_api:
                browser = browser_api.chromium.launch(headless=True)
                context = browser.new_context(storage_state=self._storage_state())
                page = context.new_page()
                page.set_default_timeout(30_000)
                page.goto(profile_url, wait_until="domcontentloaded")
                page.wait_for_timeout(1_500)
                hrefs: list[str] = []
                for _ in range(bounded_profile_scroll_attempts(requested)):
                    hrefs.extend(
                        page.locator("a[href*='/post/']").evaluate_all(
                            "els => els.map(el => el.href || el.getAttribute('href') || '')"
                        )
                    )
                    urls = extract_profile_post_urls_from_hrefs(
                        hrefs, profile_url, limit=requested
                    )
                    if len(urls) >= requested:
                        break
                    page.mouse.wheel(0, 900)
                    page.wait_for_timeout(700)
                urls = extract_profile_post_urls_from_hrefs(
                    hrefs, profile_url, limit=requested
                )
                urls = urls[
                    start_position - 1 : start_position - 1 + bounded
                ]
                rendered: list[dict[str, Any]] = []
                for post_url in urls:
                    page.goto(post_url, wait_until="domcontentloaded")
                    page.wait_for_timeout(1_200)
                    rendered.append(
                        {"post_url": post_url, **self._rendered_post(page, post_url)}
                    )
                context.close()
                browser.close()
                return rendered
        except BackendFailure:
            raise
        except Exception as exc:
            raise BackendFailure(
                f"threads_browser_session_failed:{type(exc).__name__}"
            ) from exc

    def acquire(
        self, source: dict[str, Any], *, limit: int
    ) -> list[NormalizedSourcePost]:
        rendered = self._render(source, max(1, int(limit)))
        posts: list[NormalizedSourcePost] = []
        for item in rendered:
            post_url = canonical_url(str(item.get("post_url") or ""))
            if _post_handle(post_url) != _profile_handle(str(source.get("source_url") or "")):
                continue
            post = normalized_post_from_rendered(
                source,
                post_url,
                item,
                backend_name=self.backend_name,
                backend_version=self.backend_version,
            )
            if post.original_post_text or post.media_items:
                posts.append(post)
        if not posts:
            raise BackendFailure("threads_browser_session_no_post_data")
        return posts

    def discover_profile(
        self, source: dict[str, Any], *, limit: int
    ) -> ProviderResult[list[NormalizedSourcePost]]:
        try:
            return ProviderResult(
                self.backend_name,
                self.backend_version,
                "PASS",
                data=self.acquire(source, limit=limit),
            )
        except Exception as exc:
            return ProviderResult(
                self.backend_name,
                self.backend_version,
                "UNAVAILABLE",
                reason=f"{type(exc).__name__}:threads_browser_session_unavailable",
                retryable=True,
            )
