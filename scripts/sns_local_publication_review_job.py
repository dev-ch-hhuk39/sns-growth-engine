#!/usr/bin/env python3
"""No-post two-phase Sheets review job, fail-closed on ambiguous writes.

Runs only approved sync and existing explicit review decisions. Never publishes.
A failed write-phase latches the job to prevent automatic retry after
an unknown Sheets mutation result until independent reconciliation.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import stat
import uuid
import sys

ROOT = Path("/opt/github-runners/sns-growth-engine/.buffered-runtime/current")
STATE_DIR = Path("/opt/github-runners/sns-growth-engine/.buffered-runtime/shared/review-board-state")
LATCH = "manual_reconciliation_required"
MAX_REPORT_BYTES = 1_000_000
STAGES = (
    ("sync", "scripts/sync_publication_review.py", "--confirm-review-sync"),
    ("decisions", "scripts/apply_publication_review_decisions.py", "--confirm-review-decisions"),
)


class ReviewJobBlocked(RuntimeError):
    """Fixed codes only, never a remote payload."""


def validated_result(stage: str, code: int, output: str) -> dict[str, int]:
    if code != 0 or len(output.encode("utf-8")) > MAX_REPORT_BYTES:
        raise ReviewJobBlocked("REVIEW_STAGE_OUTCOME_UNVERIFIED")
    try:
        data = json.loads(output)
        if type(data) is not dict or data.get("status") != "APPLIED":
            raise ValueError()
        if stage == "sync":
            counts = ("review_count", "appended_count", "updated_count", "unchanged_review_rows")
            if data.get("read_after_write") is not True:
                raise ValueError()
        elif stage == "decisions":
            counts = ("decision_count",)
            if not (data.get("queue_read_after_write") is True
                    and data.get("review_read_after_write") is True):
                raise ValueError()
        else:
            raise ValueError()
        if any(type(data.get(c)) is not int or not 0 <= data[c] <= 100_000 for c in counts):
            raise ValueError()
        return {c: data[c] for c in counts}
    except (ValueError, TypeError):
        raise ReviewJobBlocked("REVIEW_READBACK_UNVERIFIED") from None


def sync_state_directory(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def mark_quarantine(directory: Path) -> tuple[int, int, str] | None:
    """Persist BEFORE a writer starts; never overwrite previous evidence."""
    marker = directory / LATCH
    nonce = uuid.uuid4().hex
    try:
        fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        return None
    except OSError:
        raise ReviewJobBlocked("REVIEW_QUARANTINE_NOT_WRITABLE") from None
    try:
        with os.fdopen(fd, "w", encoding="ascii") as out:
            metadata = os.fstat(out.fileno())
            out.write("REVIEW_MUTATION_OUTCOME_UNVERIFIED\n" + nonce + "\n")
            out.flush()
            os.fsync(out.fileno())
        sync_state_directory(directory)
    except Exception:
        raise ReviewJobBlocked("REVIEW_QUARANTINE_NOT_WRITABLE") from None
    return metadata.st_dev, metadata.st_ino, nonce


def finish_verified_run(directory: Path, lease: tuple[int, int, str]) -> None:
    """Complete only this invocation's record, after both readbacks pass."""
    marker = directory / LATCH
    try:
        fd = os.open(marker, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "r", encoding="ascii") as stream:
            metadata = os.fstat(stream.fileno())
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
                    or metadata.st_mode & 0o077
                    or (metadata.st_dev, metadata.st_ino) != lease[:2]
                    or stream.read(4096) != "REVIEW_MUTATION_OUTCOME_UNVERIFIED\n" + lease[2] + "\n"):
                raise ValueError()
        metadata = marker.lstat()
        if (metadata.st_dev, metadata.st_ino) != lease[:2]:
            raise ValueError()
        marker.unlink()
        sync_state_directory(directory)
    except Exception:
        raise ReviewJobBlocked("REVIEW_MANUAL_RECONCILIATION_REQUIRED") from None


def run(*, base: Path = ROOT, state_dir: Path = STATE_DIR) -> tuple[str, dict[str, dict[str, int]]]:
    if not state_dir.is_dir() or state_dir.is_symlink():
        raise ReviewJobBlocked("REVIEW_STATE_DIR_INVALID")
    if (state_dir / LATCH).exists() or (state_dir / LATCH).is_symlink():
        raise ReviewJobBlocked("REVIEW_MANUAL_RECONCILIATION_REQUIRED")
    reports: dict[str, dict[str, int]] = {}
    env = {
        **os.environ,
        "BUFFERED_POSTING_ENABLED": "false",
        "PUBLISH_ENABLED": "false",
        "ALLOW_REAL_THREADS_POST": "false",
        "ALLOW_REAL_THREADS_VIDEO_POST": "false",
        "ALLOW_REAL_X_POST": "false",
        "ALLOW_MEDIA_POSTS": "false",
        "ALLOW_CLOUDINARY_UPLOAD": "false",
        "ALLOW_VIDEO_DOWNLOAD": "false",
        "ALLOW_VIDEO_CUT": "false",
    }
    # Mark intent before the first child can mutate Sheets. A SIGKILL or power
    # loss is not caught by Python exception handlers; this file survives it.
    lease = mark_quarantine(state_dir)
    if lease is None:
        raise ReviewJobBlocked("REVIEW_MANUAL_RECONCILIATION_REQUIRED")
    for stage, script, confirmation in STAGES:
        args = [sys.executable, "-B", str(base / script),
                "--apply", confirmation, "--use-sheets"]
        if stage == "decisions":
            args.append("--require-trusted-media-review")
        # A stage invocation might have committed before the provider timed out.
        # No automatic retry occurs; only a manual verified reconciliation
        # may clear the quarantine file.
        try:
            result = subprocess.run(
                args, cwd=base, env=env, capture_output=True, text=True,
                check=False, timeout=420,
            )
            reports[stage] = validated_result(stage, result.returncode, result.stdout)
        except Exception:
            raise ReviewJobBlocked("REVIEW_MANUAL_RECONCILIATION_REQUIRED") from None
    finish_verified_run(state_dir, lease)
    return "PASS", reports


def main() -> int:
    try:
        status, reports = run()
        # Only schema-approved counts, never queue IDs, previews or provider errors.
        print("SNS_LOCAL_PUBLICATION_REVIEW=" + json.dumps({
            "status": status, "stages": reports, "posts": 0,
            "paid_ai": 0, "read_after_write": True,
        }, sort_keys=True, separators=(",", ":")))
        return 0
    except ReviewJobBlocked as exc:
        print("SNS_LOCAL_PUBLICATION_REVIEW=" + json.dumps({
            "status": "BLOCKED", "reason": str(exc), "posts": 0, "paid_ai": 0,
        }, sort_keys=True, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    sys.exit(main())
