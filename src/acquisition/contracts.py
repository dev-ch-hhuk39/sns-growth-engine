"""Capability contracts shared by every source and publishing provider.

Providers return :class:`ProviderResult` instead of raising implementation
specific exceptions across orchestration boundaries.  The result deliberately
contains only redacted operational metadata; source cookies and credentials are
never part of this contract.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, Protocol, TypeVar, runtime_checkable

from .models import SourceMediaItem, SourcePostBundle

T = TypeVar("T")
PROVIDER_STATUSES = {"PASS", "PARTIAL", "UNAVAILABLE", "BLOCKED", "FAILED"}


@dataclass(frozen=True)
class ProviderResult(Generic[T]):
    provider_name: str
    provider_version: str
    status: str
    data: T | None = None
    reason: str = ""
    retryable: bool = False
    duration_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in PROVIDER_STATUSES:
            raise ValueError(f"unsupported_provider_status:{self.status}")
        forbidden = {"token", "cookie", "authorization", "storage_state", "secret", "password"}
        leaked = forbidden.intersection(key.lower() for key in self.metadata)
        if leaked:
            raise ValueError("provider_metadata_contains_sensitive_keys")

    @property
    def ok(self) -> bool:
        return self.status in {"PASS", "PARTIAL"}


@runtime_checkable
class ProfileDiscoveryProvider(Protocol):
    provider_name: str
    provider_version: str

    def discover_profile(self, source: dict[str, Any], *, limit: int) -> ProviderResult[list[SourcePostBundle]]: ...


@runtime_checkable
class PostDetailProvider(Protocol):
    provider_name: str
    provider_version: str

    def fetch_post_detail(self, post: SourcePostBundle) -> ProviderResult[SourcePostBundle]: ...


@runtime_checkable
class MediaResolverProvider(Protocol):
    provider_name: str
    provider_version: str

    def resolve_media(self, post: SourcePostBundle) -> ProviderResult[list[SourceMediaItem]]: ...


@runtime_checkable
class CommentProvider(Protocol):
    provider_name: str
    provider_version: str

    def fetch_comments(self, post: SourcePostBundle, *, limit: int) -> ProviderResult[list[dict[str, Any]]]: ...


@runtime_checkable
class TranscriptProvider(Protocol):
    provider_name: str
    provider_version: str

    def fetch_transcript(self, post: SourcePostBundle) -> ProviderResult[dict[str, Any]]: ...


@runtime_checkable
class WebEnrichmentProvider(Protocol):
    provider_name: str
    provider_version: str

    def enrich(self, post: SourcePostBundle) -> ProviderResult[SourcePostBundle]: ...


@runtime_checkable
class ContentUnderstandingProvider(Protocol):
    provider_name: str
    provider_version: str

    def understand(self, post: SourcePostBundle) -> ProviderResult[dict[str, Any]]: ...


@runtime_checkable
class CaptionGenerationProvider(Protocol):
    provider_name: str
    provider_version: str

    def generate_caption(
        self,
        post: SourcePostBundle,
        understanding: dict[str, Any],
        *,
        account_id: str,
        recent_posts: list[str],
    ) -> ProviderResult[dict[str, Any]]: ...


@runtime_checkable
class SemanticAlignmentProvider(Protocol):
    provider_name: str
    provider_version: str

    def evaluate(
        self,
        *,
        source_text: str,
        public_post_text: str,
        main_claims: list[str],
        claim_support: list[dict[str, str]],
        recent_posts: list[str],
    ) -> ProviderResult[dict[str, Any]]: ...


@runtime_checkable
class MediaStorageProvider(Protocol):
    provider_name: str
    provider_version: str

    def store(self, media: SourceMediaItem, *, account_id: str) -> ProviderResult[dict[str, Any]]: ...


@runtime_checkable
class PublishingProvider(Protocol):
    provider_name: str
    provider_version: str

    def publish(self, plan: dict[str, Any]) -> ProviderResult[dict[str, Any]]: ...
