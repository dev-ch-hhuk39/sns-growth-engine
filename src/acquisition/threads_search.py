"""Bounded zero-auth Threads permalink candidate discovery.

Search results are never trusted as source posts. Every candidate must be an
exact registered-author permalink and pass official oEmbed detail validation.
"""
from __future__ import annotations

import html
import re
from typing import Callable
from urllib.parse import parse_qs, quote_plus, unquote, urlsplit
from urllib.request import Request, urlopen

from .contracts import ProviderResult
from .models import NormalizedSourcePost
from .threads_official import ThreadsOEmbedDetailAdapter, canonical_threads_post_url, threads_handle

SEARCH_ENDPOINT = "https://html.duckduckgo.com/html/"
_HREF = re.compile(r"href=[\"']([^\"']+)[\"']", re.I)


def _load_search(url: str) -> str:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 acquisition-bot/1.0"})
    with urlopen(request, timeout=20) as response:
        if response.status != 200:
            raise RuntimeError(f"search_http_status:{response.status}")
        return response.read(1_000_000).decode("utf-8", errors="replace")


def extract_search_candidates(page_html: str, expected_handle: str, *, limit: int) -> list[str]:
    bounded = min(5, max(1, int(limit)))
    expected = expected_handle.lower().lstrip("@")
    candidates: list[str] = []
    for raw in _HREF.findall(page_html):
        href = html.unescape(raw)
        query = parse_qs(urlsplit(href).query)
        if "uddg" in query:
            href = unquote(query["uddg"][0])
        candidate = canonical_threads_post_url(href)
        if not candidate or threads_handle(candidate) != expected:
            continue
        if candidate not in candidates:
            candidates.append(candidate)
        if len(candidates) >= bounded:
            break
    return candidates


class ThreadsSearchIndexAdapter:
    backend_name = "threads_search_index"
    backend_version = "bounded-search-v1"

    def __init__(
        self,
        search_loader: Callable[[str], str] | None = None,
        detail_adapter: ThreadsOEmbedDetailAdapter | None = None,
    ):
        self._search_loader = search_loader or _load_search
        self._detail = detail_adapter or ThreadsOEmbedDetailAdapter()

    def discover_profile(self, source: dict, *, limit: int) -> ProviderResult[list[NormalizedSourcePost]]:
        handle = threads_handle(str(source.get("source_url") or ""))
        if not handle:
            return ProviderResult(self.backend_name, self.backend_version, "BLOCKED", data=[], reason="threads_profile_handle_required")
        bounded = min(5, max(1, int(limit)))
        query = quote_plus(f"site:threads.com/@{handle}/post/ @{handle}")
        try:
            page = self._search_loader(f"{SEARCH_ENDPOINT}?q={query}")
            candidates = extract_search_candidates(page, handle, limit=bounded)
            posts: list[NormalizedSourcePost] = []
            rejected = 0
            for candidate in candidates:
                result = self._detail.fetch_url(source, candidate)
                if not result.ok or result.data is None or result.data.author_handle.lower().lstrip("@") != handle:
                    rejected += 1
                    continue
                posts.append(result.data)
            status = "PASS" if posts else "PARTIAL"
            return ProviderResult(
                self.backend_name,
                self.backend_version,
                status,
                data=posts,
                reason="" if posts else "NO_REVALIDATED_PERMALINKS",
                metadata={"candidate_count": len(candidates), "rejected_count": rejected, "bounded_limit": bounded},
            )
        except Exception as exc:
            return ProviderResult(self.backend_name, self.backend_version, "FAILED", data=[], reason=str(exc) or type(exc).__name__, retryable=True)
