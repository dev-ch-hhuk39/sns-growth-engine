#!/usr/bin/env python3
"""Preparing direct media must create evidence tabs on legacy Sheets workbooks."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

import run_direct_reference_media_pipeline as pipeline


class Client:
    def __init__(self):
        self.ensured: list[str] = []

    def _ensure_tab(self, logical, _headers):
        self.ensured.append(logical)


client = Client()
saved: list[str] = []
original_append = pipeline.append_row
try:
    pipeline.append_row = lambda _client, logical, _row: saved.append(logical)
    pipeline._record_caption_attempt(
        client,
        post={"source_post_id": "post_1", "source_id": "source_1"},
        account_id="liver_manager",
        grounded={"status": "PASS", "semantic_alignment": {"status": "PASS"}},
    )
finally:
    pipeline.append_row = original_append

assert client.ensured == ["content_understanding_runs", "semantic_alignment_runs"], client.ensured
assert saved == ["content_understanding_runs", "semantic_alignment_runs"], saved
print("PASS test_direct_media_evidence_tabs_self_heal.py")
