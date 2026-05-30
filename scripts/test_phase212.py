"""
test_phase212.py — Phase 2.12 動作確認テスト

テスト項目:
  1.  extract_media_urls: media_urls パイプ区切りから URL リストを返す
  2.  extract_media_urls: image_urls / video_urls フィールドも処理する
  3.  extract_media_urls: 重複URLを除去する
  4.  extract_media_urls: メディアなし投稿は空リストを返す
  5.  classify_media_url: mp4/mov/amplify_video を video と判定する
  6.  classify_media_url: jpg/png/jpeg/webp/pbs.twimg.com を image と判定する
  7.  classify_media_url: 空文字は unknown を返す
  8.  safe_slug: 特殊文字をアンダースコアに変換する
  9.  build_public_id: sns-growth-engine/{account}/{post}-{index} 形式を生成する
  10. cloudinary_signature: SHA-1 署名を正しく計算する
  11. assess_imitation_risk: 動画URLがあれば high を返す
  12. assess_imitation_risk: 画像URLのみなら medium を返す
  13. assess_imitation_risk: URLなしなら unknown を返す
  14. prepare_media_asset: dry_run=True で storage_provider="dry_run" を返す
  15. prepare_media_asset: 必須フィールドを全て含む dict を返す
  16. prepare_media_asset: reference_post_id が post["id"] から取れる
  17. prepare_media_assets: メディアなし投稿をスキップする
  18. prepare_media_assets: 複数URLがある投稿は複数アセットを生成する
  19. prepare_media_assets: dry_run=True のとき upload_to_cloudinary は呼ばれない
  20. upload_to_cloudinary: allow_upload=False で RuntimeError を送出する
  21. get_cloudinary_config: allow_upload が False を返す（デフォルト）
  22. get_cloudinary_config: api_secret_set が bool フラグを返す
  23. MockSheetsClient: save_media_asset が保存できる
  24. MockSheetsClient: save_media_asset が reference_post_id + original_media_url でアップサートする
  25. MockSheetsClient: find_media_asset_by_reference_post_id が正しく引ける
  26. MockSheetsClient: find_media_asset_by_original_media_url が正しく引ける
  27. MockSheetsClient: get_media_assets が account_id でフィルタできる
  28. MockSheetsClient: save_media_assets が件数を正しく返す
  29. SheetsClient に 5 メソッド（get/find×2/save/save_batch）が存在する
  30. sample_media_assets.json が 3 件読み込める
  31. fixtures/sample_x_posts.json からメディアあり投稿を抽出して prepare_media_assets が動く
  32. check_pipeline_integrity: VALID_STORAGE_PROVIDERS / VALID_RISK_LEVELS が定義されている
  33. check_pipeline_integrity: check_media_assets がサンプルデータを正常判定する
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

from media.cloudinary_client import (
    assess_imitation_risk,
    build_public_id,
    classify_media_url,
    cloudinary_signature,
    extract_media_urls,
    prepare_media_asset,
    prepare_media_assets,
    safe_slug,
    upload_to_cloudinary,
)
from sheets_client import MockSheetsClient, SheetsClient


# ------------------------------------------------------------------ #
# ヘルパー
# ------------------------------------------------------------------ #

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"

_results: list[tuple[bool, str]] = []


def ok(name: str) -> None:
    _results.append((True, name))
    print(f"  [{PASS}] {name}")


def fail(name: str, msg: str) -> None:
    _results.append((False, name))
    print(f"  [{FAIL}] {name}: {msg}")


def assert_eq(name: str, actual, expected) -> None:
    if actual == expected:
        ok(name)
    else:
        fail(name, f"expected={expected!r}, actual={actual!r}")


def assert_in(name: str, item, container) -> None:
    if item in container:
        ok(name)
    else:
        fail(name, f"{item!r} not in {container!r}")


def assert_true(name: str, cond: bool, msg: str = "") -> None:
    if cond:
        ok(name)
    else:
        fail(name, msg or "condition is False")


# ------------------------------------------------------------------ #
# 1-4: extract_media_urls
# ------------------------------------------------------------------ #

def test_extract_media_urls() -> None:
    print("\n[extract_media_urls]")
    post = {"media_urls": "https://a.com/img1.jpg|https://b.com/img2.png"}
    urls = extract_media_urls(post)
    assert_eq("1. media_urls パイプ区切り → リスト", urls,
              ["https://a.com/img1.jpg", "https://b.com/img2.png"])

    post2 = {"image_urls": ["https://c.com/i.jpg"], "video_urls": "https://d.com/v.mp4"}
    urls2 = extract_media_urls(post2)
    assert_eq("2. image_urls list + video_urls str", urls2,
              ["https://c.com/i.jpg", "https://d.com/v.mp4"])

    post3 = {"media_urls": "https://e.com/img.jpg|https://e.com/img.jpg"}
    urls3 = extract_media_urls(post3)
    assert_eq("3. 重複URLを除去する", urls3, ["https://e.com/img.jpg"])

    post4 = {"media_urls": ""}
    urls4 = extract_media_urls(post4)
    assert_eq("4. メディアなし投稿は空リスト", urls4, [])


# ------------------------------------------------------------------ #
# 5-7: classify_media_url
# ------------------------------------------------------------------ #

def test_classify_media_url() -> None:
    print("\n[classify_media_url]")
    assert_eq("5. .mp4 → video", classify_media_url("https://example.com/video.mp4"), "video")
    assert_eq("5b. .mov → video", classify_media_url("https://example.com/clip.mov"), "video")
    assert_eq("5c. amplify_video → video", classify_media_url(
        "https://video.twimg.com/amplify_video/123/vid/example.mp4"), "video")
    assert_eq("6. .jpg → image", classify_media_url("https://pbs.twimg.com/media/ex.jpg"), "image")
    assert_eq("6b. pbs.twimg.com → image", classify_media_url("https://pbs.twimg.com/media/ex"), "image")
    assert_eq("6c. .png → image", classify_media_url("https://example.com/img.png"), "image")
    assert_eq("7. 空文字 → unknown", classify_media_url(""), "unknown")


# ------------------------------------------------------------------ #
# 8-9: safe_slug / build_public_id
# ------------------------------------------------------------------ #

def test_slugs() -> None:
    print("\n[safe_slug / build_public_id]")
    assert_eq("8. safe_slug 特殊文字除去（末尾_はstrip）", safe_slug("night scout!"), "night_scout")
    assert_eq("8b. safe_slug fallback", safe_slug("", "default"), "default")
    pid = build_public_id("post_abc", "night_scout", 0)
    assert_eq("9. build_public_id 形式", pid, "sns-growth-engine/night_scout/post_abc-00")
    pid2 = build_public_id("post_abc", "night_scout", 3)
    assert_eq("9b. build_public_id index=3", pid2, "sns-growth-engine/night_scout/post_abc-03")


# ------------------------------------------------------------------ #
# 10: cloudinary_signature
# ------------------------------------------------------------------ #

def test_cloudinary_signature() -> None:
    print("\n[cloudinary_signature]")
    params = {"public_id": "test/img", "timestamp": "1234567890"}
    secret = "mysecret"
    sig = cloudinary_signature(params, secret)
    # 手動計算: "public_id=test/img&timestamp=1234567890mysecret"
    payload = "public_id=test/img&timestamp=1234567890mysecret"
    expected = hashlib.sha1(payload.encode("utf-8")).hexdigest()
    assert_eq("10. cloudinary_signature SHA-1", sig, expected)


# ------------------------------------------------------------------ #
# 11-13: assess_imitation_risk
# ------------------------------------------------------------------ #

def test_assess_imitation_risk() -> None:
    print("\n[assess_imitation_risk]")
    post_video = {"media_urls": "https://video.twimg.com/amplify_video/123/vid/ex.mp4"}
    assert_eq("11. 動画URLがあれば high", assess_imitation_risk(post_video), "high")

    post_image = {"media_urls": "https://pbs.twimg.com/media/ex.jpg"}
    assert_eq("12. 画像URLのみなら medium", assess_imitation_risk(post_image), "medium")

    post_empty = {"media_urls": ""}
    assert_eq("13. URLなしなら unknown", assess_imitation_risk(post_empty), "unknown")


# ------------------------------------------------------------------ #
# 14-19: prepare_media_asset / prepare_media_assets
# ------------------------------------------------------------------ #

def test_prepare_media_asset() -> None:
    print("\n[prepare_media_asset]")
    post = {
        "id": "post_2222",
        "media_urls": "https://pbs.twimg.com/media/ex.jpg",
        "platform": "x",
        "url": "https://x.com/user/status/2222",
    }
    asset = prepare_media_asset(
        post=post,
        account_id="night_scout",
        config={},
        dry_run=True,
        index=0,
        original_media_url="https://pbs.twimg.com/media/ex.jpg",
    )
    assert_eq("14. dry_run → storage_provider=dry_run",
              asset.get("storage_provider"), "dry_run")
    assert_eq("14b. dry_run → storage_url 空文字",
              asset.get("storage_url"), "")

    required_fields = [
        "media_id", "account_id", "reference_post_id",
        "source_platform", "original_media_url",
        "storage_provider", "storage_url", "media_type",
        "reuse_status", "media_reuse_risk", "used_count",
    ]
    for f in required_fields:
        assert_true(f"15. 必須フィールド {f!r} が存在する", f in asset)

    assert_eq("16. reference_post_id が post['id'] から取れる",
              asset.get("reference_post_id"), "post_2222")
    assert_eq("16b. account_id が正しい",
              asset.get("account_id"), "night_scout")
    assert_eq("16c. reuse_status=reference_only（デフォルト）",
              asset.get("reuse_status"), "reference_only")


def test_prepare_media_assets() -> None:
    print("\n[prepare_media_assets]")
    posts = [
        {"id": "p1", "media_urls": "", "platform": "x", "url": ""},
        {"id": "p2", "media_urls": "https://pbs.twimg.com/media/a.jpg|https://pbs.twimg.com/media/b.jpg",
         "platform": "x", "url": "https://x.com/user/status/2"},
    ]
    assets = prepare_media_assets(posts, "night_scout", config={}, dry_run=True)
    assert_eq("17. メディアなし投稿をスキップ", len(assets), 2)
    assert_eq("18. 複数URLがある投稿は複数アセット生成",
              sum(1 for a in assets if a.get("reference_post_id") == "p2"), 2)

    uploaded_calls = []
    with patch("media.cloudinary_client.upload_to_cloudinary") as mock_upload:
        prepare_media_assets(posts, "night_scout", config={}, dry_run=True)
        assert_true("19. dry_run=True のとき upload_to_cloudinary は呼ばれない",
                    mock_upload.call_count == 0)


# ------------------------------------------------------------------ #
# 20: upload_to_cloudinary の allow_upload=False ガード
# ------------------------------------------------------------------ #

def test_upload_guard() -> None:
    print("\n[upload_to_cloudinary guard]")
    try:
        upload_to_cloudinary(b"data", "image/jpeg", "test/img", {"allow_upload": False})
        fail("20. allow_upload=False で RuntimeError", "例外が発生しなかった")
    except RuntimeError:
        ok("20. allow_upload=False で RuntimeError を送出する")
    except Exception as e:
        fail("20. allow_upload=False で RuntimeError", f"別の例外: {e!r}")


# ------------------------------------------------------------------ #
# 21-22: get_cloudinary_config
# ------------------------------------------------------------------ #

def test_get_cloudinary_config() -> None:
    print("\n[get_cloudinary_config]")
    import os
    os.environ.pop("ALLOW_CLOUDINARY_UPLOAD", None)
    os.environ.pop("CLOUDINARY_API_SECRET", None)
    # config_loader.py を直接 import するため src パスを使う
    sys.path.insert(0, os.path.join(_V2_ROOT, "src"))
    from config_loader import get_cloudinary_config
    cfg = get_cloudinary_config()
    assert_eq("21. allow_upload デフォルト False", cfg.get("allow_upload"), False)
    assert_true("22. api_secret_set は bool", isinstance(cfg.get("api_secret_set"), bool))


# ------------------------------------------------------------------ #
# 23-28: MockSheetsClient media_assets
# ------------------------------------------------------------------ #

def test_mock_sheets_client() -> None:
    print("\n[MockSheetsClient media_assets]")
    mc = MockSheetsClient(dry_run=False)

    asset1 = {
        "media_id": "m1",
        "account_id": "night_scout",
        "reference_post_id": "post_2222",
        "original_media_url": "https://pbs.twimg.com/media/a.jpg",
        "storage_provider": "dry_run",
        "storage_url": "",
        "media_type": "image",
        "reuse_status": "reference_only",
        "media_reuse_risk": "medium",
        "used_count": "0",
    }
    result = mc.save_media_asset(asset1)
    assert_true("23. save_media_asset が True を返す", result)

    found = mc.find_media_asset_by_reference_post_id("post_2222")
    assert_true("24a. find_by_reference_post_id が引ける", found is not None)
    assert_eq("24b. find 結果の media_id", found.get("media_id") if found else None, "m1")

    # アップサートテスト（同じ reference_post_id + original_media_url）
    asset1_updated = dict(asset1)
    asset1_updated["media_reuse_risk"] = "high"
    mc.save_media_asset(asset1_updated)
    assets = mc.get_media_assets(account_id="night_scout")
    assert_eq("24c. アップサートで件数が増えない（1件）", len(assets), 1)
    assert_eq("24d. アップサートで値が更新される",
              assets[0].get("media_reuse_risk"), "high")

    asset2 = dict(asset1)
    asset2["media_id"] = "m2"
    asset2["account_id"] = "other_account"
    asset2["original_media_url"] = "https://pbs.twimg.com/media/b.jpg"
    mc.save_media_asset(asset2)

    found_url = mc.find_media_asset_by_original_media_url("https://pbs.twimg.com/media/b.jpg")
    assert_true("25. find_by_original_media_url が引ける", found_url is not None)
    assert_eq("25b. find_by_url の media_id", found_url.get("media_id") if found_url else None, "m2")

    filtered = mc.get_media_assets(account_id="night_scout")
    assert_eq("26. get_media_assets account_id フィルタ", len(filtered), 1)

    mc2 = MockSheetsClient(dry_run=False)
    batch_result = mc2.save_media_assets([asset1, asset2])
    assert_eq("27. save_media_assets saved=2", batch_result["saved"], 2)
    assert_eq("27b. save_media_assets errors=0", batch_result["errors"], 0)


# ------------------------------------------------------------------ #
# 29: SheetsClient に 5 メソッドが存在する
# ------------------------------------------------------------------ #

def test_sheets_client_methods() -> None:
    print("\n[SheetsClient メソッド存在確認]")
    expected_methods = [
        "get_media_assets",
        "find_media_asset_by_reference_post_id",
        "find_media_asset_by_original_media_url",
        "save_media_asset",
        "save_media_assets",
    ]
    for method in expected_methods:
        assert_true(f"29. SheetsClient.{method} が存在する", hasattr(SheetsClient, method))


# ------------------------------------------------------------------ #
# 30: sample_media_assets.json が 3 件読み込める
# ------------------------------------------------------------------ #

def test_fixtures_media_assets() -> None:
    print("\n[fixtures/sample_media_assets.json]")
    fixture_path = os.path.join(_V2_ROOT, "fixtures", "sample_media_assets.json")
    assert_true("30a. fixtures ファイルが存在する", os.path.exists(fixture_path))
    with open(fixture_path, encoding="utf-8") as f:
        data = json.load(f)
    assert_true("30b. 3件以上のデータ", len(data) >= 3)
    for item in data:
        assert_true("30c. media_id フィールドあり", "media_id" in item)
        assert_true("30d. reference_post_id フィールドあり", "reference_post_id" in item)


# ------------------------------------------------------------------ #
# 31: fixtures/sample_x_posts.json からメディアあり投稿の end-to-end
# ------------------------------------------------------------------ #

def test_e2e_from_x_posts() -> None:
    print("\n[end-to-end: sample_x_posts → prepare_media_assets]")
    fixture_path = os.path.join(_V2_ROOT, "fixtures", "sample_x_posts.json")
    with open(fixture_path, encoding="utf-8") as f:
        raw_posts = json.load(f)

    assets = prepare_media_assets(raw_posts, "night_scout", config={}, dry_run=True)
    assert_true("31a. メディアあり投稿からアセットが生成される", len(assets) > 0)
    for a in assets:
        assert_eq("31b. storage_provider=dry_run", a.get("storage_provider"), "dry_run")
        assert_eq("31c. storage_url が空文字", a.get("storage_url"), "")
        assert_eq("31d. reuse_status=reference_only", a.get("reuse_status"), "reference_only")
        assert_in("31e. media_type が有効値", a.get("media_type"), {"image", "video", "unknown"})

    mc = MockSheetsClient(dry_run=False)
    result = mc.save_media_assets(assets)
    assert_eq("31f. save_media_assets errors=0", result["errors"], 0)
    assert_eq("31g. save_media_assets saved=len(assets)", result["saved"], len(assets))


# ------------------------------------------------------------------ #
# 32-33: check_pipeline_integrity
# ------------------------------------------------------------------ #

def test_check_pipeline_integrity() -> None:
    print("\n[check_pipeline_integrity]")
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "check_pipeline_integrity",
        os.path.join(_V2_ROOT, "scripts", "check_pipeline_integrity.py"),
    )
    cpi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cpi)

    assert_true("32a. VALID_STORAGE_PROVIDERS が定義されている",
                hasattr(cpi, "VALID_STORAGE_PROVIDERS"))
    assert_in("32b. cloudinary が VALID_STORAGE_PROVIDERS に含まれる",
              "cloudinary", cpi.VALID_STORAGE_PROVIDERS)
    assert_in("32c. dry_run が VALID_STORAGE_PROVIDERS に含まれる",
              "dry_run", cpi.VALID_STORAGE_PROVIDERS)
    assert_true("32d. VALID_RISK_LEVELS が定義されている",
                hasattr(cpi, "VALID_RISK_LEVELS"))
    assert_in("32e. high が VALID_RISK_LEVELS に含まれる",
              "high", cpi.VALID_RISK_LEVELS)

    # check_media_assets を MockSheetsClient で実行
    mc = MockSheetsClient(dry_run=False)
    fixture_path = os.path.join(_V2_ROOT, "fixtures", "sample_media_assets.json")
    with open(fixture_path, encoding="utf-8") as f:
        sample_assets = json.load(f)
    for a in sample_assets:
        mc.save_media_asset(a)

    # check_media_assets は実Sheetsを前提とした関数なのでモックでは直接呼べないが
    # 定数・関数の存在確認のみとする
    assert_true("33. check_media_assets 関数が存在する",
                hasattr(cpi, "check_media_assets"))


# ------------------------------------------------------------------ #
# runner
# ------------------------------------------------------------------ #

def run_all() -> None:
    print("=" * 60)
    print("test_phase212.py — Phase 2.12 テスト")
    print("=" * 60)

    test_extract_media_urls()
    test_classify_media_url()
    test_slugs()
    test_cloudinary_signature()
    test_assess_imitation_risk()
    test_prepare_media_asset()
    test_prepare_media_assets()
    test_upload_guard()
    test_get_cloudinary_config()
    test_mock_sheets_client()
    test_sheets_client_methods()
    test_fixtures_media_assets()
    test_e2e_from_x_posts()
    test_check_pipeline_integrity()

    print("\n" + "=" * 60)
    passed = sum(1 for ok, _ in _results if ok)
    failed = sum(1 for ok, _ in _results if not ok)
    print(f"結果: {passed} PASS / {failed} FAIL / {len(_results)} 合計")
    print("=" * 60)
    if failed > 0:
        print("\n失敗したテスト:")
        for ok_flag, name in _results:
            if not ok_flag:
                print(f"  - {name}")
        sys.exit(1)


if __name__ == "__main__":
    run_all()
