#!/usr/bin/env python3
"""Replenish bounded approved media inventory on the Xserver host.

This runner invokes only the existing prepare-only Direct and approved-clip
commands. It never promotes or publishes by itself, and all publisher env
gates are forced off for every child process.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

ACCOUNTS = ("night_scout", "liver_manager", "beauty_account")
CLIP_ACCOUNTS = ("night_scout", "liver_manager")
MINIMUM_READY = 3
TASK_TIMEOUT_SECONDS = 45 * 60
STALE_WORKSPACE_TTL_SECONDS = 24 * 60 * 60
REQUIRED_MEDIA_ENV = (
    ("SPREADSHEET_ID", "SNS_MASTER_SHEET_ID"),
    ("GCP_SA_JSON_BASE64", "SA_JSON_BASE64"),
    ("CLOUDINARY_CLOUD_NAME",),
    ("CLOUDINARY_API_KEY",),
    ("CLOUDINARY_API_SECRET",),
    ("GEMINI_API_KEY",),
)
PUBLISH_OFF = {
    "PUBLISH_ENABLED": "false",
    "ALLOW_REAL_THREADS_POST": "false",
    "ALLOW_REAL_THREADS_VIDEO_POST": "false",
    "ALLOW_MEDIA_POSTS": "false",
    "ALLOW_THREADS_CAROUSEL": "false",
    "ALLOW_REAL_X_POST": "false",
    "GITHUB_MODELS_ENABLED": "false",
    "ALLOW_TRANSCRIPTION_API": "false",
}


def truth(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def validate_runtime_config(root: Path, env: dict[str, str]) -> list[str]:
    """Fail closed if scheduled preparation or media rights execution is off."""
    try:
        autonomous = json.loads((root / "config/autonomous_mode.json").read_text(encoding="utf-8"))
        inventory = json.loads((root / "config/production_inventory.json").read_text(encoding="utf-8"))
        media = json.loads((root / "config/media_growth_engine.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ["production_config_unreadable"]
    reasons = []
    if not autonomous.get("scheduled_prepare_enabled"):
        reasons.append("scheduled_prepare_disabled")
    if truth(autonomous.get("kill_switch")):
        reasons.append("kill_switch_active")
    if not inventory.get("activation_enabled"):
        reasons.append("buffered_inventory_disabled")
    if not media.get("media_schedule_enabled") or not media.get("production_autopilot_enabled"):
        reasons.append("media_preparation_disabled")
    if not all(media.get(key) for key in (
        "download_enabled", "cut_enabled", "upload_enabled", "cloudinary_upload_enabled",
    )):
        reasons.append("approved_media_operations_disabled")
    for alternatives in REQUIRED_MEDIA_ENV:
        if not any(env.get(name, "").strip() for name in alternatives):
            reasons.append("credential_missing:" + alternatives[0])
    return reasons


def build_tasks(root: Path, env: dict[str, str] | None = None) -> list[dict[str, str]]:
    from accounts.managed_accounts import account_production_enabled, route_slot_id

    env = env or {}
    tasks = []
    for account in ACCOUNTS:
        if account == "beauty_account" and not truth(env.get("BEAUTY_ACTIVATION_APPROVED")):
            tasks.append({"account_id": account, "route": "direct_reference_media", "slot_id": "", "blocked": "beauty_activation_not_approved"})
            continue
        if not account_production_enabled(account):
            tasks.append({"account_id": account, "route": "direct_reference_media", "slot_id": "", "blocked": "account_inactive"})
            continue
        tasks.append({
            "account_id": account,
            "route": "direct_reference_media",
            "slot_id": route_slot_id(account, "direct_reference_media"),
        })
    for account in CLIP_ACCOUNTS:
        if not account_production_enabled(account):
            tasks.append({"account_id": account, "route": "approved_source_clip", "slot_id": "", "blocked": "account_inactive"})
            continue
        tasks.append({
            "account_id": account,
            "route": "approved_source_clip",
            "slot_id": route_slot_id(account, "approved_source_clip"),
        })
    return tasks


def child_environment(base: dict[str, str], *, route: str, reuse_only: bool = False) -> dict[str, str]:
    env = dict(base)
    env.update(PUBLISH_OFF)
    # Preparation does not need Threads publishing credentials or the runner's
    # short-lived GitHub token. Do not forward them to acquisition/AI children.
    for name in tuple(env):
        if name.startswith(("THREADS_ACCESS_TOKEN_", "THREADS_USER_ID_", "THREADS_HANDLE_")):
            env.pop(name, None)
    env.pop("GITHUB_TOKEN", None)
    env["ALLOW_VIDEO_DOWNLOAD"] = "false" if reuse_only else "true"
    env["ALLOW_CLOUDINARY_UPLOAD"] = "false" if reuse_only else "true"
    env["ALLOW_LOCAL_TRANSCRIPTION"] = "false" if reuse_only else "true"
    env["ALLOW_VIDEO_CUT"] = "true" if route == "approved_source_clip" and not reuse_only else "false"
    env["BEAUTY_PRODUCTION_ENABLED"] = "true" if truth(base.get("BEAUTY_ACTIVATION_APPROVED")) else "false"
    return env


def task_command(
    task: dict[str, str], root: Path, env: dict[str, str], *, reuse_uploaded_only: bool = False
) -> list[str]:
    python = str(root / ".venv" / "bin" / "python")
    if task["route"] == "direct_reference_media":
        media = json.loads((root / "config/media_growth_engine.json").read_text(encoding="utf-8"))
        attempts = max(1, min(5, int(media.get("direct_media_candidate_attempts", 5))))
        return [python, "scripts/run_direct_media_preparation_loop.py",
                "--account-id", task["account_id"], "--slot-id", task["slot_id"],
                "--max-attempts", str(attempts), "--minimum-ready", str(MINIMUM_READY),
                "--apply", "--confirm-preparation-loop"]
    command = ["xvfb-run", "-a", python, "scripts/run_media_production_pipeline.py",
            "--account-id", task["account_id"], "--slot-id", task["slot_id"],
            "--prepare-only", "--minimum-ready", str(MINIMUM_READY),
            "--apply", "--confirm-production-media", "--use-sheets"]
    if reuse_uploaded_only:
        command.append("--reuse-uploaded-only")
    return command


def last_json_object(output: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    found = []
    for index, char in enumerate(output):
        if char != "{":
            continue
        try:
            value, end = decoder.raw_decode(output[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            found.append((index + end, value))
    return max(found, key=lambda item: item[0])[1] if found else {}


def safe_summary(payload: dict[str, Any]) -> dict[str, Any]:
    allowed = ("status", "account_id", "route", "ready_count", "ready_media_count",
               "minimum", "availability_status", "reason", "preparation_stop_reason")
    summary = {}
    for key in allowed:
        if key not in payload:
            continue
        value = payload[key]
        if key in {"reason", "preparation_stop_reason"}:
            value = str(value)
            if (len(value) > 100 or not re.fullmatch(r"[A-Za-z0-9_.:-]+", value)
                    or re.search(r"(?i)(secret|token|key|cookie|bearer|https?://|/)", value)):
                continue
        summary[key] = value
    attempts = payload.get("attempts")
    if isinstance(attempts, list):
        summary["attempt_statuses"] = [str(item.get("status", "UNKNOWN")) for item in attempts[:10]
                                       if isinstance(item, dict)]
    return summary


def _run(command: list[str], *, root: Path, env: dict[str, str],
         runner: Callable[..., subprocess.CompletedProcess[str]], timeout: int) -> tuple[int, dict[str, Any]]:
    try:
        result = runner(command, cwd=root, env=env, text=True, capture_output=True,
                        check=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, {"status": "TIMEOUT"}
    except OSError as exc:
        return 127, {"status": "COMMAND_UNAVAILABLE", "reason": type(exc).__name__}
    return result.returncode, last_json_object(result.stdout)


def _budget_command(root: Path, env: dict[str, str]) -> list[str]:
    return [str(root / ".venv" / "bin" / "python"), "scripts/check_media_resource_budget.py",
            "--use-sheets", "--check-cloudinary", "--enforce", "--purpose", "prepare"]


def _budget_allowed(payload: dict[str, Any]) -> bool:
    return (payload.get("status") == "PASS" and payload.get("preparation_allowed") is True
            and payload.get("cloudinary_status") == "AVAILABLE")


def cleanup_stale_workspaces(root: Path, *, now: float, ttl_seconds: int = STALE_WORKSPACE_TTL_SECONDS) -> int:
    """Remove only old run directories carrying this runner's ownership marker."""
    removed = 0
    if not root.is_dir() or root.is_symlink():
        return removed
    resolved_root = root.resolve()
    for candidate in root.iterdir():
        if (not candidate.name.startswith("run-") or candidate.is_symlink()
                or not candidate.is_dir() or not (candidate / ".sns-media-prep-owned").is_file()):
            continue
        try:
            resolved = candidate.resolve(strict=True)
            age = now - candidate.stat().st_mtime
        except OSError:
            continue
        if resolved.parent != resolved_root or age < ttl_seconds:
            continue
        shutil.rmtree(candidate)
        removed += 1
    return removed


def _ensure_pot_provider(*, root: Path, env: dict[str, str], runner) -> tuple[bool, bool]:
    """Return (ready, started_here); never stop a provider owned by another job."""
    try:
        health = runner(["curl", "--fail", "--silent", "http://127.0.0.1:4416/ping"],
                        cwd=root, env=env, text=True, capture_output=True,
                        check=False, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        health = None
    if health and health.returncode == 0:
        return True, False
    code, _ = _run(["bash", str(root / "scripts/start_youtube_pot_provider.sh")],
                   root=root, env=env, runner=runner, timeout=45)
    return code == 0, code == 0


def run_preparation(*, root: Path = ROOT, env: dict[str, str] | None = None,
                    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
                    lock_path: Path | None = None,
                    workspace_root: Path | None = None) -> dict[str, Any]:
    base = dict(os.environ if env is None else env)
    blockers = validate_runtime_config(root, base)
    if blockers:
        return {"status": "BLOCKED", "blockers": blockers, "tasks": [], "would_post": False}

    runtime_root = Path(base.get("BUFFERED_RUNTIME_ROOT", "/opt/github-runners/sns-growth-engine/.buffered-runtime"))
    actual_lock = lock_path or runtime_root / "shared/locks/media-preparation.lock"
    actual_lock.parent.mkdir(parents=True, exist_ok=True)
    with actual_lock.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"status": "SKIPPED_LOCKED", "tasks": [], "would_post": False}
        tasks = build_tasks(root, base)
        results = []
        provider_ready, provider_started = False, False
        base.update(PUBLISH_OFF)
        base["ALLOW_REAL_X_POST"] = "false"
        preparation_root = workspace_root or runtime_root / "shared/media-prep"
        preparation_root.mkdir(parents=True, exist_ok=True)
        cleanup_stale_workspaces(preparation_root, now=datetime.now(timezone.utc).timestamp())
        with tempfile.TemporaryDirectory(prefix="run-", dir=preparation_root) as temp_dir:
            workspace = Path(temp_dir)
            (workspace / ".sns-media-prep-owned").touch()
            base["SNS_MEDIA_PREP_WORKSPACE"] = str(workspace)
            base["TMPDIR"] = str(workspace)
            base["TMP"] = str(workspace)
            base["TEMP"] = str(workspace)
            # Temporary transcription/download/cut/upload gates are enabled
            # only for the existing bounded prepare-only children below.
            try:
                for task in tasks:
                    if task.get("blocked"):
                        results.append({**task, "status": "BLOCKED", "reason": task["blocked"], "ready_count": 0})
                        continue
                    env_for_task = child_environment(base, route=task["route"])
                    if task["route"] == "approved_source_clip":
                        reuse_env = child_environment(base, route=task["route"], reuse_only=True)
                        reuse_code, reuse_payload = _run(
                            task_command(task, root, reuse_env, reuse_uploaded_only=True),
                            root=root, env=reuse_env, runner=runner, timeout=TASK_TIMEOUT_SECONDS,
                        )
                        try:
                            reuse_count = int(reuse_payload.get("ready_count", 0))
                        except (TypeError, ValueError):
                            reuse_count = 0
                        if (reuse_code == 0 and reuse_payload.get("status") == "READY_INVENTORY_OK"
                                and reuse_count >= MINIMUM_READY):
                            results.append({**task, "status": "READY", "reason": "reused_uploaded_assets",
                                            "ready_count": reuse_count, "minimum": MINIMUM_READY})
                            continue
                    budget_code, budget = _run(_budget_command(root, env_for_task), root=root,
                                               env=child_environment(base, route="resource_check"),
                                               runner=runner, timeout=120)
                    if budget_code != 0 or not _budget_allowed(budget):
                        budget_summary = safe_summary(budget)
                        results.append({**task, "status": "PREPARATION_BLOCKED",
                                        "reason": budget_summary.get("preparation_stop_reason") or budget_summary.get("cloudinary_status") or "resource_budget_unavailable",
                                        "disk_used_percent": budget.get("disk_used_percent"), "ready_count": 0})
                        continue
                    if task["route"] == "approved_source_clip" and not provider_ready:
                        provider_ready, provider_started = _ensure_pot_provider(
                            root=root, env=env_for_task, runner=runner
                        )
                        if not provider_ready:
                            results.append({**task, "status": "PREPARATION_FAILED",
                                            "reason": "youtube_po_token_provider_unavailable", "ready_count": 0})
                            continue
                    command = task_command(task, root, env_for_task)
                    code, payload = _run(command, root=root, env=env_for_task,
                                         runner=runner, timeout=TASK_TIMEOUT_SECONDS)
                    payload_status = str(payload.get("status", ""))
                    count = payload.get("ready_media_count", payload.get("ready_count", 0))
                    try:
                        count = int(count)
                    except (TypeError, ValueError):
                        count = 0
                    success_status = "READY" if task["route"] == "direct_reference_media" else "READY_INVENTORY_OK"
                    ok = code == 0 and payload_status == success_status and count >= MINIMUM_READY
                    payload_summary = safe_summary(payload)
                    results.append({**task, "status": "READY" if ok else "PREPARATION_FAILED",
                                    "reason": "" if ok else (payload_summary.get("reason") or payload_status or f"exit_{code}"),
                                    "ready_count": count, "minimum": MINIMUM_READY,
                                    "attempt_statuses": payload_summary.get("attempt_statuses", [])})
            finally:
                if provider_started:
                    _run(["bash", str(root / "scripts/stop_youtube_pot_provider.sh")],
                         root=root, env=child_environment(base, route="approved_source_clip"),
                         runner=runner, timeout=30)

            return {"status": "PASS" if all(item["status"] == "READY" for item in results) else "PARTIAL_FAILURE",
                    "execution_id": base.get("PRODUCTION_HOST_EXECUTION_ID", ""),
                    "tasks": results, "would_post": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-preparation", action="store_true")
    args = parser.parse_args()
    if not args.apply or not args.confirm_preparation:
        parser.error("--apply and --confirm-preparation are required")
    def terminate(signum, _frame):
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    result = run_preparation()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") in {"PASS", "SKIPPED_LOCKED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
