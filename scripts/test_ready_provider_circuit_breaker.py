#!/usr/bin/env python3
"""No-network account-scope paid-provider circuit breaker contracts.

Every external Sheets, publishing, AI and bank write is replaced by mocks.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/"scripts"),str(ROOT/"src")]
import maintain_text_ready_inventory as m  # noqa: E402


class FakeSheetsClient:
    def __init__(self,*args,**kwargs):
        self.dry_run=kwargs.get("dry_run")
    def _ensure_tab(self,*args,**kwargs):
        pass


def fake_slot(index):
    return {"slot_id":f"ns_test_{index}",
            "business_date_jst":"2026-10-23",
            "post_type":"original_text",
            "target_jst":"16:00"}


class PaidCircuitBreakerTests(unittest.TestCase):
    def test_sanitized_codes(self):
        categories=(
            "AI_APPROVAL_BUDGET_EXHAUSTED",
            "GENERATION_PROCESS_TIMEOUT",
            "PROVIDER_TIMEOUT","PROVIDER_RATE_LIMITED",
            "PROVIDER_UNAVAILABLE","PROVIDER_CONFIGURATION_ERROR",
            "PROVIDER_CREDENTIALS_MISSING_OR_REJECTED",
        )
        for reason in categories:
            self.assertTrue(m.paid_generation_pause_required({"failure_category":reason}))
            self.assertTrue(m.paid_generation_pause_required({
                "attempts":[{"route":"primary","reason":reason}]}))
        for reason in ("QUALITY_EXHAUSTED","OWNER_REVIEW_REQUIRED",
                       "SHEETS_QUOTA_EXHAUSTED",""):
            self.assertFalse(m.paid_generation_pause_required({"failure_category":reason}))
        self.assertFalse(m.paid_generation_pause_required({}))
        self.assertFalse(m.paid_generation_pause_required({"attempts":None}))
        self.assertFalse(m.paid_generation_pause_required(None))

    def run_main_mocked(self, first):
        runs=[]
        def generate(account_id,slot,*,apply,required,offline_only=False):
            runs.append({"slot":slot["slot_id"],"offline":offline_only,"required":required})
            if len(runs)==1:
                return {"status":"QUALITY_EXHAUSTED",
                        "failure_category":first,
                        "attempts":[{"route":"primary","reason":first}],
                        "queue_ids":[]}
            return {"status":"QUALITY_EXHAUSTED",
                    "failure_category":"QUALITY_EXHAUSTED",
                    "attempts":[],"queue_ids":[]}
        buffer=io.StringIO()
        with patch.object(sys,"argv",["inventory","--account-id","night_scout",
                       "--apply","--confirm-ready-maintenance","--use-sheets",
                       "--horizon-hours","24"]), \
             patch.object(m,"get_config",return_value={"sheet_id":"fake","sa_dict":{}}), \
             patch.object(m,"SheetsClient",FakeSheetsClient), \
             patch.object(m,"read_records_safely",return_value=[]), \
             patch.object(m,"_required_text_slots",return_value=[fake_slot(i) for i in (1,2,3)]), \
             patch.object(m,"_publishable_ready_rows",return_value=[]), \
             patch.object(m,"prime_readonly_record_cache"), \
             patch.object(m,"enable_readonly_record_cache"), \
             patch("evergreen_inventory.allocate_bank_candidate",
                   return_value={"status":"NO_ELIGIBLE_EVERGREEN"}), \
             patch.object(m,"replenish",side_effect=generate), \
             contextlib.redirect_stdout(buffer):
            rc=m.main()
        result=json.loads(buffer.getvalue())
        return runs,result,rc

    def test_timeout_first_slot_prevents_paid_on_later_two(self):
        runs,data,rc=self.run_main_mocked("GENERATION_PROCESS_TIMEOUT")
        self.assertEqual([v["offline"] for v in runs],[False,True,True])
        self.assertEqual(rc,1)
        self.assertEqual(data["status"],"FAILED")
        self.assertEqual(len(data["hard_delivery_failures"]),3)
        self.assertTrue(all(v["paid_generation_paused"] for v in data["results"]))
        self.assertFalse(data["would_post"])

    def test_budget_failure_propagates_to_following_slots(self):
        runs,data,_=self.run_main_mocked("AI_APPROVAL_BUDGET_EXHAUSTED")
        self.assertEqual([v["offline"] for v in runs],[False,True,True])
        self.assertFalse(data["would_post"])

    def test_ratelimit_failure_propagates_to_following_slots(self):
        runs,data,_=self.run_main_mocked("PROVIDER_RATE_LIMITED")
        self.assertEqual([v["offline"] for v in runs],[False,True,True])
        self.assertFalse(data["would_post"])

    def test_normal_quality_failure_keeps_paid_route_available(self):
        runs,data,rc=self.run_main_mocked("QUALITY_EXHAUSTED")
        self.assertEqual([v["offline"] for v in runs],[False,False,False])
        self.assertTrue(all(not v["paid_generation_paused"] for v in data["results"]))
        self.assertEqual(rc,1)
        self.assertFalse(data["would_post"])


if __name__=="__main__":
    unittest.main()
