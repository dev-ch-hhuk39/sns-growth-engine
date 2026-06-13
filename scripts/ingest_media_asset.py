"""
ingest_media_asset.py - media_ingestion_pipeline CLI（Phase 7.C）

動画URL/画像URL/ローカルファイルをmedia_assetsへ登録するCLI。
実ダウンロード・実アップロードはデフォルト禁止。

使い方:
  python scripts/ingest_media_asset.py --account-id night_scout --video-url "https://example.com/sample.mp4" --dry-run
  python scripts/ingest_media_asset.py --account-id night_scout --local-file /path/to/video.mp4 --dry-run --test-write
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_V2_ROOT, ".env"))
except ImportError:
    pass

from media.media_ingestion_pipeline import create_ingestion_plan


def main() -> None:
    parser = argparse.ArgumentParser(description="media_ingestion_pipeline CLI")
    parser.add_argument("--account-id", default="night_scout")
    parser.add_argument("--video-url", default="")
    parser.add_argument("--image-url", default="")
    parser.add_argument("--local-file", default="")
    parser.add_argument("--reference-post-id", default="")
    parser.add_argument("--clip-candidate-id", default="")
    parser.add_argument("--rights-status", default="unknown", choices=["unknown", "owned", "licensed", "public_domain", "restricted"])
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--test-write", action="store_true")
    parser.add_argument("--download", action="store_true", help="外部URLダウンロード許可")
    parser.add_argument("--confirm-download", action="store_true", help="ダウンロード確認")
    parser.add_argument("--upload", action="store_true", help="Cloudinaryアップロード許可")
    parser.add_argument("--confirm-upload", action="store_true", help="アップロード確認")
    parser.add_argument("--output-json", action="store_true")
    args = parser.parse_args()

    allow_cloudinary = os.environ.get("ALLOW_CLOUDINARY_UPLOAD", "false").lower() == "true"

    print(f"\n=== ingest_media_asset: {args.account_id} ===")
    if args.video_url:
        print(f"  video_url       : {args.video_url[:60]}")
    if args.image_url:
        print(f"  image_url       : {args.image_url[:60]}")
    if args.local_file:
        print(f"  local_file      : {args.local_file}")
    print(f"  rights_status   : {args.rights_status}")
    print(f"  dry_run         : {args.dry_run}")
    print(f"  allow_cloudinary: {allow_cloudinary}")
    print(f"  download        : {args.download}")
    print(f"  confirm_download: {args.confirm_download}")
    print(f"  upload          : {args.upload}")
    print(f"  confirm_upload  : {args.confirm_upload}")

    plan = create_ingestion_plan(
        account_id=args.account_id,
        video_url=args.video_url,
        image_url=args.image_url,
        local_file=args.local_file,
        reference_post_id=args.reference_post_id,
        clip_candidate_id=args.clip_candidate_id,
        rights_status=args.rights_status,
        allow_cloudinary_upload=allow_cloudinary and args.upload,
        confirm_upload=args.confirm_upload,
        allow_download=args.download,
        confirm_download=args.confirm_download,
    )

    print(f"\n--- 取り込みプラン ---")
    print(f"  plan_status   : {plan['plan_status']}")
    for reason in plan["blocked_reasons"]:
        print(f"  [BLOCKED] {reason}")
    for warn in plan["warnings"]:
        print(f"  [WARN] {warn}")
    print(f"  asset_count   : {plan['asset_count']}")
    for asset in plan["assets"]:
        print(f"\n  [{asset['media_asset_id']}]")
        print(f"    media_type   : {asset['media_type']}")
        print(f"    reuse_risk   : {asset['reuse_risk']}")
        print(f"    upload_status: {asset['upload_status']}")
        print(f"    status       : {asset['status']}")

    if args.test_write:
        print(f"\n--- test-write ---")
        if args.use_sheets:
            try:
                from config_loader import get_config, get_config_partial
                from sheets_client import make_client
                try:
                    cfg = get_config()
                except ValueError:
                    cfg = get_config_partial()
                sheets = make_client(cfg, dry_run=False)
                for asset in plan["assets"]:
                    sheets.append_row("media_ingestion_runs", asset)
                print(f"  [OK] {len(plan['assets'])} 件 Sheets書き込み完了")
            except Exception as e:
                print(f"  [WARN] Sheets書き込みエラー: {e}")
        else:
            print(f"  [MockSheets] {len(plan['assets'])} 件のmedia_assetsを保存（mock）")

    if args.output_json:
        print(f"\n--- JSON出力 ---")
        print(json.dumps(plan, ensure_ascii=False, indent=2))

    print(f"\n[DONE] ingest_media_asset 完了")
    print(f"  実ダウンロードなし / 実アップロードなし / Cloudinaryなし")


if __name__ == "__main__":
    main()
