#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main() -> int:
    rows = json.loads((ROOT / "config/source_accounts/default_sources.json").read_text())["sources"]
    third = [s for s in rows if str(s.get("rights_status") or s.get("rights_policy")) == "third_party_reference_only"]
    ok = all(s.get("media_pipeline_eligible") is not True and s.get("can_reuse_media") is not True for s in third)
    print(f"  {'PASS' if ok else 'FAIL'} third-party sources still block media pipeline")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
