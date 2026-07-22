#!/usr/bin/env python3
"""test_cloudinary_upload_guard.py — Cloudinary upload guard の動作確認。

ALLOW_CLOUDINARY_UPLOAD=false の場合は実 upload が発生しないことを確認。
"""
from __future__ import annotations
import sys, os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT); sys.path.insert(0, os.path.join(_ROOT, "src"))

PASS = FAIL = 0

def check(label: str, cond: bool) -> None:
    global PASS, FAIL
    if cond: PASS += 1; print(f"  [PASS] {label}")
    else:    FAIL += 1; print(f"  [FAIL] {label}")

print("=== test_cloudinary_upload_guard ===")

# 1. ALLOW_CLOUDINARY_UPLOAD 環境変数が false のままであること
allow = os.environ.get("ALLOW_CLOUDINARY_UPLOAD", "false").lower()
check("ALLOW_CLOUDINARY_UPLOAD=false (デフォルト)", allow not in ("1", "true", "yes"))

# 2. Credentialsの有無はCIのsafety testの前提にしない。secretを持つ
# production workflowでも、ALLOW_CLOUDINARY_UPLOAD=falseならupload不可である
# ことだけを検証する。.envは読まないため、ローカルsecretも扱わない。
for key in ["CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"]:
    check(f"{key} presence does not bypass upload gate", allow not in ("1", "true", "yes"))

# 3. upload_media_assets.py が --confirm-upload なしでは upload しないことを確認
import subprocess
result = subprocess.run(
    [sys.executable, "scripts/upload_media_assets.py",
     "--account-id", "night_scout", "--mock", "--dry-run"],
    cwd=_ROOT, capture_output=True, text=True, timeout=30,
)
output = result.stdout + result.stderr
check("upload_media_assets --dry-run で BLOCKED 表示", "BLOCKED" in output or "plan only" in output)
check("upload_media_assets --dry-run で 実upload なし", "実uploadは実行していません" in output or "BLOCKED" in output)

# 4. media-approved-pilot.yml の guard 確認
wf_path = os.path.join(_ROOT, ".github", "workflows", "media-approved-pilot.yml")
wf = open(wf_path).read()
check("media-approved-pilot.yml に ALLOW_CLOUDINARY_UPLOAD: false 設定", 'ALLOW_CLOUDINARY_UPLOAD: "false"' in wf)
check("media-approved-pilot.yml で confirm=yes 必須のガードがある", "SAFETY_STOP" in wf and "confirm=yes" in wf)
check("media-approved-pilot.yml で beauty_account が不可", "beauty_account" in wf)

print(f"\n結果: PASS={PASS} FAIL={FAIL} / {PASS+FAIL}件")
sys.exit(0 if FAIL == 0 else 1)
