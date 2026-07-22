#!/usr/bin/env python3
"""Shared checks for authoritative required source URLs.

These checks are intentionally local-only. They never fetch source URLs,
download media, write to Sheets, or call publisher APIs.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config/source_accounts/default_sources.json"
REQUIRED = ROOT / "config/source_accounts/required_source_urls.json"


def canonical_url(url: str) -> str:
    value = str(url or "").strip().split("?")[0].split("#")[0].rstrip("/")
    value = re.sub(r"^http://", "https://", value)
    value = re.sub(r"^https://www\.", "https://", value)
    return value.lower()


def url_handle(url: str) -> str:
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    if not parts:
        return ""
    first = parts[0]
    return first.lower() if first.startswith("@") else f"@{first.lower()}"


def load_sources() -> list[dict]:
    return json.loads(REGISTRY.read_text())["sources"]


def load_required() -> list[dict]:
    return json.loads(REQUIRED.read_text())["required_sources"]


def row_urls(row: dict) -> set[str]:
    return {
        canonical_url(row.get(key, ""))
        for key in ("source_url", "canonical_url", "post_url", "status_url")
        if str(row.get(key, "")).strip()
    }


def row_targets(row: dict) -> list[str]:
    return row.get("target_account_ids") or ([row.get("target_account_id")] if row.get("target_account_id") else [])


def row_categories(row: dict) -> set[str]:
    values: set[str] = set()
    category = row.get("source_category")
    if isinstance(category, list):
        values.update(str(v) for v in category)
    elif category:
        values.add(str(category))
    values.update(str(v) for v in (row.get("source_categories") or []))
    if row.get("category"):
        values.add(str(row["category"]))
    return values


def find_required_row(required: dict, sources: list[dict] | None = None) -> dict | None:
    sources = sources or load_sources()
    want_url = canonical_url(required["url"])
    want_handle = (required.get("author_handle") or url_handle(required["url"])).lower()
    want_platform = required["platform"]
    for row in sources:
        if row.get("source_platform") != want_platform:
            continue
        if want_url in row_urls(row):
            return row
    for row in sources:
        if row.get("source_platform") != want_platform:
            continue
        handles = {
            str(row.get("source_handle", "")).lower(),
            str(row.get("author_handle", "")).lower(),
            str(row.get("account_handle", "")).lower(),
        }
        if want_handle and want_handle in handles:
            return row
    return None


def assert_required_present() -> None:
    sources = load_sources()
    missing = [r["url"] for r in load_required() if find_required_row(r, sources) is None]
    assert not missing, f"missing required source URLs: {missing}"


def assert_required_threads() -> None:
    sources = load_sources()
    rows = [find_required_row(r, sources) for r in load_required() if r["platform"] == "threads"]
    assert len(rows) == 6 and all(rows), f"threads required rows missing: {rows}"
    for row in rows:
        assert row["source_platform"] == "threads", row.get("source_id")
        assert row_targets(row) == ["night_scout"], row.get("source_id")
        assert row.get("target_account_id") == "night_scout", row.get("source_id")
        assert row.get("active") is True, row.get("source_id")
        assert row.get("fetch_enabled") is False, row.get("source_id")
        assert row.get("manual_only") is True, row.get("source_id")
        assert row.get("source_track") == "night_scout_reference", row.get("source_id")


def assert_required_x_manual_only() -> None:
    sources = load_sources()
    rows = [find_required_row(r, sources) for r in load_required() if r["platform"] == "x"]
    assert len(rows) == 7 and all(rows), f"x required rows missing: {rows}"
    for row in rows:
        assert row["source_platform"] == "x", row.get("source_id")
        assert row_targets(row) == ["night_scout"], row.get("source_id")
        assert row.get("target_account_id") == "night_scout", row.get("source_id")
        assert row.get("active") is False, row.get("source_id")
        assert row.get("fetch_enabled") is False, row.get("source_id")
        assert row.get("allow_network_fetch") is False, row.get("source_id")
        assert row.get("manual_only") is True, row.get("source_id")
        assert row.get("source_track") == "x_manual_reference", row.get("source_id")
        assert row.get("rights_policy") == "reference_only", row.get("source_id")
        assert row.get("use_policy") == "REFERENCE_ONLY", row.get("source_id")
        assert row.get("can_reuse_media") is False, row.get("source_id")


def assert_canonical_matching() -> None:
    sources = load_sources()
    for req in load_required():
        row = find_required_row(req, sources)
        assert row is not None, req["url"]
        assert canonical_url(req["url"]) in row_urls(row), (req["url"], row.get("source_id"), row_urls(row))
    status_req = next(r for r in load_required() if r.get("source_type") == "post")
    status_row = find_required_row(status_req, sources)
    assert status_row is not None
    assert status_row.get("author_handle") == "@minatoku789"
    assert canonical_url(status_req["url"]) in row_urls(status_row)


def assert_no_fetch_enabled_required_sources() -> None:
    sources = load_sources()
    for req in load_required():
        row = find_required_row(req, sources)
        assert row is not None, req["url"]
        assert row.get("fetch_enabled") is False, row.get("source_id")
        assert row.get("allow_download") is False, row.get("source_id")
        assert row.get("allow_cut") is False, row.get("source_id")
        assert row.get("allow_upload") is False, row.get("source_id")


def assert_required_classification() -> None:
    for req in load_required():
        row = find_required_row(req)
        assert row is not None, req["url"]
        assert row.get("rights_policy") == "reference_only", row.get("source_id")
        assert row.get("use_policy") == "REFERENCE_ONLY", row.get("source_id")
        assert row.get("can_reuse_media") is False, row.get("source_id")
        cats = row_categories(row)
        if req["platform"] == "threads":
            assert {"night_work_scout", "cabaret_knowhow"} & cats, (row.get("source_id"), cats)
        if req["platform"] == "x":
            assert {"night_work_scout", "cabaret_knowhow", "nightlife_reference"} & cats, (row.get("source_id"), cats)


def run_checks(checks: list[tuple[str, callable]]) -> int:
    passed = failed = 0
    for name, check in checks:
        try:
            check()
            print(f"  PASS {name}")
            passed += 1
        except AssertionError as exc:
            print(f"  FAIL {name}: {exc}")
            failed += 1
    print(f"PASS: {passed} / FAIL: {failed}")
    return 0 if failed == 0 else 1
