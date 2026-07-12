#!/usr/bin/env python3
from media_post_validator import validate_media_post

TEXT = "夜職で店を選ぶ時、時給だけで決めると続かなくなることがあります。\n\n客層、ノルマ、出勤のしやすさ、相談できる人がいるか。\n条件を並べて、自分が無理なく続けられる場所かを見てみてください。"

result = validate_media_post({
    "rights_status": "approved_creator_clip",
    "permission_status": "approved",
    "media_url": "https://cdn.example/night.mp4",
    "media_asset_id": "night_asset",
    "platform": "threads",
    "account_id": "night_scout",
    "media_type": "video",
    "duration_seconds": 20,
    "aspect_ratio": "9:16",
    "public_post_text": TEXT,
})
ok = result["status"] == "PASS"
print(f"  {'PASS' if ok else 'FAIL'} night_scout approved media post passes validator")
print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
raise SystemExit(0 if ok else 1)
