from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acquisition.capability_registry import CapabilityRegistry  # noqa: E402
from acquisition.failures import FailureCategory, classify_failure, fallback_allowed  # noqa: E402
from acquisition.factory import build_router  # noqa: E402
from acquisition.router import AdapterRouter, BackendFailure, BackendRoute  # noqa: E402
from acquisition.twscrape_optional import TwscrapeOptionalAdapter  # noqa: E402


def test_active_profile_routes_are_capability_compatible_and_backend_only() -> None:
    registry = CapabilityRegistry.load()
    router = build_router()
    assert not registry.validate_routes(router.routes, registered=set(router.adapters))
    for route in router.routes.values():
        for backend_id in (route.primary, *route.fallbacks):
            backend = registry.get(backend_id)
            assert backend.production_selectable
            assert not backend.requires_browser
            assert not backend.requires_external_service


def test_browser_auth_and_opaque_candidates_are_not_production_selectable() -> None:
    registry = CapabilityRegistry.load()
    for backend_id in (
        "threads_hasya_userscript",
        "threads_zeeshan_playwright",
        "threads_vdite_playwright",
        "threads_galih_playwright",
        "twscrape",
        "f2_tiktok",
        "universal_downloader",
    ):
        assert not registry.get(backend_id).production_selectable


def test_unknown_or_capability_mismatched_backend_fails_closed() -> None:
    registry = CapabilityRegistry.load()
    with pytest.raises(ValueError, match="backend_not_in_capability_registry"):
        registry.get("missing")
    with pytest.raises(ValueError, match="backend_capability_mismatch"):
        registry.require_production_route("threads_public_http", "x.profile_posts")


def test_failure_taxonomy_never_falls_back_around_rights_or_provenance() -> None:
    assert classify_failure("x", "author_mismatch") == FailureCategory.AUTHOR_MISMATCH
    assert classify_failure("tiktok", "secondary user ID") == FailureCategory.POST_DISCOVERY_UNAVAILABLE
    assert classify_failure("threads", "http_status:429") == FailureCategory.RATE_LIMITED
    assert not fallback_allowed(FailureCategory.RIGHTS_BLOCKED)
    assert not fallback_allowed(FailureCategory.THIRD_PARTY_REPOST)
    assert fallback_allowed(FailureCategory.TOOL_NOT_INSTALLED)


def test_router_does_not_fallback_around_author_mismatch() -> None:
    class AuthorMismatch:
        def acquire(self, source, *, limit):
            raise BackendFailure("author_mismatch")

    class MustNotRun:
        def acquire(self, source, *, limit):
            raise AssertionError("rights fallback must not run")

    router = AdapterRouter(
        {"primary": AuthorMismatch(), "fallback": MustNotRun()},
        {"x.profile_posts": BackendRoute("x.profile_posts", "primary", ("fallback",))},
    )
    with pytest.raises(BackendFailure, match="non_fallback_failure:AUTHOR_MISMATCH"):
        router.route("x.profile_posts", {"platform": "x"}, limit=1)


def test_twscrape_optional_adapter_reports_auth_without_secret_values(monkeypatch) -> None:
    monkeypatch.setattr("acquisition.twscrape_optional.importlib.util.find_spec", lambda name: object())
    monkeypatch.delenv("TWSCRAPE_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("TWSCRAPE_CT0", raising=False)
    result = TwscrapeOptionalAdapter.capability_status()
    assert result.status == "BLOCKED"
    assert result.reason == "AUTH_REQUIRED:auth_token_and_ct0"
    assert result.data == {"installed": True, "auth_present": False, "active": False}
