#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IDS = {"src_lm_yt_user_001", "src_lm_tt_user_001", "src_lm_tt_user_002", "src_lm_tt_user_003"}


def main() -> int:
    sources = json.loads((ROOT / "config/source_accounts/default_sources.json").read_text(encoding="utf-8"))["sources"]
    rows = [s for s in sources if s.get("source_id") in IDS]
    ok = len(rows) == 4 and all(s.get("rights_status") == "third_party_reference_only" and s.get("can_reuse_media") is False and s.get("use_policy") == "REFERENCE_ONLY" for s in rows)
    print(f"  {'PASS' if ok else 'FAIL'} new liver sources reference only")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
