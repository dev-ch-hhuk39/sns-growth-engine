#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    cfg = json.loads((ROOT / "config/autonomous_mode.json").read_text(encoding="utf-8"))
    ok = cfg.get("allowed_platforms_for_post") == ["threads"] and "x" in cfg.get("blocked_platforms_for_post", [])
    print(f"  {'PASS' if ok else 'FAIL'} x post blocked")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
