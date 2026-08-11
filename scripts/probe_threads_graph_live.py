#!/usr/bin/env python3
"""Bounded read-only proof for official Threads public discovery.

The probe reads only registered Threads sources. It never writes Sheets,
uploads media, publishes a post, or reads browser/session state. A missing
runtime token returns the exact setup contract without attempting the network.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acquisition.threads_official import (  # noqa: E402
    DISCOVERY_OPTIONAL_SCOPES,
    DISCOVERY_REQUIRED_SCOPES,
    DISCOVERY_TOKEN_ENV,
    GRAPH_API_VERSION,
    GRAPH_ROOT,
    ThreadsGraphPublicDiscoveryAdapter,
    ThreadsOEmbedDetailAdapter,
    threads_handle,
)

PRIORITY_SOURCE_IDS = (
    "src_ns_threads_user_chiishunin_s",
    "src_lm_threads_user_me01_lsm",
)
ACCOUNT_ORDER = ("night_scout", "liver_manager")


def truthy(value: Any) -> bool:
    return value is True or str(value or "").strip().lower() in {"1", "true", "yes"}


def account_for(source: dict[str, Any]) -> str:
    targets = source.get("target_account_ids") or [source.get("target_account_id")]
    return str(targets[0] if targets else "")


def registered_sources(account_id: str) -> list[dict[str, Any]]:
    payload = json.loads(
        (ROOT / "config/source_accounts/default_sources.json").read_text(encoding="utf-8")
    )
    priority = {source_id: index for index, source_id in enumerate(PRIORITY_SOURCE_IDS)}
    rows = [
        dict(row)
        for row in payload.get("sources", [])
        if str(row.get("source_platform") or row.get("platform") or "").lower() == "threads"
        and truthy(row.get("active"))
        and truthy(row.get("fetch_enabled"))
        and account_for(row) in ACCOUNT_ORDER
        and account_id in {"all", account_for(row)}
        and threads_handle(str(row.get("source_url") or ""))
    ]
    return sorted(
        rows,
        key=lambda row: (
            ACCOUNT_ORDER.index(account_for(row)),
            priority.get(str(row.get("source_id") or ""), len(priority)),
            str(row.get("source_id") or ""),
        ),
    )


def runtime_contract() -> dict[str, Any]:
    return {
        "env_token_name": DISCOVERY_TOKEN_ENV,
        "env_app_id_name": None,
        "env_app_secret_name": None,
        "required_scopes": list(DISCOVERY_REQUIRED_SCOPES),
        "optional_scopes": list(DISCOVERY_OPTIONAL_SCOPES),
        "graph_host": GRAPH_ROOT,
        "graph_version": GRAPH_API_VERSION,
        "token_refresh_model": (
            "Exchange the short-lived Threads user token for a 60-day long-lived token; "
            "refresh the unexpired long-lived token with th_refresh_token. App ID/secret "
            "are OAuth provisioning inputs, not live acquisition runtime variables."
        ),
        "advanced_access_or_review_requirement": (
            "Required for public-profile discovery outside app roles/testers; "
            "threads_keyword_search requires its own optional permission."
        ),
    }


def setup_checklist() -> list[str]:
    return [
        "Create a dedicated Meta app with the Threads use case; do not use a personal browser session.",
        "Authorize threads_basic and threads_profile_discovery for the dedicated app.",
        "Request Advanced Access/App Review before discovering public profiles outside app roles/testers.",
        "Optionally authorize threads_keyword_search; absence does not block profile discovery.",
        "Exchange the short-lived user token for a long-lived token and refresh it before expiry.",
        f"Provide the token only at runtime as {DISCOVERY_TOKEN_ENV}; never commit it.",
        "Run: python3 scripts/acquisition_doctor.py --json",
        (
            "Run: THREADS_DISCOVERY_ACCESS_TOKEN='<THREADS_ACCESS_TOKEN>' "
            "python3 scripts/probe_threads_graph_live.py --account-id all --max-posts 5 "
            "--output /private/tmp/threads-graph-live-v22.json"
        ),
    ]


def post_summary(post: Any) -> dict[str, Any]:
    media = [asdict(item) for item in post.media_items]
    return {
        "source_post_id": post.source_post_id,
        "source_id": post.source_id,
        "account_id": post.target_account_id,
        "id": post.external_post_id,
        "username": post.author_handle,
        "permalink": post.canonical_post_url,
        "text": post.original_post_text,
        "timestamp": post.published_at,
        "shortcode": post.canonical_post_url.rsplit("/", 1)[-1],
        "media_type": post.media_type or "TEXT_POST",
        "media_url": media[0]["original_media_url"] if media else "",
        "thumbnail_url": media[0]["thumbnail_url"] if media else "",
        "media_items": media,
        "content_hash": post.content_hash,
        "collection_backend": post.collection_backend,
        "backend_version": post.backend_version,
        "quote_or_repost": post.detail_status == "PARTIAL",
    }


def run_probe(
    *,
    account_id: str,
    max_posts: int,
    keyword: str = "",
    graph: ThreadsGraphPublicDiscoveryAdapter | None = None,
    oembed: ThreadsOEmbedDetailAdapter | None = None,
) -> dict[str, Any]:
    sources = registered_sources(account_id)
    contract = runtime_contract()
    if not os.environ.get(DISCOVERY_TOKEN_ENV, "").strip() and graph is None:
        return {
            "status": "BLOCKED",
            "THREADS_AUTH_SETUP_REQUIRED": True,
            "THREADS_RUNTIME_AUTH_CONTRACT": contract,
            "USER_META_SETUP_CHECKLIST": setup_checklist(),
            "selected_source_ids": [str(row.get("source_id") or "") for row in sources],
            "source_results": [],
            "keyword_search": {"status": "NOT_RUN_AUTH_REQUIRED"},
            "production_writes": False,
            "browser_or_cookie_access": False,
        }

    graph = graph or ThreadsGraphPublicDiscoveryAdapter()
    oembed = oembed or ThreadsOEmbedDetailAdapter()
    results: list[dict[str, Any]] = []
    selected_accounts: set[str] = set()
    for source in sources:
        source_account = account_for(source)
        if source_account in selected_accounts:
            continue
        discovery = graph.discover_profile(source, limit=min(5, max(1, max_posts)))
        row: dict[str, Any] = {
            "source_id": source.get("source_id"),
            "account_id": source_account,
            "registered_handle": threads_handle(str(source.get("source_url") or "")),
            "profile_lookup": discovery.status,
            "profile_posts": len(discovery.data or []),
            "reason": discovery.reason,
            "chosen_post": None,
            "oembed_crosscheck": "NOT_RUN",
        }
        original_posts = [
            post
            for post in (discovery.data or [])
            if post.detail_status != "PARTIAL"
            and post.author_handle == row["registered_handle"]
            and post.canonical_post_url.startswith(
                f"https://www.threads.com/@{row['registered_handle']}/post/"
            )
        ]
        if original_posts:
            chosen = original_posts[0]
            detail = oembed.fetch_url(source, chosen.canonical_post_url)
            row["chosen_post"] = post_summary(chosen)
            row["oembed_crosscheck"] = (
                "PASS"
                if detail.ok
                and detail.data is not None
                and detail.data.canonical_post_url == chosen.canonical_post_url
                and detail.data.author_handle == chosen.author_handle
                else "FAIL"
            )
            selected_accounts.add(source_account)
        results.append(row)

    keyword_result: dict[str, Any] = {"status": "NOT_REQUESTED"}
    if keyword.strip() and sources:
        found = graph.search_posts(sources[0], keyword.strip(), limit=min(5, max_posts))
        if found.status in {"BLOCKED", "FAILED"} and (
            "AUTH" in found.reason.upper() or "PERMISSION" in found.reason.upper()
        ):
            keyword_result = {
                "status": "OPTIONAL_AUTH_SCOPE_MISSING",
                "permission": DISCOVERY_OPTIONAL_SCOPES[0],
                "normalized_count": 0,
            }
        else:
            keyword_result = {
                "status": found.status,
                "permission": DISCOVERY_OPTIONAL_SCOPES[0],
                "normalized_count": len(found.data or []),
                "results": [post_summary(post) for post in (found.data or [])],
                "reason": found.reason,
            }

    expected_accounts = set(ACCOUNT_ORDER if account_id == "all" else (account_id,))
    complete = expected_accounts == selected_accounts and all(
        any(
            row["account_id"] == expected
            and row["chosen_post"]
            and row["oembed_crosscheck"] == "PASS"
            for row in results
        )
        for expected in expected_accounts
    )
    return {
        "status": "PASS" if complete else "BLOCKED",
        "THREADS_AUTH_SETUP_REQUIRED": False,
        "THREADS_RUNTIME_AUTH_CONTRACT": contract,
        "USER_META_SETUP_CHECKLIST": [],
        "selected_source_ids": [str(row.get("source_id") or "") for row in sources],
        "source_results": results,
        "keyword_search": keyword_result,
        "PLATFORM_DISCOVERY_LIVE_EVIDENCE_COMPLETE": complete,
        "PLATFORM_PHYSICAL_LIVE_EVIDENCE_COMPLETE": False,
        "physical_status": (
            "THREADS_DISCOVERY_LIVE_PASS_PHYSICAL_MEDIA_URL_UNAVAILABLE"
            if complete and not any(
                (row.get("chosen_post") or {}).get("media_url") for row in results
            )
            else "PHYSICAL_PERMISSION_GATED_PROOF_REQUIRED"
        ),
        "production_writes": False,
        "browser_or_cookie_access": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", choices=["all", *ACCOUNT_ORDER], default="all")
    parser.add_argument("--max-posts", type=int, default=5)
    parser.add_argument("--keyword", default="")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run_probe(
        account_id=args.account_id,
        max_posts=min(5, max(1, args.max_posts)),
        keyword=args.keyword,
    )
    encoded = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
