#!/usr/bin/env python3
import run_system_owned_media_canaries as media_canaries
from pathlib import Path


video_calls = []


def fake_video(image_path, output_path, *, seconds, clip=False):
    video_calls.append((image_path, output_path, seconds, clip))
    output_path.write_bytes(b"test-video")


media_canaries._video = fake_video

for account in ("night_scout", "liver_manager"):
    specs = media_canaries.build_specs(account, Path("/tmp/system-owned-media-test"))
    assert {item["kind"] for item in specs} == {"direct_image", "direct_carousel", "direct_video", "generated_clip"}
    assert all(item["text"] and item["canary_id"].startswith(f"canary_fresh_{account}_") for item in specs)
    assert len({item["text"] for item in specs}) == len(specs)
assert [(seconds, clip) for _, _, seconds, clip in video_calls] == [(10, False), (8, True), (10, False), (8, True)]
assert '"clip_candidate_id": clip_id' in Path(media_canaries.__file__).read_text(encoding="utf-8")
print("PASS")
