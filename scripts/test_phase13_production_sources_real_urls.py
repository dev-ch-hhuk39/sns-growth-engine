#!/usr/bin/env python3
"""Verify user-provided production source URLs are fully reflected."""
from __future__ import annotations

import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES_FILE = os.path.join(_ROOT, "config", "source_accounts", "production_sources.example.json")

EXPECTED_URLS = {
    "https://x.com/takashimaanna", "https://x.com/minatoku789", "https://x.com/kyaba_career",
    "https://x.com/kyabataihendane", "https://x.com/amuxamudaily", "https://x.com/1okukure_",
    "https://x.com/onigiriscout_0", "https://x.com/urarament", "https://x.com/3j2c9q",
    "https://www.youtube.com/channel/UCh7IsMrygg8X4hEJe8mUcQw", "https://www.youtube.com/@sakuraimizuki",
    "https://www.youtube.com/@shingekinoa3485", "https://www.youtube.com/channel/UC_GIhz5Cvb1NANQr_QPsnpA",
    "https://www.youtube.com/channel/UCbclA18j8r-O1LyzTVpnI-A", "https://www.youtube.com/@ichijo_hibiki",
    "https://www.youtube.com/@ClubUNJOURTOKYO", "https://www.youtube.com/@miyuchannel1108",
    "https://www.youtube.com/@kyaba_camera/", "https://www.youtube.com/@suu-san_pococha",
    "https://www.youtube.com/@nanachan7pococha", "https://www.youtube.com/playlist?list=PLc2iRTy3vD2ES8qEy3RdcHIavU7AMf8by",
    "https://www.youtube.com/@%E3%83%A9%E3%82%A4%E3%83%90%E3%83%BC%E7%A0%94%E7%A9%B6%E6%89%80%E3%83%A9%E3%82%A4%E3%83%96%E3%83%8A%E3%82%A6",
    "https://www.youtube.com/@yukidora", "https://www.youtube.com/@yukidora/streams", "https://www.youtube.com/@amaneri333",
    "https://note.com/mitsuakisusa", "https://note.com/taitan_118", "https://note.com/taitan_118/n/nf70121f2fda2",
    "https://note.com/tiktok_live/all", "https://note.com/libertas_group", "https://note.com/libertas_group/n/n4349020204a7",
    "https://www.youtube.com/@CosmeWotaSara", "https://www.youtube.com/channel/UCffg7iYU2K7HFJDhylZzUBw",
    "https://www.youtube.com/@hirobeautychannel", "https://www.youtube.com/@aratatomori", "https://www.youtube.com/@775nanako",
    "https://www.youtube.com/@fukurena", "https://www.youtube.com/@yui_yanagihashi", "https://www.youtube.com/@saaya3831",
    "https://www.youtube.com/@shikanoma", "https://www.youtube.com/@arichan_make", "https://www.tiktok.com/@egachannel1",
    "https://www.tiktok.com/@miwa_asmr", "https://www.tiktok.com/@mote_cosme", "https://www.tiktok.com/@machimachi_877",
    "https://www.tiktok.com/@snam8_", "https://www.tiktok.com/@shushu_223_", "https://www.tiktok.com/@coscoslife",
    "https://x.com/saraparin", "https://x.com/hondayuni", "https://x.com/mochi__cosme", "https://x.com/fortune_sachiko",
    "https://x.com/chicoecco", "https://x.com/soi_beauty",
}


def main() -> int:
    with open(SOURCES_FILE, encoding="utf-8") as f:
        sources = json.load(f)["sources"]
    text = json.dumps(sources, ensure_ascii=False)
    urls = {s.get("source_url", "") for s in sources if s.get("source_url")}
    missing = sorted(EXPECTED_URLS - urls)
    placeholder = "REPLACE_WITH_REAL" in text
    unsafe = [s["source_id"] for s in sources if s.get("active") or s.get("fetch_enabled")]
    print("=== Phase13 production real URL audit ===")
    print(f"expected={len(EXPECTED_URLS)} present={len(EXPECTED_URLS)-len(missing)} placeholders={placeholder}")
    if missing:
        print("missing:", missing[:10])
    if unsafe:
        print("unsafe active/fetch_enabled:", unsafe[:10])
    ok = not missing and not placeholder and not unsafe
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
