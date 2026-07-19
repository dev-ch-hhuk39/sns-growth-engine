#!/usr/bin/env python3
from run_media_growth_engine import append_clip_evidence_to_sheets
from sheets_client import TAB_DEFINITIONS


class Worksheet:
    def __init__(self, headers):
        self.headers = headers
        self.rows = []

    def get_all_records(self):
        return list(self.rows)

    def row_values(self, row):
        assert row == 1
        return list(self.headers)

    def append_row(self, values, value_input_option=None):
        self.rows.append(dict(zip(self.headers, values)))


class Client:
    def __init__(self):
        self.tabs = {}

    def _ensure_tab(self, logical, headers):
        return self.tabs.setdefault(logical, Worksheet(headers))

    def _ws(self, logical):
        return self.tabs[logical]

    def _call_with_rate_limit_retry(self, _label, operation):
        return operation()


candidate = {
    "clip_candidate_id": "clip_evidence_1",
    "source_id": "source_1",
    "source_video_id": "video_1",
    "account_id": "liver_manager",
    "platform": "youtube",
    "public_post_text": "配信で初見さんが入りやすくなる工夫を一つずつ整えよう。",
    "caption_provider": "github_models",
    "caption_provider_version": "v1",
    "content_understanding_status": "PASS",
    "main_claims_json": '["初見が入りやすい導線"]',
    "analysis_topic": "配信導線",
    "analysis_audience": "配信初心者",
    "alignment_status": "PASS",
    "final_alignment_score": "0.92",
    "main_claim_coverage": "1.0",
    "unsupported_claim_count": "0",
    "source_copy_similarity": "0.20",
    "recent_post_similarity": "0.10",
    "claim_support_json": "[]",
    "source_content_hash": "abc123",
    "transcript_excerpt": "this must never be persisted in evidence logs",
}
video = {"source_video_id": "video_1", "comment_count": "4", "content_hash": "abc123"}
client = Client()
first = append_clip_evidence_to_sheets(client, [candidate], [video])
second = append_clip_evidence_to_sheets(client, [candidate], [video])
assert first == 2, first
assert second == 0, second
assert len(client.tabs["content_understanding_runs"].rows) == 1
assert len(client.tabs["semantic_alignment_runs"].rows) == 1
assert "transcript" not in str(client.tabs["content_understanding_runs"].rows).lower()
assert "transcript" not in str(client.tabs["semantic_alignment_runs"].rows).lower()
print("PASS test_clip_understanding_alignment_evidence.py")
