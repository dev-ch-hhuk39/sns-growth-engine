#!/usr/bin/env python3
import json
from pathlib import Path
from discover_approved_source_videos import build_discovery_plan
from generation.media_platform_policy import PHYSICAL_MEDIA_PLATFORMS, REFERENCE_PLATFORMS

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    plan = build_discovery_plan("liver_manager")
    tiktok_media_rows = [r for r in plan["source_results"] if str(r.get("platform", "")).lower() == "tiktok"]
    routing = json.loads((ROOT / "config/source_backend_routing.json").read_text(encoding="utf-8"))
    route = routing["routes"]["tiktok.profile_posts"]
    ok = (
        "tiktok" in REFERENCE_PLATFORMS
        and "tiktok" in PHYSICAL_MEDIA_PLATFORMS
        and not tiktok_media_rows
        and route["primary"] == "tiktok_public_embed"
        and route.get("fallbacks") == ["tiktok_gallery_dl"]
    )
    print(f"  {'PASS' if ok else 'FAIL'} tiktok bounded discovery and owner-gated physical media are enabled")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
