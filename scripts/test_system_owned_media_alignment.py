#!/usr/bin/env python3
from pathlib import Path
import run_system_owned_media_canaries as media

media._video = lambda _image, output, **_kwargs: output.write_bytes(b"fresh-video")
specs = media.build_specs("night_scout", Path("/tmp/system-owned-alignment"), batch_id="fresh_alignment_test")
by_kind = {item["kind"]: item for item in specs}
assert by_kind["direct_video"]["files"][0].name == "short.mp4"
assert by_kind["generated_clip"]["files"][0].name == "clip.mp4"
assert by_kind["direct_video"]["alignment"]["storyboard"] != by_kind["generated_clip"]["alignment"]["storyboard"]
assert all(item["alignment"]["alignment_status"] == "PASS" for item in specs)
print("PASS test_system_owned_media_alignment.py")
