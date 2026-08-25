#!/usr/bin/env python3
"""A fail-soft external skip advances to another approved parent."""
from __future__ import annotations

import contextlib
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

import ingest_direct_reference_media_reliable as reliable  # noqa: E402

original_main = reliable.core.main
original_argv = list(sys.argv)
try:
    calls: list[int] = []

    def fake_main() -> int:
        calls.append(1)
        status = "SKIPPED_EXTERNAL_UNAVAILABLE" if len(calls) == 1 else "INGESTED_BUNDLE"
        print(f'{{"status":"{status}"}}')
        return 0

    reliable.core.main = fake_main
    sys.argv = [
        "ingest_direct_reference_media_reliable.py",
        "--account-id",
        "night_scout",
    ]
    errors = io.StringIO()
    with contextlib.redirect_stderr(errors):
        assert reliable.main() == 0
    assert len(calls) == 2, calls
    assert "trying next approved parent" in errors.getvalue()
finally:
    reliable.core.main = original_main
    sys.argv = original_argv

print("PASS test_direct_media_reliable_external_skip_retry.py")
