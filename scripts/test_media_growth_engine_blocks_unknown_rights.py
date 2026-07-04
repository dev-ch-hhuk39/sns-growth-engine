#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from media.rights_policy import rights_allows_media_use

def main() -> int:
    ok = not rights_allows_media_use("unknown") and not rights_allows_media_use("third_party_reference_only")
    print(f"  {'PASS' if ok else 'FAIL'} media growth blocks unknown rights")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
