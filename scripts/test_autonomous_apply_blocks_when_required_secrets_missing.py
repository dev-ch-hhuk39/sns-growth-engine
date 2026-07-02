#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("run_autonomous_loop", ROOT / "scripts/run_autonomous_loop.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def main() -> int:
    keys = [
        "SNS_MASTER_SHEET_ID", "NOTE_MASTER_SHEET_ID", "SPREADSHEET_ID",
        "SA_JSON_BASE64", "GCP_SA_JSON", "GCP_SA_JSON_BASE64",
        "THREADS_ACCESS_TOKEN", "THREADS_USER_ID",
        "THREADS_ACCESS_TOKEN_NIGHT_SCOUT", "THREADS_USER_ID_NIGHT_SCOUT",
        "THREADS_ACCESS_TOKEN_LIVER_MANAGER", "THREADS_USER_ID_LIVER_MANAGER",
        "THREADS_TOKEN_STORE_DIR",
    ]
    old = {k: os.environ.get(k) for k in keys}
    try:
        for k in keys:
            os.environ[k] = ""
        os.environ["THREADS_TOKEN_STORE_DIR"] = "/tmp/sns-growth-engine-no-token-store"
        preflight = mod.apply_preflight(mod.build_autonomous_plan("all"))
        ok = preflight["ok"] is False and preflight["blocked_reasons"]
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    print(f"  {'PASS' if ok else 'FAIL'} apply blocks when required secrets missing")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
