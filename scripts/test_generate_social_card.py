#!/usr/bin/env python3
"""Validate self-generated social card generation and its safety properties."""
from __future__ import annotations

import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "src"))

from media.cloudinary_uploader import plan_cloudinary_upload
from media.social_card import (
    FORMATS,
    SELF_GENERATED_RIGHTS,
    build_self_generated_card_asset,
    render_text_card,
)


def main() -> int:
    checks: list[tuple[str, bool]] = []

    with tempfile.TemporaryDirectory() as tmp:
        # portrait / square のサイズ整合
        for fmt, expected in (("portrait", (1080, 1350)), ("square", (1080, 1080))):
            out = os.path.join(tmp, f"{fmt}.png")
            r = render_text_card(
                hook="フックの一文",
                body="本文1行目\n本文2行目はそれなりに長くしてもちゃんと折り返されるはず。",
                out_path=out,
                fmt=fmt,
            )
            checks.append((f"{fmt} rendered ok", r["ok"] is True))
            checks.append((f"{fmt} file exists", os.path.exists(out)))
            checks.append((f"{fmt} dims {expected}", (r["width"], r["height"]) == expected))
            try:
                from PIL import Image

                im = Image.open(out)
                checks.append((f"{fmt} png size matches", im.size == expected))
            except Exception:
                checks.append((f"{fmt} png size matches", False))

        # 不正フォーマットは弾く
        try:
            render_text_card(hook="x", body="y", out_path=os.path.join(tmp, "z.png"), fmt="banner")
            checks.append(("invalid format rejected", False))
        except ValueError:
            checks.append(("invalid format rejected", True))

    # self_generated レコードの権利値（既存語彙に整合・安全側）
    asset = build_self_generated_card_asset(
        account_id="night_scout", local_path="/tmp/x.png", fmt="portrait"
    )
    checks.append(("rights_policy=owned", asset["rights_policy"] == "owned"))
    checks.append(("reuse_policy=allow_reuse", asset["reuse_policy"] == "allow_reuse"))
    checks.append(("media_policy=owned", asset["media_policy"] == "owned"))
    checks.append(("status=SELF_GENERATED", asset["status"] == "SELF_GENERATED"))
    checks.append(("reuse_policy != no_reuse", asset["reuse_policy"] != "no_reuse"))
    checks.append(
        ("media_policy not do_not_download/plan_only",
         asset["media_policy"] not in {"do_not_download", "plan_only"})
    )
    checks.append(("source marked self_generated", asset["source_id"] == "self_generated"))
    checks.append(("no external_url", asset.get("external_url", "") == ""))
    checks.append(("no cloudinary_url yet", asset.get("cloudinary_url", "") == ""))
    checks.append(("rights constants consistent",
                   SELF_GENERATED_RIGHTS["rights_policy"] == "owned"))

    # Cloudinary upload は rights が clear でも env ゲートのまま
    plan_no_flag = plan_cloudinary_upload(
        {"media_asset_id": asset["media_asset_id"], "local_path": "/tmp/x.png", "status": asset["status"]},
        upload=False, confirm_upload=False, dry_run=True,
    )
    checks.append(("plan blocked without --upload", plan_no_flag["status"] == "BLOCKED"))

    os.environ.pop("ALLOW_CLOUDINARY_UPLOAD", None)
    plan_upload_no_env = plan_cloudinary_upload(
        {"media_asset_id": asset["media_asset_id"], "local_path": "/tmp/x.png", "status": asset["status"]},
        upload=True, confirm_upload=True, dry_run=False,
    )
    checks.append((
        "upload blocked without ALLOW_CLOUDINARY_UPLOAD",
        any("ALLOW_CLOUDINARY_UPLOAD" in r for r in plan_upload_no_env["blocked_reasons"]),
    ))

    # 出力先が output/ 配下（.gitignore 済み）を指す設計であること
    import importlib.util

    cli_path = os.path.join(_ROOT, "scripts", "generate_social_card.py")
    spec = importlib.util.spec_from_file_location("generate_social_card", cli_path)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    rel = os.path.relpath(cli.OUTPUT_DIR, _ROOT)
    checks.append(("CLI output dir under output/", rel.startswith("output" + os.sep)))

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
