#!/usr/bin/env python3
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

import ingest_direct_reference_media_reliable as reliable


cutoff = reliable.LEGACY_THREADS_BACKEND_FAILURE_RECOVERY_CUTOFF

base = {
    "download_status": "FAILED",
    "last_error": "ingest_failed:BackendFailure",
    "updated_at": (cutoff - timedelta(seconds=1)).isoformat(),
}

assert reliable.legacy_threads_backend_failure_recoverable(
    base,
    "threads",
)

assert not reliable.legacy_threads_backend_failure_recoverable(
    {
        **base,
        "updated_at": cutoff.isoformat(),
    },
    "threads",
)

assert not reliable.legacy_threads_backend_failure_recoverable(
    {
        **base,
        "updated_at": (cutoff + timedelta(seconds=1)).isoformat(),
    },
    "threads",
)

assert not reliable.legacy_threads_backend_failure_recoverable(
    base,
    "youtube",
)

assert not reliable.legacy_threads_backend_failure_recoverable(
    {
        **base,
        "last_error": "ingest_failed:IndexError",
    },
    "threads",
)

assert not reliable.legacy_threads_backend_failure_recoverable(
    {
        **base,
        "last_error": "ingest_failed:threads_post_parent_mismatch",
    },
    "threads",
)

assert not reliable.legacy_threads_backend_failure_recoverable(
    {
        **base,
        "last_error": "ingest_failed:threads_post_author_mismatch",
    },
    "threads",
)

assert not reliable.legacy_threads_backend_failure_recoverable(
    {
        **base,
        "download_status": "BLOCKED",
    },
    "threads",
)

assert not reliable.legacy_threads_backend_failure_recoverable(
    {
        **base,
        "updated_at": "",
    },
    "threads",
)

print("PASS test_direct_media_recovers_legacy_threads_backend_failure_once.py")
