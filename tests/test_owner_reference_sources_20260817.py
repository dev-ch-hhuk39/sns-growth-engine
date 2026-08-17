from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def _canonical(value: str) -> str:
    parsed = urlsplit(value)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return f"https://{host}{parsed.path.rstrip('/')}".lower()


def test_owner_reference_manifest_is_complete_deduped_and_registered() -> None:
    manifest = json.loads(
        (ROOT / "config/source_accounts/owner_reference_sources_20260817.json").read_text()
    )["accounts"]
    registry = json.loads(
        (ROOT / "config/source_accounts/default_sources.json").read_text()
    )["sources"]
    registered = {_canonical(row["source_url"]): row for row in registry if row.get("source_url")}
    expected_counts = {
        ("beauty_account", "x"): 6,
        ("beauty_account", "youtube"): 9,
        ("beauty_account", "tiktok"): 7,
        ("night_scout", "x"): 8,
        ("night_scout", "youtube"): 7,
        ("night_scout", "threads"): 8,
        ("liver_manager", "x"): 2,
        ("liver_manager", "youtube"): 2,
        ("liver_manager", "tiktok"): 4,
        ("liver_manager", "threads"): 1,
    }
    all_urls: list[str] = []
    for account_id, platforms in manifest.items():
        for platform, urls in platforms.items():
            assert len(urls) == expected_counts[(account_id, platform)]
            normalized = [_canonical(url) for url in urls]
            assert len(normalized) == len(set(normalized))
            for url in normalized:
                assert url in registered
                row = registered[url]
                assert account_id in (row.get("target_account_ids") or [])
                assert row.get("source_platform") == platform
            all_urls.extend(normalized)
    assert len(all_urls) == 54
    assert len(set(all_urls)) == 54


def test_owner_reference_manifest_does_not_broaden_media_or_beauty_safety() -> None:
    registry = json.loads(
        (ROOT / "config/source_accounts/default_sources.json").read_text()
    )["sources"]
    beauty = [row for row in registry if "beauty_account" in (row.get("target_account_ids") or [])]
    assert beauty
    assert all(row.get("target_account_id") != "beauty_future" for row in registry)
    assert all(row.get("active") is False and row.get("fetch_enabled") is False for row in beauty)
    assert all(row.get("can_reuse_media") is not True for row in beauty)
    assert all(row.get("media_pipeline_eligible") is not True for row in beauty)

    new_reference_only = {
        "src_ba_yt_owner_ega_channel",
        "src_ba_yt_owner_shushu_223",
        "src_ns_x_owner_nomination",
        "src_ns_yt_owner_amiru",
        "src_ns_yt_owner_lastcall",
        "src_lm_tt_owner_ikkyu",
    }
    rows = [row for row in registry if row.get("source_id") in new_reference_only]
    assert len(rows) == len(new_reference_only)
    assert all(row.get("rights_policy") == "reference_only" for row in rows)
    assert all(row.get("allow_download") is False for row in rows)
    assert all(row.get("allow_cut") is False for row in rows)
    assert all(row.get("allow_upload") is False for row in rows)
    assert all(row.get("media_pipeline_eligible") is False for row in rows)


def test_all_requested_threads_sources_are_bounded_autopilot_references() -> None:
    registry = json.loads(
        (ROOT / "config/source_accounts/default_sources.json").read_text()
    )["sources"]
    requested = {
        "https://threads.com/@kyaba_oohata",
        "https://threads.com/@kyaba_rui_scout",
        "https://threads.com/@chiikawan400",
        "https://threads.com/@kyaba_ryo",
        "https://threads.com/@mizuno9120",
        "https://threads.com/@kyabaraunzi",
        "https://threads.com/@levi_kyaba",
        "https://threads.com/@chiishunin_s",
        "https://threads.com/@me01_lsm",
    }
    rows = [
        row
        for row in registry
        if _canonical(row.get("source_url", "")) in requested
    ]
    assert len(rows) == 9
    assert all(row.get("active") is True for row in rows)
    assert all(row.get("fetch_enabled") is True for row in rows)
    assert all(row.get("manual_only") is False for row in rows)
    assert all(row.get("collection_method") == "threads_cli_public" for row in rows)
    assert all(row.get("allow_download") is False for row in rows)
