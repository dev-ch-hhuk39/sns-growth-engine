#!/usr/bin/env python3
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("run_autonomous_loop", ROOT / "scripts/run_autonomous_loop.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def main() -> int:
    night = mod.build_autonomous_plan("night_scout")
    liver = mod.build_autonomous_plan("liver_manager")
    ok = night["selected_account"] == "night_scout" and liver["selected_account"] == "liver_manager"
    print(f"  {'PASS' if ok else 'FAIL'} account-specific workflow overrides rotation")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
