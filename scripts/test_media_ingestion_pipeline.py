"""
test_media_ingestion_pipeline.py - media_ingestion_pipeline テスト（Phase 7.C）

実ダウンロードなし / 実アップロードなし / Cloudinaryなし。
"""
from __future__ import annotations

import os
import sys

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_V2_ROOT, ".env"))
except ImportError:
    pass

_PASS = 0
_FAIL = 0


def _test(name: str, fn) -> None:
    global _PASS, _FAIL
    try:
        fn()
        print(f"  [PASS] {name}")
        _PASS += 1
    except Exception as e:
        print(f"  [FAIL] {name}: {e}")
        _FAIL += 1


def test_import():
    """media_ingestion_pipeline がインポートできる。"""
    from media.media_ingestion_pipeline import create_ingestion_plan
    assert callable(create_ingestion_plan)


def test_video_url_plan():
    """video_url のプランが作成できる。"""
    from media.media_ingestion_pipeline import create_ingestion_plan
    plan = create_ingestion_plan(
        account_id="night_scout",
        video_url="https://example.com/sample.mp4",
    )
    assert plan["asset_count"] == 1
    assert plan["assets"][0]["media_type"] == "video"
    assert plan["assets"][0]["source_type"] == "video_url"


def test_image_url_plan():
    """image_url のプランが作成できる。"""
    from media.media_ingestion_pipeline import create_ingestion_plan
    plan = create_ingestion_plan(
        account_id="night_scout",
        image_url="https://example.com/sample.jpg",
    )
    assert plan["asset_count"] == 1
    assert plan["assets"][0]["media_type"] == "image"


def test_no_input_error():
    """入力なしは ERROR になる。"""
    from media.media_ingestion_pipeline import create_ingestion_plan
    plan = create_ingestion_plan(account_id="night_scout")
    assert plan["status"] == "ERROR"


def test_cloudinary_upload_blocked_by_env():
    """ALLOW_CLOUDINARY_UPLOAD=false なら upload は BLOCKED。"""
    from media.media_ingestion_pipeline import create_ingestion_plan
    plan = create_ingestion_plan(
        account_id="night_scout",
        video_url="https://example.com/sample.mp4",
        allow_cloudinary_upload=False,
        confirm_upload=False,
        allow_download=True,
        confirm_download=True,
    )
    asset = plan["assets"][0]
    assert "BLOCKED" in asset["upload_status"], (
        f"Cloudinary upload が BLOCKED でない: {asset['upload_status']}"
    )


def test_no_download_blocked():
    """--download なし の外部URL は BLOCKED_NO_DOWNLOAD_PERMISSION になる。"""
    from media.media_ingestion_pipeline import create_ingestion_plan
    plan = create_ingestion_plan(
        account_id="night_scout",
        video_url="https://example.com/sample.mp4",
        allow_download=False,
        confirm_download=False,
    )
    asset = plan["assets"][0]
    assert asset["upload_status"] == "BLOCKED_NO_DOWNLOAD_PERMISSION", (
        f"予期しない upload_status: {asset['upload_status']}"
    )


def test_high_reuse_risk_blocked():
    """rights_status=unknown は reuse_risk=high → upload_status に BLOCKED が含まれる。"""
    from media.media_ingestion_pipeline import create_ingestion_plan
    plan = create_ingestion_plan(
        account_id="night_scout",
        video_url="https://example.com/sample.mp4",
        rights_status="unknown",
        allow_download=True,
        confirm_download=True,
        allow_cloudinary_upload=True,
        confirm_upload=True,
    )
    asset = plan["assets"][0]
    assert asset["reuse_risk"] == "high", f"unknown rights の reuse_risk が high でない: {asset['reuse_risk']}"
    assert "BLOCKED" in asset["upload_status"], (
        f"high reuse_risk でも BLOCKED でない: {asset['upload_status']}"
    )


def test_waiting_review_for_unknown_rights():
    """rights_status=unknown のアセットは status=WAITING_REVIEW。"""
    from media.media_ingestion_pipeline import create_ingestion_plan
    plan = create_ingestion_plan(
        account_id="night_scout",
        video_url="https://example.com/video.mp4",
        rights_status="unknown",
    )
    for asset in plan["assets"]:
        assert asset["status"] == "WAITING_REVIEW", (
            f"rights=unknown でも WAITING_REVIEW でない: {asset['status']}"
        )


def test_local_file_not_found():
    """存在しない local_file は LOCAL_FILE_NOT_FOUND になる。"""
    from media.media_ingestion_pipeline import create_ingestion_plan
    plan = create_ingestion_plan(
        account_id="night_scout",
        local_file="/nonexistent/path/video.mp4",
    )
    asset = plan["assets"][0]
    assert asset["upload_status"] == "LOCAL_FILE_NOT_FOUND", (
        f"存在しない local_file の upload_status が正しくない: {asset['upload_status']}"
    )


def test_media_type_detection():
    """ファイル拡張子からメディアタイプが推定できる。"""
    from media.media_ingestion_pipeline import _detect_media_type
    assert _detect_media_type("video.mp4") == "video"
    assert _detect_media_type("image.jpg") == "image"
    assert _detect_media_type("photo.png") == "image"
    assert _detect_media_type("clip.mov") == "video"


def test_fixture_exists():
    """sample_media_ingestion_plan.json が存在する。"""
    path = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_media_ingestion_plan.json")
    assert os.path.isfile(path), "fixture が見つかりません"


def test_no_real_download_upload():
    """実ダウンロード・実アップロードが実行されないことを確認。"""
    from media.media_ingestion_pipeline import create_ingestion_plan
    # デフォルトパラメータでは download も upload も行われない
    plan = create_ingestion_plan(
        account_id="night_scout",
        video_url="https://example.com/sample.mp4",
    )
    # BLOCKED_NO_DOWNLOAD_PERMISSION があることでダウンロードしていないことを確認
    assert any("BLOCKED" in a["upload_status"] for a in plan["assets"])


if __name__ == "__main__":
    print("=" * 65)
    print("  test_media_ingestion_pipeline.py")
    print("=" * 65)

    _test("import", test_import)
    _test("video_url_plan", test_video_url_plan)
    _test("image_url_plan", test_image_url_plan)
    _test("no_input_error", test_no_input_error)
    _test("cloudinary_upload_blocked_by_env", test_cloudinary_upload_blocked_by_env)
    _test("no_download_blocked", test_no_download_blocked)
    _test("high_reuse_risk_blocked", test_high_reuse_risk_blocked)
    _test("waiting_review_for_unknown_rights", test_waiting_review_for_unknown_rights)
    _test("local_file_not_found", test_local_file_not_found)
    _test("media_type_detection", test_media_type_detection)
    _test("fixture_exists", test_fixture_exists)
    _test("no_real_download_upload", test_no_real_download_upload)

    print(f"\n{'=' * 65}")
    print(f"  PASS={_PASS}  FAIL={_FAIL}")
    print("=" * 65)
    if _FAIL > 0:
        sys.exit(1)
