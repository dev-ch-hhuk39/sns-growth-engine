#!/usr/bin/env python3
"""Validate fail-closed publication flags across every GitHub workflow."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github/workflows"
WATCHED_FLAGS = (
    "PUBLISH_ENABLED",
    "ALLOW_REAL_X_POST",
    "ALLOW_REAL_THREADS_POST",
    "ALLOW_TRANSCRIPTION_API",
    "ALLOW_CLOUDINARY_UPLOAD",
    "ALLOW_VIDEO_DOWNLOAD",
    "ALLOW_VIDEO_CUT",
    "ALLOW_MEDIA_POSTS",
    "ALLOW_REAL_THREADS_VIDEO_POST",
)
REAL_ACTION_CMDS = (
    "--confirm-real-post",
    "--confirm-upload",
    "--confirm-download",
    "--confirm-cut",
    "--confirm-direct-media",
)
TEXT_SCHEDULED = {
    "autonomous-growth-loop-night-scout.yml": (
        'ACCOUNT_ID: "night_scout"',
        'cron: "45 4 * * *"',
        'cron: "45 6 * * *"',
        'cron: "45 15 * * *"',
    ),
    "autonomous-growth-loop-liver-manager.yml": (
        'ACCOUNT_ID: "liver_manager"',
        'cron: "45 0 * * *"',
        'cron: "45 3 * * *"',
        'cron: "45 11 * * *"',
    ),
}
MEDIA_SCHEDULED = {
    "direct-reference-media-night-scout.yml": ('ACCOUNT_ID: "night_scout"', 'cron: "45 8 * * *"'),
    "direct-reference-media-liver-manager.yml": ('ACCOUNT_ID: "liver_manager"', 'cron: "45 6 * * *"'),
    "media-growth-post-night-scout.yml": ('ACCOUNT_ID: "night_scout"', 'cron: "45 11 * * *"'),
    "media-growth-post-liver-manager.yml": ('ACCOUNT_ID: "liver_manager"', 'cron: "45 8 * * *"'),
}


def as_text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def has_guard(value: Any) -> bool:
    text = as_text(value).lower()
    return any(token in text for token in (
        "confirm",
        "run_autonomous_apply",
        "steps.activation.outputs.allowed",
        "steps.preflight.outputs.window_allowed",
        "human_approved",
    ))


def workflow_on(data: dict[str, Any]) -> Any:
    return data.get("on") if "on" in data else data.get(True)


def scope_envs(data: dict[str, Any]):
    if isinstance(data.get("env"), dict):
        yield "workflow", data["env"]
    for job_name, job in (data.get("jobs") or {}).items():
        if isinstance(job, dict) and isinstance(job.get("env"), dict):
            yield f"job:{job_name}", job["env"]


def steps(data: dict[str, Any]):
    for job_name, job in (data.get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        for step in job.get("steps") or []:
            if isinstance(step, dict):
                yield job_name, step


def main() -> int:
    results: list[tuple[str, bool]] = []
    paths = sorted(WORKFLOW_DIR.glob("*.yml"))
    for path in paths:
        name = path.name
        text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(text)

        for scope, env in scope_envs(data):
            for flag in WATCHED_FLAGS:
                if flag in env:
                    value = as_text(env[flag]).lower()
                    results.append((f"{name} [{scope}] {flag}=false", value == "false"))

        for _job_name, step in steps(data):
            label = str(step.get("name", "(no-name)"))
            condition = step.get("if", "")
            env = step.get("env") or {}
            if isinstance(env, dict):
                for flag in WATCHED_FLAGS:
                    if flag not in env:
                        continue
                    value = env[flag]
                    rendered = as_text(value).lower()
                    if "${{" in rendered:
                        results.append((f"{name} step[{label}] {flag} expression guarded", has_guard(value)))
                    elif rendered == "true":
                        results.append((f"{name} step[{label}] {flag}=true guarded", has_guard(condition)))

            run = str(step.get("run", "") or "")
            commands = [command for command in REAL_ACTION_CMDS if command in run]
            if commands:
                stripped = run
                for command in REAL_ACTION_CMDS:
                    stripped = stripped.replace(command, "")
                guarded = has_guard(condition) or has_guard(stripped)
                for command in commands:
                    results.append((f"{name} step[{label}] {command} guarded", guarded))

        on_value = workflow_on(data)
        scheduled = isinstance(on_value, dict) and "schedule" in on_value
        if not scheduled:
            continue

        if name in TEXT_SCHEDULED:
            results.extend((f"{name} canonical marker {marker}", marker in text) for marker in TEXT_SCHEDULED[name])
            for marker in (
                "Schedule heartbeat",
                "Early runtime preflight",
                "scheduled_execution_guard",
                "scheduled_window_decision",
                "Resolve autonomous execution mode",
                "scheduled_publish_enabled",
                "production_publish_activation_approved",
                "run_scheduled_text_slot_pipeline.py",
                'PUBLISH_ENABLED: "false"',
                'ALLOW_REAL_X_POST: "false"',
                'ALLOW_VIDEO_DOWNLOAD: "false"',
                'ALLOW_VIDEO_CUT: "false"',
                'ALLOW_CLOUDINARY_UPLOAD: "false"',
            ):
                results.append((f"{name} text safety marker {marker}", marker in text))
            results.append((f"{name} no idle sleep", "random.randint" not in text and "time.sleep" not in text))

        elif name in MEDIA_SCHEDULED:
            results.extend((f"{name} canonical marker {marker}", marker in text) for marker in MEDIA_SCHEDULED[name])
            for marker in (
                "Schedule heartbeat",
                "Early runtime preflight",
                "scheduled_execution_guard",
                "scheduled_window_decision",
                "Stop delayed scheduled execution",
                "exit 2",
                "run_hybrid_ready_pipeline.py",
                "scheduled_publish_activation_gate.py --use-sheets",
                "Runtime activation gate",
                "selected_queue_id",
                '--queue-id "$qid"',
                'PUBLISH_ENABLED: "false"',
                'ALLOW_REAL_THREADS_POST: "false"',
                'ALLOW_REAL_X_POST: "false"',
                'ALLOW_VIDEO_DOWNLOAD: "false"',
                'ALLOW_VIDEO_CUT: "false"',
                'ALLOW_CLOUDINARY_UPLOAD: "false"',
            ):
                results.append((f"{name} media safety marker {marker}", marker in text))
            results.append((f"{name} no text fallback", "--fallback-to-text" not in text))
            results.append((f"{name} activation output visible", ">/dev/null 2>&1" not in text))

        elif name == "content-slot-recovery.yml":
            results.append((f"{name} recovery cadence", 'cron: "0,30 * * * *"' in text))
            results.append((f"{name} explicit backfill confirmation", "--confirm-backfill" in text))

        else:
            results.append((f"{name} scheduled default publish disabled", 'PUBLISH_ENABLED: "true"' not in text or "confirm" in text.lower()))

    failures = [label for label, ok in results if not ok]
    for label, ok in results:
        print(f"  {'PASS' if ok else 'FAIL'} {label}")
    print(f"\nInspected workflows: {len(paths)}")
    print(f"PASS: {len(results) - len(failures)} / FAIL: {len(failures)}")
    if failures:
        print("Failed checks:")
        for label in failures:
            print(f"- {label}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
