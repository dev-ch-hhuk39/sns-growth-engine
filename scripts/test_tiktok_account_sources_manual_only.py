#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    sources = json.loads((ROOT / "config/source_accounts/default_sources.json").read_text(encoding="utf-8"))["sources"]
    rows = [s for s in sources if str(s.get("source_id", "")).startswith("src_lm_tt_user_")]
    ok = len(rows) == 3 and all(
        s.get("manual_only") is False
        and s.get("source_type") == "account"
        and int(s.get("max_items_per_run") or 0) <= 3
        for s in rows
    )
    print(f"  {'PASS' if ok else 'FAIL'} TikTok account discovery is automatic and bounded")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
