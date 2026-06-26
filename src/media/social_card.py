"""Self-generated social card rendering (Phase: media pipeline, lowest legal risk).

このモジュールは「自前生成テキストカード」を作る。
第三者画像/動画は一切扱わない。生成物は完全に自社著作物として扱える。

権利モデル（既存 media_assets 語彙に整合）:
  - rights_policy = "owned"        （自前生成なので所有）
  - reuse_policy  = "allow_reuse"  （再利用可）
  - media_policy  = "owned"        （do_not_download / plan_only ではない）
  - status        = "SELF_GENERATED"（rights上は投稿可。ただし Cloudinary upload は
                    ALLOW_CLOUDINARY_UPLOAD=true + --confirm-upload で別途ゲート）

出力は output/ 配下のみ（.gitignore 済み）。VPS / repo には生成物を保存しない。
"""
from __future__ import annotations

import os
from typing import Any

from .media_asset_store import build_media_asset

# 1080px 基準の縦長 / 正方フォーマット
FORMATS: dict[str, tuple[int, int]] = {
    "portrait": (1080, 1350),
    "square": (1080, 1080),
}

# 自前生成カードの安全な権利値（既存語彙）
SELF_GENERATED_RIGHTS = {
    "rights_policy": "owned",
    "reuse_policy": "allow_reuse",
    "media_policy": "owned",
    "status": "SELF_GENERATED",
}

# 日本語対応フォント候補（macOS / 一般的な環境）
_FONT_CANDIDATES = [
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/System/Library/Fonts/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
]


def resolve_font_path(explicit: str | None = None) -> str | None:
    """利用可能な日本語フォントの絶対パスを返す。無ければ None。"""
    candidates = [explicit, *(_FONT_CANDIDATES)] if explicit else list(_FONT_CANDIDATES)
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


def build_self_generated_card_asset(
    *,
    account_id: str,
    local_path: str,
    fmt: str = "portrait",
) -> dict[str, Any]:
    """自前生成カードの media_assets レコードを安全な権利値で作る。

    レジストリ source に依存しない（third-party preflight は通さない）。
    """
    asset = build_media_asset(
        account_id=account_id,
        source_id="self_generated",
        raw_item_id="",
        media_type="image",
        local_path=local_path,
        **SELF_GENERATED_RIGHTS,
    )
    asset["source_platform"] = "self_generated"
    asset["format"] = fmt
    asset["notes"] = "self_generated text card; rights owned; Cloudinary upload still gated"
    return asset


def _wrap_japanese(draw, text: str, font, max_width: int) -> list[str]:
    """日本語（スペース区切りなし）向けに、幅を測りながら文字単位で折り返す。

    明示改行（\\n）は尊重する。
    """
    lines: list[str] = []
    for raw_line in text.split("\n"):
        if raw_line == "":
            lines.append("")
            continue
        current = ""
        for ch in raw_line:
            trial = current + ch
            width = draw.textlength(trial, font=font)
            if width <= max_width or current == "":
                current = trial
            else:
                lines.append(current)
                current = ch
        if current:
            lines.append(current)
    return lines


def render_text_card(
    *,
    hook: str,
    body: str,
    out_path: str,
    fmt: str = "portrait",
    font_path: str | None = None,
    bg_color: tuple[int, int, int] = (17, 17, 23),
    fg_color: tuple[int, int, int] = (245, 245, 250),
    accent_color: tuple[int, int, int] = (122, 162, 247),
    margin: int = 96,
) -> dict[str, Any]:
    """フック + 本文のテキストカードを PNG として描画する。

    Returns: {path, width, height, format, font_used, ok}
    """
    from PIL import Image, ImageDraw, ImageFont  # 遅延 import（テストの一部は不要）

    if fmt not in FORMATS:
        raise ValueError(f"unknown format: {fmt!r} (allowed: {sorted(FORMATS)})")
    width, height = FORMATS[fmt]

    resolved_font = resolve_font_path(font_path)
    hook_size = 64
    body_size = 44
    if resolved_font:
        hook_font = ImageFont.truetype(resolved_font, hook_size)
        body_font = ImageFont.truetype(resolved_font, body_size)
    else:
        hook_font = ImageFont.load_default()
        body_font = ImageFont.load_default()

    img = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    # アクセントバー（上部）
    draw.rectangle([margin, margin, margin + 120, margin + 12], fill=accent_color)

    text_width = width - margin * 2
    y = margin + 48

    hook_lines = _wrap_japanese(draw, hook.strip(), hook_font, text_width)
    for line in hook_lines:
        draw.text((margin, y), line, font=hook_font, fill=fg_color)
        y += int(hook_size * 1.35)

    y += int(body_size * 0.8)

    body_lines = _wrap_japanese(draw, body.strip(), body_font, text_width)
    for line in body_lines:
        if y > height - margin - body_size:
            break  # はみ出しは打ち切り（カードは要約。全文は本文テキストに残す）
        draw.text((margin, y), line, font=body_font, fill=fg_color)
        y += int(body_size * 1.45)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    img.save(out_path, format="PNG")

    return {
        "path": out_path,
        "width": width,
        "height": height,
        "format": fmt,
        "font_used": resolved_font or "PIL_default",
        "ok": True,
    }
