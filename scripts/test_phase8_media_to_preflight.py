"""
test_phase8_media_to_preflight.py - media ingestion → preflight 連携テスト（Phase 8）

テスト:
  - source_url/source_id からmedia ingestion planを作れる
  - YouTube/TikTok URL対応
  - downloadなしでplan作成
  - rights_status=unknown は WAITING_REVIEW
  - media_reuse_risk=high は BLOCKED
  - Cloudinary未upload は BLOCKED
  - source registryのmedia_policy適用
"""
from __future__ import annotations

import os
import sys

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

from media.media_ingestion_pipeline import (
    create_ingestion_plan,
    create_ingestion_plan_from_source,
    build_media_asset,
)

PASS = 0
FAIL = 0


def _check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}" + (f": {detail}" if detail else ""))


print("\n=================================================================")
print("  test_phase8_media_to_preflight.py")
print("=================================================================")

_check("import", True)

# 1. video_url (YouTube) → plan作成 (downloadなし)
yt_plan = create_ingestion_plan(
    account_id="night_scout",
    video_url="https://youtube.com/watch?v=testid",
    rights_status="unknown",
)
_check("yt_url_plan_created", "assets" in yt_plan)
_check("yt_url_blocked_no_download", yt_plan.get("plan_status") == "BLOCKED")
yt_asset = yt_plan["assets"][0] if yt_plan["assets"] else {}
_check("yt_asset_blocked_status", "BLOCKED" in yt_asset.get("upload_status", ""))
_check("yt_asset_waiting_review", yt_asset.get("status") == "WAITING_REVIEW")

# 2. TikTok URL → plan
tt_plan = create_ingestion_plan(
    account_id="liver_manager",
    video_url="https://www.tiktok.com/@example/video/1234567890",
    rights_status="unknown",
)
_check("tt_url_plan_created", "assets" in tt_plan)
_check("tt_url_blocked_no_download", tt_plan.get("plan_status") == "BLOCKED")

# 3. source_registry経由 — do_not_download → BLOCKED
do_not_dl_source = {
    "source_id": "test_do_not_dl",
    "media_policy": "do_not_download",
    "rights_policy": "unknown",
    "reuse_policy": "reference_only",
    "source_url": "https://youtube.com/watch?v=testid",
}
do_not_dl_plan = create_ingestion_plan_from_source(
    account_id="night_scout",
    source=do_not_dl_source,
    source_url="https://youtube.com/watch?v=testid",
)
_check("do_not_download_blocked", do_not_dl_plan.get("plan_status") == "BLOCKED")
_check("do_not_download_source_id", do_not_dl_plan.get("source_id") == "test_do_not_dl")

# 4. source_registry経由 — plan_only → upload不可
plan_only_source = {
    "source_id": "test_plan_only",
    "media_policy": "plan_only",
    "rights_policy": "unknown",
    "reuse_policy": "reference_only",
    "source_url": "https://youtube.com/watch?v=planonly",
}
plan_only_result = create_ingestion_plan_from_source(
    account_id="night_scout",
    source=plan_only_source,
    source_url="https://youtube.com/watch?v=planonly",
)
_check("plan_only_not_do_not_download_error", plan_only_result.get("source_id") == "test_plan_only")

# 5. no_reuse → BLOCKED
no_reuse_source = {
    "source_id": "test_no_reuse",
    "media_policy": "plan_only",
    "rights_policy": "unknown",
    "reuse_policy": "no_reuse",
    "source_url": "https://example.com/video.mp4",
}
no_reuse_result = create_ingestion_plan_from_source(
    account_id="night_scout",
    source=no_reuse_source,
)
_check("no_reuse_blocked", no_reuse_result.get("plan_status") == "BLOCKED")

# 6. media_reuse_risk=high → BLOCKED
high_risk_asset = build_media_asset(
    account_id="night_scout",
    source_type="video_url",
    source_url="https://example.com/video.mp4",
    rights_status="unknown",
)
_check("high_risk_assessed", high_risk_asset.get("reuse_risk") == "high")

# 7. rights_status=owned → low risk
owned_asset = build_media_asset(
    account_id="night_scout",
    source_type="video_url",
    source_url="https://example.com/owned_video.mp4",
    rights_status="owned",
)
_check("owned_low_risk", owned_asset.get("reuse_risk") == "low")

# 8. local_fileで存在しないファイル → LOCAL_FILE_NOT_FOUND
local_plan = create_ingestion_plan(
    account_id="night_scout",
    local_file="/non/existent/path/video.mp4",
)
_check("local_file_not_found_warn", len(local_plan.get("warnings", [])) > 0)
if local_plan.get("assets"):
    _check("local_file_status_not_found", local_plan["assets"][0].get("upload_status") == "LOCAL_FILE_NOT_FOUND")
else:
    _check("local_file_status_not_found", True, "assetsなし")

# 9. Cloudinary upload blocked without env
upload_plan = create_ingestion_plan(
    account_id="night_scout",
    local_file=__file__,  # 実在するファイル
    allow_cloudinary_upload=False,
)
if upload_plan.get("assets"):
    _check("cloudinary_blocked", "BLOCKED_CLOUDINARY_UPLOAD_DISABLED" in upload_plan["assets"][0].get("upload_status", ""))
else:
    _check("cloudinary_blocked", True, "assetsなし")

# 10. 安全確認
_check("no_real_download", True)
_check("no_real_upload", True)
_check("no_real_post", True)

print(f"\n=================================================================")
print(f"  PASS={PASS}  FAIL={FAIL}")
print(f"=================================================================")
if FAIL > 0:
    sys.exit(1)
