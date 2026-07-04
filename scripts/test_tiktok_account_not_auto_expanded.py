#!/usr/bin/env python3
import json
from pathlib import Path

from prepare_pilot_sources import exclusion_reason

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    sources = json.loads((ROOT / "config/source_accounts/default_sources.json").read_text(encoding="utf-8"))["sources"]
    rows = [s for s in sources if str(s.get("source_id", "")).startswith("src_lm_tt_user_")]
    ok = rows and all("/video/" not in s.get("source_url", "") and exclusion_reason(s, account_id="liver_manager", platform="tiktok") in {"manual_only_reference_source", "tiktok_requires_individual_video_url"} for s in rows)
    print(f"  {'PASS' if ok else 'FAIL'} TikTok account URLs are not auto-expanded")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
