#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acquisition.contracts import ProviderResult


def main() -> int:
    checks = []
    passed = ProviderResult("fixture", "1", "PASS", data=[1])
    checks.append(("PASS result is usable", passed.ok and passed.data == [1]))
    blocked = ProviderResult("fixture", "1", "BLOCKED", reason="policy")
    checks.append(("BLOCKED result is fail closed", not blocked.ok))
    try:
        ProviderResult("fixture", "1", "PASS", metadata={"token": "never"})
        sensitive_blocked = False
    except ValueError:
        sensitive_blocked = True
    checks.append(("sensitive provider metadata is rejected", sensitive_blocked))
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    failed = [name for name, ok in checks if not ok]
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
