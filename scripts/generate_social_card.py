#!/usr/bin/env python3
"""Generate a self-generated social card (text image) for Threads-first operation.

安全方針:
  - 自前生成テキストカードのみ。第三者画像/動画は扱わない。
  - 生成物は output/ 配下のみ（.gitignore 済み）。VPS / repo には保存しない。
  - 既定は dry-run（Sheets 書き込みなし / Cloudinary upload なし）。
  - Cloudinary upload は ALLOW_CLOUDINARY_UPLOAD=true + --confirm-upload で別途ゲート。
    本スクリプトは upload を実行しない（plan のみ表示）。

使い方:
  python3 scripts/generate_social_card.py \
      --account-id night_scout \
      --hook "今日のひとこと" \
      --body "本文をここに。\n改行も使えます。" \
      --format portrait
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "src"))

from media.cloudinary_uploader import plan_cloudinary_upload  # noqa: E402
from media.social_card import (  # noqa: E402
    FORMATS,
    build_self_generated_card_asset,
    render_text_card,
)

OUTPUT_DIR = os.path.join(_ROOT, "output", "social_cards")


def main() -> int:
    parser = argparse.ArgumentParser(description="generate self-generated social card")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--hook", required=True)
    parser.add_argument("--body", default="")
    parser.add_argument("--format", choices=sorted(FORMATS), default="portrait")
    parser.add_argument("--font-path", default=None)
    parser.add_argument("--out", default=None, help="出力PNGパス（既定: output/social_cards/）")
    # Cloudinary は本スクリプトでは実行しない。plan 表示用フラグのみ受け取る。
    parser.add_argument("--upload", action="store_true", help="plan のみ。実uploadはしない")
    parser.add_argument("--confirm-upload", action="store_true")
    args = parser.parse_args()

    if args.out:
        out_path = args.out
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(OUTPUT_DIR, f"{args.account_id}_{args.format}_{stamp}.png")

    body = args.body.replace("\\n", "\n")
    render = render_text_card(
        hook=args.hook,
        body=body,
        out_path=out_path,
        fmt=args.format,
        font_path=args.font_path,
    )

    asset = build_self_generated_card_asset(
        account_id=args.account_id,
        local_path=out_path,
        fmt=args.format,
    )

    # Cloudinary upload は実行しない。ゲート状態だけ可視化する。
    upload_plan = plan_cloudinary_upload(
        {"media_asset_id": asset["media_asset_id"], "local_path": out_path, "status": asset["status"]},
        upload=args.upload,
        confirm_upload=args.confirm_upload,
        dry_run=True,
    )

    print(json.dumps({
        "status": "GENERATED",
        "render": render,
        "media_asset": asset,
        "cloudinary_plan": {
            "status": upload_plan["status"],
            "allow_cloudinary_upload": upload_plan["allow_cloudinary_upload"],
            "blocked_reasons": upload_plan["blocked_reasons"],
        },
        "notes": "実uploadは未実行。Sheets書き込みなし。生成物はoutput/のみ。",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
