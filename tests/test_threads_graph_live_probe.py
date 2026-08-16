from __future__ import annotations

import importlib.util
import os
from pathlib import Path

from acquisition.contracts import ProviderResult
from acquisition.models import NormalizedSourcePost, stable_content_hash

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "probe_threads_graph_live.py"
SPEC = importlib.util.spec_from_file_location("probe_threads_graph_live", SCRIPT)
assert SPEC and SPEC.loader
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


def _post(source: dict, code: str) -> NormalizedSourcePost:
    handle = probe.threads_handle(source["source_url"])
    url = f"https://www.threads.com/@{handle}/post/{code}"
    return NormalizedSourcePost(
        source_post_id=f"sp_{source['source_id']}_{code}",
        source_id=source["source_id"],
        target_account_id=probe.account_for(source),
        platform="threads",
        profile_url=source["source_url"],
        canonical_post_url=url,
        external_post_id=code,
        original_post_text=f"public text {code}",
        published_at="2026-08-11T00:00:00+0000",
        author_handle=handle,
        collection_backend="threads_graph_public_discovery",
        backend_version="graph-public-v1",
        content_hash=stable_content_hash(code, []),
        discovered_at="2026-08-11T00:00:00+00:00",
        detail_status="PASS",
    )


class FakeGraph:
    def discover_profile(self, source: dict, *, limit: int):
        assert 1 <= limit <= 5
        return ProviderResult("graph", "v1", "PASS", data=[_post(source, source["source_id"][-6:])])

    def search_posts(self, source: dict, query: str, *, limit: int):
        return ProviderResult("graph", "v1", "PASS", data=[_post(source, "keyword1")])


class FakeOEmbed:
    def fetch_url(self, source: dict, post_url: str):
        return ProviderResult("oembed", "v1", "PASS", data=_post(source, post_url.rsplit("/", 1)[-1]))


def test_missing_token_returns_setup_without_network(monkeypatch):
    monkeypatch.delenv(probe.DISCOVERY_TOKEN_ENV, raising=False)
    result = probe.run_probe(account_id="all", max_posts=5)
    assert result["status"] == "BLOCKED"
    assert result["THREADS_AUTH_SETUP_REQUIRED"] is True
    assert result["source_results"] == []
    assert result["production_writes"] is False
    assert result["browser_or_cookie_access"] is False
    assert "<THREADS_ACCESS_TOKEN>" in "\n".join(result["USER_META_SETUP_CHECKLIST"])


def test_registered_priority_sources_complete_bounded_proof(monkeypatch):
    monkeypatch.setenv(probe.DISCOVERY_TOKEN_ENV, "fixture-only")
    result = probe.run_probe(
        account_id="all",
        max_posts=99,
        keyword="配信",
        graph=FakeGraph(),
        oembed=FakeOEmbed(),
    )
    assert result["status"] == "PASS"
    assert result["PLATFORM_DISCOVERY_LIVE_EVIDENCE_COMPLETE"] is True
    assert [row["source_id"] for row in result["source_results"]] == list(probe.PRIORITY_SOURCE_IDS)
    assert all(row["oembed_crosscheck"] == "PASS" for row in result["source_results"])
    assert result["keyword_search"]["normalized_count"] == 1
    assert result["production_writes"] is False
    assert os.environ[probe.DISCOVERY_TOKEN_ENV] not in str(result)


def test_runtime_contract_requires_only_discovery_scopes():
    contract = probe.runtime_contract()
    assert contract["required_scopes"] == ["threads_basic", "threads_profile_discovery"]
    assert contract["optional_scopes"] == ["threads_keyword_search"]
    assert contract["env_app_id_name"] is None
    assert contract["env_app_secret_name"] is None
