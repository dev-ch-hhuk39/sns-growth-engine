#!/usr/bin/env python3
from pathlib import Path

from run_autonomous_loop import _last_json_object, infer_no_post_reason, summarize_autonomous_results
from run_scheduled_text_slot_pipeline import generated_queue_ids, generation_failure_reason

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    generated = {
        "results": [{
            "cmd": "python scripts/generate_threads_ideas_from_references.py",
            "payload": {"status": "GENERATED", "effective_queue_ids": ["q_fresh"]},
        }]
    }
    assert generated_queue_ids(generated) == ["q_fresh"]

    multi_result_stdout = """
log line before JSON
{"status":"WILL_RUN","video_reference_analysis":{"status":"TRANSCRIPT_MISSING"}}
{"status":"GENERATED","effective_queue_ids":["q_fresh"],"analysis":{"status":"TRANSCRIPT_MISSING"}}
"""
    parsed = _last_json_object(multi_result_stdout)
    assert parsed["status"] == "GENERATED"
    assert parsed["effective_queue_ids"] == ["q_fresh"]

    rate_limited = {
        "results": [{
            "cmd": "python scripts/generate_threads_ideas_from_references.py",
            "stderr_tail": "Gemini API returned HTTP 429 RESOURCE_EXHAUSTED",
            "payload": {"status": "NO_DATA"},
        }]
    }
    assert generation_failure_reason(rate_limited) == "GEMINI_RATE_LIMITED"

    stopped = [{
        "cmd": "scripts/process_threads_queue.py --stop-before-post",
        "returncode": 0,
        "status": "SKIPPED",
        "reason": "stop_before_post",
    }]
    summary = summarize_autonomous_results("night_scout", "apply", stopped)
    assert summary["processed_count"] == 0
    assert summary["no_post_reason"] == "AWAITING_HYBRID_REVIEW"

    missing = infer_no_post_reason({"returncode": 0, "payload": {}})
    assert missing == "NO_POST_RESULT_MISSING"

    source = (ROOT / "scripts/run_autonomous_loop.py").read_text(encoding="utf-8")
    assert '"--top-n",\n            "1"' in source
    assert "NO_POST_UNKNOWN" not in source
    scheduled = (ROOT / "scripts/run_scheduled_text_slot_pipeline.py").read_text(encoding="utf-8")
    assert '"--account-id"' in scheduled
    assert '"--post-type"' in scheduled
    recovery = (ROOT / ".github/workflows/threads-queue-worker.yml").read_text(encoding="utf-8")
    assert "queue_id:" in recovery
    # Approval, dry-run and real processing must all use the same exact row.
    assert recovery.count('--queue-id "$QUEUE_ID"') == 4
    assert "Scoped runtime activation gate" in recovery
    print("PASS test_scheduled_exact_candidate_contract.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
