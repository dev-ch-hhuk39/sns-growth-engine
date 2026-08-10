#!/usr/bin/env python3
"""Automatic preparation advances; explicit targets remain fixed."""
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
    results = iter([1, 0])

    def automatic() -> int:
        calls.append(1)
        return next(results)

    reliable.core.main = automatic
    sys.argv = ["ingest_direct_reference_media_reliable.py", "--account-id", "night_scout"]
    with contextlib.redirect_stderr(io.StringIO()) as errors:
        assert reliable.main() == 0
    assert len(calls) == 2
    assert "trying next approved parent" in errors.getvalue()

    explicit_calls: list[int] = []

    def explicit() -> int:
        explicit_calls.append(1)
        return 1

    reliable.core.main = explicit
    sys.argv = [
        "ingest_direct_reference_media_reliable.py",
        "--source-post-id",
        "sp_fixed",
    ]
    assert reliable.main() == 1
    assert len(explicit_calls) == 1
finally:
    reliable.core.main = original_main
    sys.argv = original_argv

print("PASS test_direct_media_reliable_candidate_retry.py")
