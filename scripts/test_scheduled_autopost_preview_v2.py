#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
preview = (ROOT / "scripts/run_scheduled_autopost_preview_v2.py").read_text(encoding="utf-8")
workflow = (ROOT / ".github/workflows/wp3-production-readonly-verification.yml").read_text(encoding="utf-8")
source_context = (ROOT / "scripts/hybrid_ai_source_context.py").read_text(encoding="utf-8")
autonomous = (ROOT / "scripts/run_autonomous_loop.py").read_text(encoding="utf-8")
generator = (ROOT / "scripts/generate_threads_ideas_from_references.py").read_text(encoding="utf-8")
record_reader = (ROOT / "src/sheets_record_reader.py").read_text(encoding="utf-8")
media_pipeline = (ROOT / "scripts/run_media_production_pipeline.py").read_text(encoding="utf-8")

for slot_id in (
    "ns_1400_reference", "ns_1600_original", "ns_1800_direct_media",
    "ns_2100_clip_media", "ns_2500_pdca", "lm_1000_original",
    "lm_1300_reference", "lm_1600_direct_media", "lm_1800_clip_media",
    "lm_2100_pdca",
):
    assert slot_id in preview

for forbidden in (
    "process_threads_queue.py", "--confirm-real-post", "PUBLISH_ENABLED=true",
    "update_queue_item(", "append_row(", "append_rows(", "update_cell(",
):
    assert forbidden not in preview, forbidden

assert "dry_run=True" in preview
assert "writes_performed" in preview
assert "queue_unchanged" in preview
assert "protected_rows_unchanged" in preview
assert "scheduled_publish_activation_gate.py\", \"--use-sheets" in preview
assert "--json-output" not in preview
assert "include_preview_rows" in generator
assert "--include-preview-queue" in generator
assert "client: Any | None = None" in generator
assert 'read_records_safely(client, "posted_results")' in generator
assert "posted_results=[dict(row) for row in posted_results_all]" in generator
assert "enable_readonly_record_cache(client)" in preview
assert "client=client" in preview
assert "READONLY_RECORD_CACHE_ATTR" in record_reader
assert "_cached_records(client, logical)" in record_reader
assert "read_records_safely(client, logical)" in media_pipeline
assert "_call_with_rate_limit_retry" in media_pipeline
assert "READONLY_RECORD_CACHE_ATTR" in media_pipeline
assert "--require-measured-pdca" in autonomous
assert "source_account_posts" in source_context
assert "source_result_id" in source_context
assert "media_permissions" in source_context
assert "permission_evidence_status" in source_context
assert "Preview all scheduled candidates with Gemini" in workflow
assert "if: always()" in workflow
assert 'PUBLISH_ENABLED: "false"' in workflow
assert 'ALLOW_REAL_THREADS_POST: "false"' in workflow
assert 'ALLOW_MEDIA_POSTS: "false"' in workflow
print("PASS test_scheduled_autopost_preview_v2.py")
