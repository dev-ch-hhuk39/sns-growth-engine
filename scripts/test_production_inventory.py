#!/usr/bin/env python3
import unittest
from datetime import datetime, timedelta

from production_inventory import (
    JST, coverage, due_slots, hashes, policy, scheduled_slots, select_evergreen,
    usable_evergreen_entries,
)


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 9, 12, tzinfo=JST)
        self.settings = {**policy(), "accounts": ["night_scout"]}
        self.queue = dict(queue_id="bank_q", account_id="night_scout", platform="threads", status="READY",
                          public_post_text="Example verified evergreen", validator_status="PASS",
                          internal_leak_status="PASS", account_fit_status="PASS")
        exact, normalized = hashes(self.queue["public_post_text"])
        self.entry = dict(fallback_id="bank", queue_id="bank_q", account_id="night_scout", status="VALIDATED",
                          text_hash=exact, normalized_hash=normalized, use_count=0)

    def select(self, *, queues=None, posted=None, check=lambda row: True):
        return select_evergreen([self.entry], queues if queues is not None else [self.queue], posted or [],
                               account="night_scout", now=self.now, runtime_check=check,
                               similar=lambda a, b: a == b, settings=self.settings)

    def test_ai_outage_bank_uses_same_canonical_identity(self):
        result = self.select()
        self.assertEqual(result["canonical_queue"], self.queue)
        self.assertEqual(result["canonical_queue"]["queue_id"], "bank_q")

    def test_cross_account_and_unapproved_blocked(self):
        for key, value in [("account_id", "beauty_account"), ("status", "WAITING_REVIEW"),
                           ("validator_status", "BLOCKED"), ("repost_prohibited", "true"),
                           ("media_asset_id", "image"), ("public_post_text", "modified")]:
            with self.subTest(key=key):
                self.assertIsNone(self.select(queues=[{**self.queue, key: value}]))

    def test_runtime_quality_blocked_never_ready(self):
        self.assertIsNone(self.select(check=lambda row: False))

    def test_usable_reserves_count_distinct_canonical_hashes_only(self):
        duplicate = {**self.entry, "fallback_id": "duplicate"}
        values = usable_evergreen_entries(
            [self.entry, duplicate], [self.queue], [], account="night_scout", now=self.now,
            runtime_check=lambda row: True, similar=lambda _a, _b: False, settings=self.settings,
        )
        self.assertEqual([row["fallback_id"] for row in values], ["bank"])

    def test_already_published_queue_not_recycled_after_cooldown(self):
        self.assertIsNone(self.select(posted=[dict(queue_id="bank_q", account_id="night_scout",
            posted_at=(self.now-timedelta(days=365)).isoformat(), posted_text=self.queue["public_post_text"])]))

    def test_recent_duplicate_and_normalization(self):
        self.assertIsNone(self.select(posted=[dict(account_id="night_scout", posted_text="Example verified evergreen",
                                                 posted_at=self.now.isoformat())]))
        self.assertEqual(hashes("Ａ b\n")[1], hashes("ab")[1])

    def test_future_and_invalid_cooldown(self):
        for value in [(self.now+timedelta(days=1)).isoformat(), "broken"]:
            self.entry["cooldown_until"] = value
            self.assertIsNone(self.select())

    def test_72_hours_include_day_25_and_beauty(self):
        end = self.now + timedelta(hours=72)
        for account, count in [("night_scout", 15), ("liver_manager", 15), ("beauty_account", 6)]:
            slots = scheduled_slots(account, self.now, end)
            self.assertEqual(len(slots), count)
            self.assertEqual(len({s["allocation_key"] for s in slots}), count)
        overnight = next(s for s in scheduled_slots("night_scout", self.now, end) if s["slot_id"] == "ns_2500_pdca")
        self.assertEqual(overnight["business_date_jst"], "2026-09-09")
        self.assertEqual(overnight["target_at"], "2026-09-10T01:00:00+09:00")

    def test_primary_alone_is_not_full_reserve_coverage(self):
        self.queue.update(slot_id="ns_1600_original", business_date_jst="2026-09-09")
        rows = coverage([self.queue], now=self.now, settings=self.settings, runtime_check=lambda row: True)
        selected = next(r for r in rows if r["ready_primary"])
        self.assertEqual(selected["missing"], 2)
        self.assertEqual(len(rows), 9)

    def test_bank_reserve_can_cover_text_slot_without_double_counting(self):
        self.queue.update(slot_id="ns_1600_original", business_date_jst="2026-09-09")
        reserve = {**self.queue, "queue_id": "reserve_q", "slot_id": "", "business_date_jst": "", "schedule_date_jst": "",
                   "public_post_text": "別の検証済み予備本文です。"}
        exact, normalized = hashes(reserve["public_post_text"])
        entry = {**self.entry, "queue_id": "reserve_q", "fallback_id": "reserve", "text_hash": exact, "normalized_hash": normalized}
        at = datetime(2026, 9, 9, 15, tzinfo=JST)
        rows = coverage([self.queue, reserve], now=at, settings=self.settings, runtime_check=lambda row: True,
                        evergreen_entries=[entry], posted=[], similar=lambda _a, _b: False)
        selected = next(row for row in rows if row["ready_primary"])
        self.assertEqual(selected["bank_reserve"], ["reserve_q"])
        self.assertEqual(selected["missing"], 1)

    def test_media_slot_does_not_consume_text_reserve(self):
        settings = {**policy(), "accounts": ["night_scout"], "text_candidates_per_slot": 1}
        reserve = {**self.queue, "queue_id": "reserve_media", "slot_id": "", "business_date_jst": "", "schedule_date_jst": "",
                   "public_post_text": "別の検証済み予備本文です。"}
        exact, normalized = hashes(reserve["public_post_text"])
        entry = {**self.entry, "queue_id": "reserve_media", "fallback_id": "media-reserve", "text_hash": exact, "normalized_hash": normalized}
        at = datetime(2026, 9, 9, 17, tzinfo=JST)
        rows = coverage([reserve], now=at, settings=settings, runtime_check=lambda row: True,
                        evergreen_entries=[entry], posted=[], similar=lambda _a, _b: False, include_media_fallback=True)
        media = next(row for row in rows if row["post_type"] == "direct_reference_media")
        self.assertEqual(media["expected_post_type"], "direct_reference_media")
        self.assertEqual(media["actual_coverage_type"], "")
        self.assertEqual(media["bank_reserve"], [])
        self.assertEqual(media["missing"], 1)

    def test_media_slot_rejects_preallocated_text_fallback(self):
        settings = {**policy(), "accounts": ["night_scout"], "text_candidates_per_slot": 1}
        allocated = {
            **self.queue,
            "queue_id": "allocated_text_fallback",
            "slot_id": "ns_1800_direct_media",
            "business_date_jst": "2026-09-09",
            "schedule_date_jst": "2026-09-09",
        }
        at = datetime(2026, 9, 9, 17, tzinfo=JST)
        rows = coverage(
            [allocated], now=at, settings=settings, runtime_check=lambda row: True,
            include_media_fallback=True,
        )
        media = next(row for row in rows if row["post_type"] == "direct_reference_media")
        self.assertEqual(media["ready_primary"], [])
        self.assertEqual(media["actual_coverage_type"], "")
        self.assertEqual(media["missing"], 1)

    def test_recently_used_media_does_not_count_as_ready_coverage(self):
        settings = {**policy(), "accounts": ["night_scout"], "text_candidates_per_slot": 1}
        slot = next(s for s in scheduled_slots("night_scout", self.now, self.now + timedelta(days=2))
                    if s["post_type"] in {"direct_reference_media", "approved_source_clip"})
        media = {**self.queue, "queue_id": "recent_media", "media_asset_id": "asset-recent",
                 "generation_mode": slot["post_type"], "slot_id": slot["slot_id"],
                 "business_date_jst": slot["business_date_jst"],
                 "schedule_date_jst": slot["business_date_jst"]}
        posted = [{"account_id": "night_scout", "status": "POSTED", "real_post": "true",
                   "media_asset_id": "asset-recent", "posted_at": (self.now - timedelta(hours=1)).isoformat()}]
        rows = coverage([media], now=self.now, settings=settings, runtime_check=lambda row: True,
                        posted=posted, include_media_fallback=True)
        result = next(r for r in rows if r["allocation_key"] == slot["allocation_key"])
        self.assertEqual(result["ready_primary"], [])
        self.assertEqual(result["missing"], 1)

    def test_duplicate_rows_cannot_inflate_coverage(self):
        self.queue.update(slot_id="ns_1600_original", business_date_jst="2026-09-09")
        rows = coverage([self.queue]*3, now=self.now, settings=self.settings, runtime_check=lambda row: True)
        self.assertEqual(sum(len(r["ready_primary"])+len(r["ready_reserve"]) for r in rows), 0)

    def test_delayed_reconcile_respects_terminal_and_ambiguous(self):
        now = datetime(2026, 9, 9, 16, 1, tzinfo=JST)
        terminal = dict(account_id="night_scout", slot_id="ns_1400_reference", schedule_date_jst="2026-09-09", status="POSTED")
        rows = due_slots("night_scout", now=now, slot_runs=[terminal], posted=[])
        self.assertEqual([r["slot_id"] for r in rows], ["ns_1600_original"])
        lease = {**terminal, "slot_id": "ns_1600_original", "status": "CLAIMED", "claim_status": "CLAIMED"}
        rows = due_slots("night_scout", now=now, slot_runs=[terminal, lease], posted=[])
        self.assertFalse(rows[0]["publishable"])

    def test_timezone_must_be_aware(self):
        with self.assertRaises(ValueError):
            scheduled_slots("night_scout", self.now.replace(tzinfo=None), self.now+timedelta(hours=72))

    def test_no_generation_import(self):
        import production_inventory
        from pathlib import Path
        code = Path(production_inventory.__file__).read_text()
        self.assertNotIn("GeminiHybridClient", code)
        self.assertNotIn("requests.post", code)


if __name__ == "__main__":
    unittest.main()
