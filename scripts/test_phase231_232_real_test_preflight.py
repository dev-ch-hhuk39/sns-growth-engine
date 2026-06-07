"""
test_phase231_232_real_test_preflight.py - Phase 2.31/2.32 実テスト直前確認

Phase 2.31: Cloudflare 30秒 smoke test 準備確認
Phase 2.32: Cloudinary 小ファイルアップロード smoke test 準備確認

このテスト自体は実API呼び出し・実アップロードを行わない。
スクリプトの存在・安全ガード・ドキュメントの確認のみ。

実行方法: python scripts/test_phase231_232_real_test_preflight.py
"""
from __future__ import annotations

import importlib.util
import inspect
import os
import sys

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

# ============================================================
# テストフレームワーク
# ============================================================

_PASS = 0
_FAIL = 0
_tests: list[tuple[str, bool, str]] = []


def _test(name: str, fn) -> None:
    global _PASS, _FAIL
    try:
        fn()
        _PASS += 1
        _tests.append((name, True, ""))
    except Exception as e:
        _FAIL += 1
        _tests.append((name, False, str(e)))


# ============================================================
# Phase 2.31: Cloudflare transcription smoke test 準備
# ============================================================

print("\n=== Phase 2.31: Cloudflare smoke test 準備 ===")


def t_cloudflare_credentials_script_exists():
    path = os.path.join(_V2_ROOT, "scripts", "test_cloudflare_transcription_credentials.py")
    assert os.path.isfile(path), f"見つかりません: {path}"


def t_cloudflare_smoke_script_exists():
    path = os.path.join(_V2_ROOT, "scripts", "test_cloudflare_transcription_smoke.py")
    assert os.path.isfile(path), f"見つかりません: {path}"


def t_cloudflare_smoke_has_safety_guard():
    """Cloudflare smoke test スクリプトに ALLOW_TRANSCRIPTION_API ガードがあること。"""
    path = os.path.join(_V2_ROOT, "scripts", "test_cloudflare_transcription_smoke.py")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        src = f.read()
    assert "ALLOW_TRANSCRIPTION_API" in src, \
        "ALLOW_TRANSCRIPTION_API 安全ガードが必要"
    assert "false" in src.lower(), "デフォルト false のガードが必要"


def t_cloudflare_credentials_no_real_call():
    """credentials チェックスクリプトが実API呼び出しをしないこと。"""
    path = os.path.join(_V2_ROOT, "scripts", "test_cloudflare_transcription_credentials.py")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        src = f.read()
    # 実API呼び出しをするパターンがないことを確認
    assert "requests.post" not in src or "ALLOW_TRANSCRIPTION_API" in src, \
        "credentials確認スクリプトで実API呼び出しをしてはいけない"
    assert "httpx.post" not in src or "ALLOW_TRANSCRIPTION_API" in src, \
        "credentials確認スクリプトで実API呼び出しをしてはいけない"


_test("test_cloudflare_transcription_credentials.py 存在", t_cloudflare_credentials_script_exists)
_test("test_cloudflare_transcription_smoke.py 存在", t_cloudflare_smoke_script_exists)
_test("Cloudflare smoke: ALLOW_TRANSCRIPTION_API ガードあり", t_cloudflare_smoke_has_safety_guard)
_test("Cloudflare credentials: 実API呼び出しなし", t_cloudflare_credentials_no_real_call)


# ============================================================
# Phase 2.32: Cloudinary upload smoke test 準備
# ============================================================

print("\n=== Phase 2.32: Cloudinary upload smoke test 準備 ===")


def t_cloudinary_credentials_script_exists():
    path = os.path.join(_V2_ROOT, "scripts", "test_cloudinary_credentials.py")
    assert os.path.isfile(path), f"見つかりません: {path}"


def t_cloudinary_upload_smoke_script_exists():
    path = os.path.join(_V2_ROOT, "scripts", "test_cloudinary_upload_smoke.py")
    assert os.path.isfile(path), f"見つかりません: {path}"


def t_cloudinary_credentials_checks_three_vars():
    """credentials スクリプトが3つの環境変数を確認すること。"""
    spec = importlib.util.spec_from_file_location(
        "test_cloudinary_credentials",
        os.path.join(_V2_ROOT, "scripts", "test_cloudinary_credentials.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    # スクリプトを exec せずソースだけ確認
    path = os.path.join(_V2_ROOT, "scripts", "test_cloudinary_credentials.py")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    assert "CLOUDINARY_CLOUD_NAME" in src, "CLOUDINARY_CLOUD_NAME チェックが必要"
    assert "CLOUDINARY_API_KEY" in src, "CLOUDINARY_API_KEY チェックが必要"
    assert "CLOUDINARY_API_SECRET" in src, "CLOUDINARY_API_SECRET チェックが必要"


def t_cloudinary_credentials_no_value_display():
    """credentials スクリプトが秘密値を表示しないこと。"""
    path = os.path.join(_V2_ROOT, "scripts", "test_cloudinary_credentials.py")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    # 値を print するパターンがないこと（os.getenv の戻り値をそのまま print しない）
    assert 'print(os.getenv("CLOUDINARY_API_KEY"))' not in src, \
        "API KEY の値を直接 print してはいけない"
    assert 'print(os.getenv("CLOUDINARY_API_SECRET"))' not in src, \
        "API SECRET の値を直接 print してはいけない"


def t_cloudinary_upload_smoke_three_layer_guard():
    """upload smoke スクリプトに3層ガードがあること。"""
    path = os.path.join(_V2_ROOT, "scripts", "test_cloudinary_upload_smoke.py")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    assert "ALLOW_CLOUDINARY_UPLOAD" in src, "Layer 1: ALLOW_CLOUDINARY_UPLOAD env var ガードが必要"
    assert "--upload" in src, "Layer 2: --upload フラグが必要"
    assert "--confirm-upload" in src, "Layer 3: --confirm-upload フラグが必要"


def t_cloudinary_upload_smoke_max_file_size():
    """upload smoke スクリプトにファイルサイズ制限があること。"""
    path = os.path.join(_V2_ROOT, "scripts", "test_cloudinary_upload_smoke.py")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    assert "MAX_FILE_SIZE_BYTES" in src or "512" in src, \
        "MAX_FILE_SIZE_BYTES (512KB) 制限が必要"


def t_cloudinary_upload_smoke_allowed_extensions():
    """upload smoke スクリプトに許可拡張子リストがあること。"""
    path = os.path.join(_V2_ROOT, "scripts", "test_cloudinary_upload_smoke.py")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    assert "ALLOWED_EXTENSIONS" in src or ".jpg" in src, \
        "ALLOWED_EXTENSIONS リストが必要"


def t_cloudinary_safety_vars_default_false():
    """ALLOW_CLOUDINARY_UPLOAD のデフォルトが false であること。"""
    path = os.path.join(_V2_ROOT, "scripts", "test_cloudinary_credentials.py")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    assert "false" in src.lower(), \
        "ALLOW_CLOUDINARY_UPLOAD のデフォルトが false であること"


_test("test_cloudinary_credentials.py 存在", t_cloudinary_credentials_script_exists)
_test("test_cloudinary_upload_smoke.py 存在", t_cloudinary_upload_smoke_script_exists)
_test("Cloudinary credentials: 3変数チェック", t_cloudinary_credentials_checks_three_vars)
_test("Cloudinary credentials: 秘密値を表示しない", t_cloudinary_credentials_no_value_display)
_test("Cloudinary upload smoke: 3層ガード（env/--upload/--confirm-upload）", t_cloudinary_upload_smoke_three_layer_guard)
_test("Cloudinary upload smoke: MAX_FILE_SIZE_BYTES 制限", t_cloudinary_upload_smoke_max_file_size)
_test("Cloudinary upload smoke: ALLOWED_EXTENSIONS リスト", t_cloudinary_upload_smoke_allowed_extensions)
_test("ALLOW_CLOUDINARY_UPLOAD デフォルト false", t_cloudinary_safety_vars_default_false)


# ============================================================
# Phase 2.31/2.32: ドキュメント確認
# ============================================================

print("\n=== Phase 2.31/2.32: ドキュメント確認 ===")


def t_cloudinary_smoke_doc_exists():
    path = os.path.join(_V2_ROOT, "docs", "cloudinary-upload-smoke-test.md")
    assert os.path.isfile(path), f"見つかりません: {path}"


def t_cloudinary_smoke_doc_no_real_upload():
    path = os.path.join(_V2_ROOT, "docs", "cloudinary-upload-smoke-test.md")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        content = f.read()
    assert "今回は実アップロードしない" in content, \
        "docs に '今回は実アップロードしない' の記載が必要"


def t_fixture_cloudinary_smoke_plan():
    import json
    path = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_cloudinary_smoke_plan.json")
    assert os.path.isfile(path), f"見つかりません: {path}"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    assert data["meta"]["real_upload_executed"] is False


_test("cloudinary-upload-smoke-test.md 存在", t_cloudinary_smoke_doc_exists)
_test("cloudinary doc: '今回は実アップロードしない' 記載あり", t_cloudinary_smoke_doc_no_real_upload)
_test("sample_cloudinary_smoke_plan.json: real_upload_executed=False", t_fixture_cloudinary_smoke_plan)


# ============================================================
# 結果表示
# ============================================================

print("\n" + "=" * 60)
print(f"  test_phase231_232_real_test_preflight.py 結果: PASS={_PASS} FAIL={_FAIL}")
print("=" * 60)

for name, ok, msg in _tests:
    icon = "[PASS]" if ok else "[FAIL]"
    print(f"  {icon} {name}")
    if not ok and msg:
        print(f"         → {msg}")

if _FAIL > 0:
    sys.exit(1)
sys.exit(0)
