#!/usr/bin/env python3
"""AUTOPOST pilot requires config, env, confirm, and no skip-real-post."""
from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run_autopilot_loop.py"


def _load():
    spec = importlib.util.spec_from_file_location("run_autopilot_loop_for_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def gate(mod, *, auto_post=False, enabled=False, env=False, confirm=False, skip=True):
    prev = {k: os.environ.get(k) for k in ("PUBLISH_ENABLED", "ALLOW_REAL_THREADS_POST")}
    try:
        if env:
            os.environ["PUBLISH_ENABLED"] = "true"
            os.environ["ALLOW_REAL_THREADS_POST"] = "true"
        else:
            os.environ.pop("PUBLISH_ENABLED", None)
            os.environ.pop("ALLOW_REAL_THREADS_POST", None)
        args = argparse.Namespace(auto_post=auto_post, confirm_real_post=confirm, skip_real_post=skip)
        return mod.auto_post_gate(args, {"defaults": {"auto_post_enabled": enabled}})
    finally:
        for key, value in prev.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def main() -> int:
    mod = _load()
    checks = [
        ("not requested blocked", gate(mod, enabled=True, env=True, confirm=True, skip=False)["allowed"] is False),
        ("config disabled blocked", gate(mod, auto_post=True, env=True, confirm=True, skip=False)["allowed"] is False),
        ("env missing blocked", gate(mod, auto_post=True, enabled=True, confirm=True, skip=False)["allowed"] is False),
        ("confirm missing blocked", gate(mod, auto_post=True, enabled=True, env=True, skip=False)["allowed"] is False),
        ("skip real post blocks", gate(mod, auto_post=True, enabled=True, env=True, confirm=True, skip=True)["allowed"] is False),
        ("all gates allow", gate(mod, auto_post=True, enabled=True, env=True, confirm=True, skip=False)["allowed"] is True),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
