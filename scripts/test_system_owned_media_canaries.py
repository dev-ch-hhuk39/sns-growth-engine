#!/usr/bin/env python3
from run_system_owned_media_canaries import build_specs
from pathlib import Path

for account in ("night_scout", "liver_manager"):
    specs = build_specs(account, Path("/tmp/system-owned-media-test"))
    assert {item["kind"] for item in specs} == {"direct_image", "direct_carousel", "direct_video", "generated_clip"}
    assert all(item["text"] and item["canary_id"].startswith(f"canary_{account}") for item in specs)
print("PASS")
