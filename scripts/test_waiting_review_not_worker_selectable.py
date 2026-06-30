#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("process_threads_queue", ROOT / "scripts/process_threads_queue.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    mod = _load()
    checks = [
        ("READYのみeligible", mod.ELIGIBLE_STATUSES == {"READY"}),
        ("WAITING_REVIEW非対象", "WAITING_REVIEW" not in mod.ELIGIBLE_STATUSES),
        ("DRAFT非対象", "DRAFT" not in mod.ELIGIBLE_STATUSES),
    ]
    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {n}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
