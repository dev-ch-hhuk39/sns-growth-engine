#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IDS = {"src_lm_yt_user_001", "src_lm_tt_user_001", "src_lm_tt_user_002", "src_lm_tt_user_003"}


def main() -> int:
    sources = json.loads((ROOT / "config/source_accounts/default_sources.json").read_text(encoding="utf-8"))["sources"]
    rows = [s for s in sources if s.get("source_id") in IDS]
    ok = len(rows) == 4 and all(s.get("media_pipeline_eligible") is False and s.get("clip_enabled") is False and s.get("media_download") is False for s in rows)
    print(f"  {'PASS' if ok else 'FAIL'} new liver sources no media pipeline")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
