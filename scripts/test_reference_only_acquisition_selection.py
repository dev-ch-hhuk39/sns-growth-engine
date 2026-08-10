#!/usr/bin/env python3
"""Reference collection must not require direct-media permission."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts" / "acquire_approved_source_posts.py"
spec = importlib.util.spec_from_file_location("acquisition", PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def main() -> int:
    sources, blocked = module.selected_sources("liver_manager", "threads", reference_only=True)
    ids = {row["source_id"] for row in sources}
    policy = module.reference_only_permission(next(row for row in sources if row["source_id"] == "src_lm_threads_user_me01_lsm"))
    checks = [
        ("me01 Threads reference is selected", "src_lm_threads_user_me01_lsm" in ids),
        ("reference fetch does not need media ledger", not any(row["source_id"] == "src_lm_threads_user_me01_lsm" for row in blocked)),
        ("reuse remains reference only", policy["rights_status"] == "reference_only"),
        ("permission never becomes approved", policy["permission_status"] == "reference_only"),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
