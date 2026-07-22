#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("run_autonomous_loop", ROOT / "scripts/run_autonomous_loop.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def main() -> int:
    cfg = mod.load_autonomous_config()
    blocked = mod.original_text_similarity_guard("同じ文章です", "同じ文章です", threshold=cfg["max_similarity_to_source"])
    ok = cfg["max_similarity_to_source"] == 0.45 and blocked["status"] == "BLOCKED"
    print(f"  {'PASS' if ok else 'FAIL'} similarity guard")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
