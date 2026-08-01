#!/usr/bin/env python3
from pathlib import Path

workflow = (
    Path(__file__).resolve().parents[1]
    / ".github/workflows/direct-media-preparation.yml"
).read_text(encoding="utf-8")

assert "strategy:\n      fail-fast: false\n      max-parallel: 1\n      matrix:" in workflow
assert workflow.count("account_id: night_scout") == 1
assert workflow.count("account_id: liver_manager") == 1
assert "PUBLISH_ENABLED: \"false\"" in workflow
assert "ALLOW_REAL_THREADS_POST: \"false\"" in workflow
assert "ALLOW_MEDIA_POSTS: \"false\"" in workflow

print("PASS test_direct_media_preparation_serialized.py")
