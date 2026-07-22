#!/usr/bin/env python3
"""Run every repository-local test without exposing production credentials."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTERNAL_ENV_PROBES = {
    "test_gemini_real.py",
    "test_cloudflare_transcription_credentials.py",
    "test_cloudflare_transcription_smoke.py",
    "test_cloudinary_credentials.py",
    "test_cloudinary_upload_smoke.py",
    "test_sheets_connection.py",
    "test_threads_credentials.py",
    "test_x_credentials.py",
}
OPTIONAL_LOCAL_TOOL_PROBES = {
    "test_codegraph_installation.py",
    "test_context_mode_installation.py",
    "test_headroom_installation.py",
}
SENSITIVE_ENV_PARTS = ("SECRET", "TOKEN", "PASSWORD", "COOKIE", "STORAGE_STATE", "SA_JSON", "API_KEY")


def sanitized_environment() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if not any(part in key.upper() for part in SENSITIVE_ENV_PARTS)
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-external-probes", action="store_true")
    parser.add_argument("--pattern", default="", help="optional filename substring")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--json-output", default="")
    args = parser.parse_args()

    excluded = set(OPTIONAL_LOCAL_TOOL_PROBES)
    if not args.include_external_probes:
        excluded.update(EXTERNAL_ENV_PROBES)
    tests = [
        path
        for path in sorted((ROOT / "scripts").glob("test_*.py"))
        if path.name not in excluded and (not args.pattern or args.pattern in path.name)
    ]
    failures = []
    env = sanitized_environment()
    for index, path in enumerate(tests, start=1):
        try:
            run = subprocess.run(
                [sys.executable, str(path)],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                timeout=max(1, args.timeout_seconds),
                check=False,
            )
            if run.returncode:
                failures.append({
                    "test": path.name,
                    "exit_code": run.returncode,
                    "stdout_tail": "\n".join(run.stdout.splitlines()[-40:]),
                    "stderr_tail": "\n".join(run.stderr.splitlines()[-40:]),
                })
        except subprocess.TimeoutExpired:
            failures.append({"test": path.name, "exit_code": 124, "stdout_tail": "", "stderr_tail": "timeout"})
        if index % 50 == 0 or index == len(tests):
            print(f"progress={index}/{len(tests)} failures={len(failures)}", flush=True)

    result = {
        "status": "PASS" if not failures else "FAIL",
        "test_count": len(tests),
        "failed_count": len(failures),
        "excluded_external_probe_count": len(EXTERNAL_ENV_PROBES) if not args.include_external_probes else 0,
        "excluded_optional_local_tool_count": len(OPTIONAL_LOCAL_TOOL_PROBES),
        "failures": failures,
    }
    if args.json_output:
        Path(args.json_output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
