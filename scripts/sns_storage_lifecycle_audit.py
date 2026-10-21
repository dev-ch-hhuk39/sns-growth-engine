#!/usr/bin/env python3
"""Read-only SNS Growth Engine storage lifecycle inventory and retention plan.

No deletion, network, Docker, log contents, env values, or cross-service scans.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_RUNNER = Path("/opt/github-runners/sns-growth-engine")
DEFAULT_DATA = Path("/var/lib/sns-growth-engine")
DEFAULT_ROOT = DEFAULT_RUNNER / ".buffered-runtime"
BASELINE = Path(__file__).resolve().parents[1] / "config" / "sns_storage_lifecycle_baseline_20261020.json"
MEDIA_POLICY_CONFIG = Path(__file__).resolve().parents[1] / "config" / "media_growth_engine.json"
SHA = re.compile(r"[0-9a-f]{40}\Z")
MIN_RELEASE_AGE_SECONDS = 7 * 86400
MIN_STAGE_FREE_BYTES = 9 * 1024**3
MIN_POST_STAGE_FREE_BYTES = 8 * 1024**3


class StorageAuditBlocked(RuntimeError):
    """Fail closed with a non-sensitive reason code."""


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise StorageAuditBlocked(reason)


def ordinary_dir(path: Path, *, required: bool = True) -> bool:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        require(not required, "SNS_STORAGE_REQUIRED_PATH_MISSING")
        return False
    require(stat.S_ISDIR(mode), "SNS_STORAGE_PATH_NOT_ORDINARY_DIRECTORY")
    return True


def disk_bytes(path: Path) -> int:
    """Use allocated bytes; do not read file contents or follow linked trees."""
    if not path.exists():
        return 0
    ordinary_dir(path)
    result = subprocess.run(
        ["du", "-sk", "--", str(path)],
        capture_output=True, text=True, timeout=90, check=False,
    )
    require(result.returncode == 0, "SNS_STORAGE_SIZE_UNVERIFIABLE")
    try:
        kib = int(result.stdout.split()[0])
    except (IndexError, ValueError):
        raise StorageAuditBlocked("SNS_STORAGE_SIZE_UNVERIFIABLE") from None
    require(kib >= 0, "SNS_STORAGE_SIZE_UNVERIFIABLE")
    return kib * 1024


def pointer_sha(root: Path, name: str, releases: Path, *, required: bool) -> str | None:
    pointer = root / name
    if not pointer.exists() and not pointer.is_symlink():
        require(not required, "SNS_STORAGE_REQUIRED_POINTER_MISSING")
        return None
    require(pointer.is_symlink(), "SNS_STORAGE_POINTER_NOT_SYMLINK")
    try:
        target = pointer.resolve(strict=True)
    except (OSError, RuntimeError):
        raise StorageAuditBlocked("SNS_STORAGE_POINTER_BROKEN") from None
    require(target.parent == releases.resolve(strict=True)
            and SHA.fullmatch(target.name) is not None,
            "SNS_STORAGE_POINTER_OUT_OF_SCOPE")
    ordinary_dir(target)
    require(not target.is_symlink(), "SNS_STORAGE_POINTER_RELEASE_SYMLINK")
    return target.name


def release_identity(path: Path) -> bool:
    marker = path / ".production-release"
    if not marker.is_file() or marker.is_symlink():
        return False
    try:
        return marker.stat().st_size <= 128 and marker.read_text(encoding="ascii").strip() == path.name
    except (OSError, UnicodeError):
        return False


def healthy_release(path: Path) -> bool:
    executable = path / ".venv" / "bin" / "python"
    # Standard Python venv has a bin/python symlink, but it must resolve within
    # an existing ordinary venv directory. Never execute it as part of an audit.
    return release_identity(path) and ordinary_dir(path / ".venv", required=False) and (
        executable.exists() and os.access(executable, os.X_OK)
    )


def audited_release_inventory(root: Path, *, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    require(root.name == ".buffered-runtime", "SNS_STORAGE_RUNTIME_SCOPE_INVALID")
    ordinary_dir(root)
    ordinary_dir(root / "shared")
    releases = root / "releases"
    ordinary_dir(releases)
    pointers = {
        name: pointer_sha(root, name, releases, required=name != "pending")
        for name in ("current", "previous", "pending")
    }
    require(pointers["current"] != pointers["previous"], "SNS_STORAGE_ROLLBACK_NOT_DISTINCT")
    protected = {sha for sha in pointers.values() if sha}
    items = []
    unknown_entries = 0
    stage_entries = 0
    for path in sorted(releases.iterdir(), key=lambda entry: entry.name):
        if not SHA.fullmatch(path.name):
            # Unknown entries are protected; a separate marker-scoped
            # interrupted-stage cleanup already exists in the repository.
            unknown_entries += 1
            if path.name.startswith(".stage-"):
                stage_entries += 1
            continue
        ordinary_dir(path)
        marker = release_identity(path)
        healthy = healthy_release(path) if marker else False
        mtime = path.stat().st_mtime
        item = {
            "sha": path.name,
            "allocated_bytes": disk_bytes(path),
            "python_venv_bytes": disk_bytes(path / ".venv") if (path / ".venv").is_dir() else 0,
            "modified_at_utc": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(),
            "age_days": max(0, int((now - mtime) // 86400)),
            "cleanup_eligible_after_utc": (
                datetime.fromtimestamp(mtime, tz=timezone.utc)
                + timedelta(seconds=MIN_RELEASE_AGE_SECONDS)
            ).isoformat() if marker else None,
            "marker_valid": marker,
            "rebuildable_venv_present": healthy,
            "protected_reason": "POINTER" if path.name in protected else "",
        }
        items.append(item)
    require(any(i["sha"] == pointers["current"] and i["rebuildable_venv_present"] for i in items),
            "SNS_STORAGE_CURRENT_UNHEALTHY")
    require(any(i["sha"] == pointers["previous"] and i["rebuildable_venv_present"] for i in items),
            "SNS_STORAGE_PREVIOUS_UNHEALTHY")
    # Do not rely solely on current + previous: preserve a third independently
    # reinstallable, marker-verified full release for emergency rollback.
    available = [i for i in items if i["sha"] not in protected and i["rebuildable_venv_present"]]
    require(bool(available), "SNS_STORAGE_EMERGENCY_RELEASE_UNAVAILABLE")
    emergency = max(available, key=lambda i: i["modified_at_utc"])
    emergency["protected_reason"] = "EMERGENCY_RECOVERY"
    protected.add(emergency["sha"])
    for item in items:
        if item["sha"] in protected:
            continue
        age = now - datetime.fromisoformat(item["modified_at_utc"]).timestamp()
        if not item["marker_valid"]:
            # Unknown ownership is never inferred from an old SHA-looking name.
            item["protected_reason"] = "FORENSIC_HOLD_UNVERIFIED_IDENTITY"
        elif age < MIN_RELEASE_AGE_SECONDS:
            item["protected_reason"] = (
                "INCOMPLETE_SEVEN_DAY_GRACE"
                if not item["rebuildable_venv_present"] else "SEVEN_DAY_GRACE"
            )
        else:
            # Exact marker-matched stale partials can enter the SAME guarded
            # explicit SHA cleanup as full releases, but are never auto-deleted.
            # A candidate is not proof of no process/FD/rollback dependencies.
            item["protected_reason"] = "CANDIDATE_REQUIRES_APPROVAL_AND_IN_USE_SCAN"
    candidates = [item for item in items
                  if item["protected_reason"] == "CANDIDATE_REQUIRES_APPROVAL_AND_IN_USE_SCAN"]
    return {
        "pointers": pointers,
        "emergency_recovery_sha": emergency["sha"],
        "release_count": len(items),
        "held_unrecognized_release_entries": unknown_entries,
        "held_interrupted_stage_entries": stage_entries,
        "release_allocated_bytes": sum(i["allocated_bytes"] for i in items),
        "release_venv_bytes": sum(i["python_venv_bytes"] for i in items),
        "releases": items,
        "review_candidates": [i["sha"] for i in candidates],
        "review_candidates_details": [
            {"sha": i["sha"], "allocated_bytes": i["allocated_bytes"],
             "full_recovery_release": i["rebuildable_venv_present"]}
            for i in candidates
        ],
        "grace_period_hold_count": sum(
            i["protected_reason"] in ("SEVEN_DAY_GRACE", "INCOMPLETE_SEVEN_DAY_GRACE")
            for i in items
        ),
        "grace_period_hold_sha": [
            {"sha": i["sha"], "eligible_after_utc": i["cleanup_eligible_after_utc"]}
            for i in items if i["protected_reason"] in (
                "SEVEN_DAY_GRACE", "INCOMPLETE_SEVEN_DAY_GRACE"
            )
        ],
        "preliminary_reclaim_bytes": sum(i["allocated_bytes"] for i in candidates),
        "max_manual_releases_per_approval": 2,
        "minimum_release_age_days": 7,
    }


def audit(
    root: Path = DEFAULT_ROOT, runner: Path = DEFAULT_RUNNER,
    data: Path = DEFAULT_DATA, *, now: float | None = None,
    allow_test_roots: bool = False, disk_total: int | None = None,
    disk_free: int | None = None,
) -> dict:
    if not allow_test_roots:
        require(sys.platform == "linux" and
                root == DEFAULT_ROOT and runner == DEFAULT_RUNNER and data == DEFAULT_DATA,
                "SNS_STORAGE_PRODUCTION_SCOPE_REQUIRED")
    ordinary_dir(runner)
    ordinary_dir(data)
    require(root.parent == runner, "SNS_STORAGE_ROOT_NOT_OWNED_BY_RUNNER")
    result = audited_release_inventory(root, now=now)
    # Only known SNS-owned locations; no /var/lib/containerd, Docker, /root or
    # global home/cache paths. User data, backup and P0 ledger are measured
    # without enumerating their contents.
    paths = {
        "runtime_shared_protected": root / "shared",
        "runtime_cron_logs": root / "shared" / "logs",
        "p0_private_ledger_and_recovery": root / "shared" / "p0_once_private",
        "runner_worktree": runner / "_work" / "sns-growth-engine",
        "runner_python_toolcache": runner / "_work" / "_tool",
        "runner_diagnostic_logs": runner / "_diag",
        "pip_cache": data / ".cache" / "pip",
        "huggingface_model_cache": data / ".cache" / "huggingface",
        "sns_local_config_and_state": data / ".config",
    }
    measured = {}
    for label, path in paths.items():
        # Missing optional directories must not be created just to audit.
        measured[label] = disk_bytes(path)
    if disk_total is None or disk_free is None:
        usage = shutil.disk_usage("/")
        disk_total, disk_free = usage.total, usage.free
    require(disk_total > 0 and 0 <= disk_free <= disk_total,
            "SNS_STORAGE_DISK_USAGE_INVALID")
    # Read the exact existing media resource stop threshold; never invent an
    # independent limit that drifts from check_media_resource_budget.py.
    try:
        media_policy = json.loads(MEDIA_POLICY_CONFIG.read_text(encoding="utf-8"))
        media_prepare_stop = float(media_policy["resource_limits"]["disk_prepare_stop_percent"])
        require(0 < media_prepare_stop <= 100, "SNS_STORAGE_MEDIA_THRESHOLD_INVALID")
    except (OSError, ValueError, KeyError, TypeError):
        raise StorageAuditBlocked("SNS_STORAGE_MEDIA_THRESHOLD_UNVERIFIABLE") from None
    used_percent = round(100.0 * (disk_total - disk_free) / disk_total, 2)
    media_preparation_gate = "PASS" if used_percent < media_prepare_stop else "BLOCKED"
    try:
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        baseline_metrics = baseline["metrics"]
        require(baseline["schema_version"] == 1, "SNS_STORAGE_BASELINE_SCHEMA_INVALID")
        growth = {
            metric: actual - int(baseline_metrics[metric])
            for metric, actual in {
                "release_allocated_bytes": result["release_allocated_bytes"],
                "runner_python_toolcache": measured["runner_python_toolcache"],
                "huggingface_model_cache": measured["huggingface_model_cache"],
                "pip_cache": measured["pip_cache"],
                "runner_diagnostic_logs": measured["runner_diagnostic_logs"],
                "runtime_shared_protected": measured["runtime_shared_protected"],
                "disk_free_bytes": disk_free,
            }.items()
        }
    except (OSError, KeyError, ValueError, TypeError):
        raise StorageAuditBlocked("SNS_STORAGE_BASELINE_UNVERIFIABLE") from None
    result.update({
        "baseline_measured_at_jst": baseline["measured_at_jst"],
        "growth_since_baseline": growth,
        "schema_version": 1,
        "status": ("PASS" if disk_free >= MIN_STAGE_FREE_BYTES
                   and media_preparation_gate == "PASS" else "CAPACITY_WARNING"),
        "audit_mode": "READ_ONLY",
        "owner": "sns-growth-engine",
        "measured_at_utc": datetime.fromtimestamp(
            time.time() if now is None else now, timezone.utc
        ).isoformat(),
        "disk_total_bytes": disk_total,
        "disk_free_bytes": disk_free,
        "disk_used_percent": used_percent,
        "media_prepare_stop_percent": media_prepare_stop,
        "media_preparation_disk_gate": media_preparation_gate,
        "before_stage_9gib_gate": "PASS" if disk_free >= MIN_STAGE_FREE_BYTES else "BLOCKED",
        "after_stage_8gib_gate": "PASS" if disk_free >= MIN_POST_STAGE_FREE_BYTES else "BLOCKED",
        "owned_subtree_allocated_bytes": measured,
        "shared_docker_containerd": "OUT_OF_SCOPE_NO_WRITE",
        "backup_databases_uploads": "PROTECTED_NO_DELETE",
        "last_used_at": "UNVERIFIED_mtime_is_not_last_use",
        "deletion_performed": False,
        "automated_deletion_enabled": False,
        "required_cleanup_authority": "exact_SHA_and_owner_approval_and_global_lock_and_proc_scan",
    })
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--runner-root", type=Path, default=DEFAULT_RUNNER)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--summary-only", action="store_true")
    args = parser.parse_args()
    try:
        report = audit(args.runtime_root, args.runner_root, args.data_root)
    except (OSError, ValueError, StorageAuditBlocked, subprocess.TimeoutExpired) as exc:
        # Do not leak path, local environment or tool stderr through exceptions.
        reason = str(exc) if isinstance(exc, StorageAuditBlocked) else "SNS_STORAGE_AUDIT_UNVERIFIABLE"
        print(json.dumps({"status": "BLOCKED", "reason": reason,
                          "deletion_performed": False}, sort_keys=True))
        return 2
    if args.output:
        if not args.output.is_absolute() or args.output.is_symlink():
            print('{"status":"BLOCKED","reason":"SNS_STORAGE_OUTPUT_UNSAFE"}')
            return 2
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
    if args.summary_only:
        print(json.dumps({
            key: report[key] for key in (
                "status", "release_count", "release_allocated_bytes",
                "release_venv_bytes", "disk_free_bytes", "before_stage_9gib_gate",
                "disk_used_percent", "media_prepare_stop_percent", "media_preparation_disk_gate",
                "review_candidates", "preliminary_reclaim_bytes", "deletion_performed",
            )
        }, sort_keys=True))
    else:
        print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
