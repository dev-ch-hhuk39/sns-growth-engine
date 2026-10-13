#!/usr/bin/env python3
"""Local-only SNS Growth Engine development QA (no GitHub Actions, no VPS).

This is deliberately NOT a deployment, scheduler or publication tool.
Run it from the Mac worktree to validate source/test changes without
contacting GitHub, Google Sheets, Cloudinary, any SNS, or production APIs.
External credential probes are explicitly excluded by the repository runner.

Examples:
  python3 scripts/run_local_quality_gate.py --mode focused
  python3 scripts/run_local_quality_gate.py --mode full
  python3 scripts/run_local_quality_gate.py --mode full --output /tmp/sns-qa.json

Only executable commands shipped in this repository or installed local
linters/scanners are invoked. Never run untrusted shell text from a manifest.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SENSITIVE_PARTS = (
    "SECRET", "TOKEN", "PASSWORD", "COOKIE", "STORAGE_STATE", "SA_JSON",
    "API_KEY", "GOOGLE_APPLICATION_CREDENTIALS", "OPENAI_API_KEY",
)
FOCUSED = (
    "test_buffered_metrics_aftercare_host.py",
    "test_metrics_aftercare_apply_preflight.py",
    "test_metrics_reservation_recovery.py",
    "test_media_mirror_operator_idp.py",
    "test_phase5b6h_legacy_sheets_mutation_inventory.py",
    "test_phase5b6d_network_sink_inventory.py",
)
MAX_OUTPUT_SIZE = 700000


def local_env() -> dict[str, str]:
    """Strip production credentials; avoid implicit/cloud token discovery."""
    return {
        name: value for name, value in os.environ.items()
        if not any(word in name.upper() for word in SENSITIVE_PARTS)
    }


def _safe_output(path: Path) -> None:
    if not path.is_absolute():
        raise ValueError("report_requires_absolute_path")
    if path == ROOT or ROOT in path.parents:
        raise ValueError("report_must_be_outside_repository")
    path.parent.mkdir(parents=True, exist_ok=True)


def _record(
    name: str, argv: tuple[str, ...], *,
    timeout: int, env: dict[str, str], log_dir: Path,
) -> dict[str, object]:
    """Run one bounded local process; never use shell or provider clients."""
    if not argv or any(type(token) is not str for token in argv):
        raise ValueError("invalid_local_qa_command")
    try:
        result = subprocess.run(
            argv, cwd=ROOT, env=env, capture_output=True, text=True,
            errors="replace", timeout=timeout, check=False,
        )
        return_code = result.returncode
        output = (result.stdout + "\n" + result.stderr)[-MAX_OUTPUT_SIZE:]
    except FileNotFoundError:
        return_code, output = 127, "required_local_tool_unavailable"
    except subprocess.TimeoutExpired:
        return_code, output = 124, "local_test_timeout"
    log_path = log_dir / (name + ".log")
    log_path.write_text(output, encoding="utf-8")
    return {
        "name": name, "status": "PASS" if return_code == 0 else "FAIL",
        "exit_code": return_code, "log_path": str(log_path),
    }


def run(
    *, mode: str, output: Path, log_dir: Path,
    skip_git_history_scan: bool = False,
) -> dict[str, object]:
    if mode not in ("focused", "full"):
        raise ValueError("mode_invalid")
    if type(skip_git_history_scan) is not bool:
        raise ValueError("scanner_mode_invalid")
    if mode == "full" and skip_git_history_scan:
        raise ValueError("full_mode_requires_local_secret_history_scan")
    _safe_output(output)
    _safe_output(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    env = local_env()
    # All commands are literal, local, and non-deploying. In particular no
    # 'gh', 'git push', workflow_dispatch, curl, SSH or service update.
    commands: list[tuple[str, tuple[str, ...], int]] = [
        (
            "ruff_fatal",
            (
                sys.executable, "-m", "ruff", "check", "--select",
                "E9,F63,F7,F82", "src", "scripts",
            ), 240,
        ),
        (
            "python_compile",
            (sys.executable, "-m", "compileall", "-q", "src", "scripts"), 240,
        ),
        ("git_worktree_diff", ("git", "diff", "--check"), 60),
        ("git_staged_diff", ("git", "diff", "--cached", "--check"), 60),
    ]
    if mode == "focused":
        commands = [
            (name.removesuffix(".py"), (sys.executable, str(SCRIPTS / name)), 240)
            for name in FOCUSED
        ] + commands
    else:
        commands = [
            (
                "repository_offline",
                (
                    sys.executable, str(SCRIPTS / "run_repository_tests.py"),
                    "--json-output", str(log_dir / "repository_result.json"),
                ), 1500,
            ),
            (
                "workflow_static_safety",
                (sys.executable, str(SCRIPTS / "test_all_workflows_safety_flags.py")), 300,
            ),
        ] + commands
    if not skip_git_history_scan:
        commands.append(
            (
                "gitleaks_local",
                (
                    "gitleaks", "detect", "--redact", "--exit-code=2",
                    "--log-opts=origin/main..HEAD",
                ), 180,
            )
        )

    checks = []
    for name, argv, timeout in commands:
        result = _record(name, argv, timeout=timeout, env=env, log_dir=log_dir)
        checks.append(result)
        print(
            f"{name}: {result['status']} (local only)",
            file=sys.stderr, flush=True,
        )

    report: dict[str, object] = {
        "schema_version": 1,
        "source": "LOCAL_MAC_TESTS_ONLY",
        "mode": mode,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "PASS" if all(r["status"] == "PASS" for r in checks) else "FAIL",
        "github_actions_invoked": False,
        "production_deployment_performed": False,
        "production_sheets_written": False,
        "sns_post_performed": False,
        "external_credential_probes_included": False,
        "note": (
            "This report verifies local code behavior only; does not prove "
            "Google/SNS/IdP runtime permissions or production automation."
        ),
        "checks": checks,
    }
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("focused", "full"), default="focused")
    parser.add_argument("--output", type=Path, default=Path("/tmp/sns-local-qa.json"))
    parser.add_argument(
        "--log-dir", type=Path, default=Path("/tmp/sns-local-qa-logs")
    )
    parser.add_argument(
        "--skip-git-history-scan", action="store_true",
        help="only for interim focused iteration; full validation should scan",
    )
    args = parser.parse_args()
    try:
        report = run(
            mode=args.mode, output=args.output, log_dir=args.log_dir,
            skip_git_history_scan=args.skip_git_history_scan,
        )
    except (ValueError, OSError) as exc:
        print(
            json.dumps({"status": "BLOCKED", "reason": str(exc)}),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(
        {"status": report["status"], "mode": args.mode, "report": str(args.output),
         "checks": [{"name": r["name"], "status": r["status"]} for r in report["checks"]]},
        ensure_ascii=False,
    ))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
