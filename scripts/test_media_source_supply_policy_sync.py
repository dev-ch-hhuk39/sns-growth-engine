#!/usr/bin/env python3
"""Local policy synchronization never substitutes for live ledger authorization."""
from __future__ import annotations

import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from generation.media_platform_policy import (  # noqa: E402
    can_attempt_physical_media,
    physical_media_provider,
)
from generation.video_source_acquirer import (  # noqa: E402
    is_download_authorized,
    tiktok_registered_author_matches,
)
from reference.source_registry import load_registry  # noqa: E402

TIKTOK = {
    "src_lm_tt_user_001": "@user5597696107300",
    "src_lm_tt_user_002": "@me02_lsm",
    "src_lm_tt_user_003": "@uare.inc",
}
EXISTING_YOUTUBE = {
    "src_lm_yt_user_001", "src_lm_yt_cand_001",
    *(f"src_ns_yt_cand_{index:03d}" for index in range(1, 10)),
}


def config(name):
    return json.loads((ROOT / "config" / name).read_text(encoding="utf-8"))


class MediaSourceSupplyPolicySyncTests(unittest.TestCase):
    def test_exact_allowlist_and_owner_identity(self):
        growth = config("media_growth_engine.json")
        allowed = growth["allowed_source_ids"]
        self.assertEqual(set(allowed), EXISTING_YOUTUBE | set(TIKTOK))
        self.assertEqual(len(allowed), len(set(allowed)))
        owner = {s["source_id"]: s for s in config("owner_source_permissions_20260811.json")["sources"]}
        youtube = config("youtube_source_permissions_20260811.json")["sources"]
        self.assertEqual({s["source_id"] for s in youtube}, {"src_ns_yt_cand_006", "src_lm_yt_cand_001"})
        policy = config("registered_source_rights_policy.json")
        manifest = json.loads((ROOT / policy["canonical_manifest"]).read_text(encoding="utf-8"))
        registry = {s["source_id"]: s for s in load_registry()}
        modes = config("media_source_usage_modes.json")["source_modes"]
        for source_id, handle in TIKTOK.items():
            with self.subTest(source_id=source_id):
                attestation, source = owner[source_id], registry[source_id]
                url = f"https://www.tiktok.com/{handle}"
                self.assertEqual(attestation["source_handle"], handle)
                self.assertEqual(attestation["account_id"], "liver_manager")
                self.assertEqual(attestation["platform"], "tiktok")
                self.assertIn(url, manifest["accounts"]["liver_manager"]["tiktok"])
                self.assertEqual(source["source_handle"], handle)
                self.assertEqual(source["canonical_url"], url)
                self.assertEqual(source["source_url"], url)
                self.assertEqual(source["target_account_id"], "liver_manager")
                self.assertEqual(source["registered_owner_scope_id"], policy["decision_id"])
                self.assertEqual(modes[source_id], "direct_and_clip")
                self.assertTrue(tiktok_registered_author_matches(f"{url}/video/123", source))
                self.assertFalse(tiktok_registered_author_matches("https://www.tiktok.com/@other/video/123", source))
        self.assertTrue(can_attempt_physical_media("tiktok"))
        self.assertEqual(physical_media_provider("tiktok"), "public_embed_direct_http")
        self.assertEqual(growth["physical_media_provider_by_platform"]["tiktok"], physical_media_provider("tiktok"))
        self.assertIn("tiktok", growth["physical_media_source_platforms"])
        self.assertNotIn("tiktok", growth["deferred_physical_media_source_platforms"])

    def test_direct_targets_match_canonical_minimum(self):
        inventory = config("production_inventory.json")
        targets = config("media_growth_engine.json")["asset_inventory_targets"]
        self.assertEqual(inventory["minimum_media_per_route"], 3)
        for account in inventory["accounts"]:
            self.assertEqual(targets[account]["direct_reference_media"], inventory["minimum_media_per_route"])
        self.assertEqual(targets["beauty_account"]["approved_source_clip"], 1)

    def test_allowlisted_owner_sources_still_require_latest_active_ledger(self):
        registry = {s["source_id"]: s for s in load_registry()}
        for source_id, handle in TIKTOK.items():
            source = registry[source_id]
            # Synthetic ledger evidence only; no seed, grant, or production write.
            row = {
                "source_id": source_id, "source_handle": handle,
                "account_id": "liver_manager", "rights_status": "approved_creator_clip",
                "permission_status": "approved", "revoked": False,
                "allow_download": True, "allow_cut": True,
                "evidence_type": "owner_attestation", "evidence_reference": "local-test-only",
                "approved_by": "fixture", "approved_at": "2026-08-11T00:00:00+09:00",
                "updated_at": "2026-08-11T00:00:00+09:00",
            }
            before = deepcopy(source)
            self.assertFalse(is_download_authorized(source, account_id="liver_manager"))
            self.assertFalse(is_download_authorized(source, [], account_id="liver_manager"))
            self.assertTrue(is_download_authorized(source, [row], account_id="liver_manager"))
            for field, value in (
                ("revoked", True), ("allow_cut", False), ("allow_download", False),
                ("permission_status", "pending"), ("rights_status", "reference_only"),
                ("account_id", "night_scout"), ("source_handle", "@other"),
                ("source_handle", ""), ("evidence_reference", ""),
                ("expires_at", "2000-01-01T00:00:00+00:00"),
            ):
                with self.subTest(source_id=source_id, field=field):
                    denied = {**row, field: value, "updated_at": "2026-08-12T00:00:00+09:00"}
                    for rows in ([row, denied], [denied, row]):
                        snapshot = deepcopy(rows)
                        self.assertFalse(is_download_authorized(source, rows, account_id="liver_manager"))
                        self.assertEqual(rows, snapshot)
            for flag in ("allow_download", "allow_cut"):
                missing = {key: value for key, value in row.items() if key != flag}
                self.assertFalse(is_download_authorized(source, [missing], account_id="liver_manager"))
            self.assertFalse(is_download_authorized(source, [{**row, "source_id": "unrelated"}], account_id="liver_manager"))
            self.assertEqual(source, before)


if __name__ == "__main__":
    unittest.main()
