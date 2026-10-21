#!/usr/bin/env python3
"""No-network proof: exact-used offline catalogue items skip expensive preflight.

The remaining items must keep identical content/voice/hard-gate checks.
Nothing is generated, written to Sheets, approved or posted by these tests.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/"scripts"),str(ROOT/"src")]
import offline_original_catalog as catalog  # noqa: E402
from auto_approve_queue import normalize_text  # noqa: E402


class OfflineCatalogUsedPrefilterTests(unittest.TestCase):
    def tearDown(self):
        catalog._prepared_candidates.cache_clear()

    def fixture(self, *, hard_status="PASS"):
        items=("Used existing entry", "New eligible original entry")
        self.addCleanup(catalog._prepared_candidates.cache_clear)
        catalog._prepared_candidates.cache_clear()
        calls={k:0 for k in ("repair","validator","hard","quality","rank")}
        def repair(value, account):
            calls["repair"]+=1
            return {"public_post_text":value, "repair_count":0}
        def valid(value, account):
            calls["validator"]+=1
            return {"status":"PASS","reader_value_score":91,
                    "account_fit_score":92,"naturalness_score":93,
                    "cta_pressure_score":0}
        def hard(*args, **kwargs):
            calls["hard"]+=1
            return {"status":hard_status,"hard_gate_reasons":[]}
        def quality(*args, **kwargs):
            calls["quality"]+=1
            return {"topic_coherence_score":91,"batch_diversity_status":"PASS",
                    "diversity_blocked_reasons":[],"topic_blocked_reasons":[]}
        def rank(*args, **kwargs):
            calls["rank"]+=1
            return {"quality_rank":90.0,"quality_rank_components":{}}
        patches=[
            patch.object(catalog,"catalog",return_value=items),
            patch("generation.content_quality_v2.repair_style_only",side_effect=repair),
            patch("public_post_quality.final_public_post_validator",side_effect=valid),
            patch("generation.content_quality_v2.hard_gate",side_effect=hard),
            patch("generation_quality_gates.evaluate_generation_quality",side_effect=quality),
            patch("generation.content_quality_v2.rank_candidate",side_effect=rank),
        ]
        return items,calls,patches

    def test_previously_used_entry_never_reaches_expensive_quality(self):
        items,calls,patches=self.fixture()
        for p in patches:p.start();self.addCleanup(p.stop)
        excluded=frozenset({normalize_text(items[0])})
        rows=catalog._prepared_candidates("night_scout",excluded)
        self.assertEqual([r["text"] for r in rows],[items[1]])
        self.assertEqual(calls["repair"],2)
        self.assertEqual(calls["validator"],1)
        self.assertEqual(calls["hard"],1)
        self.assertEqual(calls["quality"],1)
        self.assertEqual(calls["rank"],1)

    def test_all_used_entries_have_zero_editorial_spend(self):
        items,calls,patches=self.fixture()
        for p in patches:p.start();self.addCleanup(p.stop)
        excluded=frozenset(normalize_text(t) for t in items)
        rows=catalog._prepared_candidates("night_scout",excluded)
        self.assertEqual(rows,())
        self.assertEqual(calls["validator"],0)
        self.assertEqual(calls["hard"],0)
        self.assertEqual(calls["quality"],0)
        self.assertEqual(calls["rank"],0)

    def test_new_content_never_bypasses_original_hard_gate(self):
        items,calls,patches=self.fixture(hard_status="BLOCKED")
        for p in patches:p.start();self.addCleanup(p.stop)
        rows=catalog._prepared_candidates(
            "night_scout",frozenset({normalize_text(items[0])}))
        self.assertEqual(rows,())
        self.assertEqual(calls["hard"],1)
        self.assertEqual(calls["quality"],0)

    def test_default_argument_preserves_legacy_catalogue_contract(self):
        items,calls,patches=self.fixture()
        for p in patches:p.start();self.addCleanup(p.stop)
        rows=catalog._prepared_candidates("night_scout")
        self.assertEqual(len(rows),2)
        self.assertEqual(calls["validator"],2)
        self.assertEqual(calls["hard"],2)

    def test_select_original_supplies_both_history_and_used_texts(self):
        with patch.object(catalog,"_prepared_candidates",return_value=()) as prepared:
            result=catalog.select_original("night_scout",["Historical text"],
                                           used_texts=["Reserved queue text"])
        self.assertEqual(result,{})
        prepared.assert_called_once_with(
            "night_scout",frozenset({
                normalize_text("Historical text"),
                normalize_text("Reserved queue text"),
            }))


if __name__=="__main__":
    unittest.main()
