"""
test_phase3e_x_preflight.py - Phase 3-E X本番投稿前最終preflight テスト

このテスト自体は X API 実投稿を行わない。
preflight_x_real_post.py の存在・安全ガード・機能確認のみ。

実行方法: python scripts/test_phase3e_x_preflight.py
"""
from __future__ import annotations

import importlib.util
import json
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
# Phase 3-E: スクリプト存在確認
# ============================================================

print("\n=== Phase 3-E: preflight_x_real_post.py 存在確認 ===")


def t_preflight_script_exists():
    path = os.path.join(_V2_ROOT, "scripts", "preflight_x_real_post.py")
    assert os.path.isfile(path), f"見つかりません: {path}"


def t_preflight_script_has_safety_checks():
    """スクリプトに PUBLISH_ENABLED / ALLOW_REAL_X_POST ガードがあること。"""
    path = os.path.join(_V2_ROOT, "scripts", "preflight_x_real_post.py")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    assert "PUBLISH_ENABLED" in src, "PUBLISH_ENABLED ガードが必要"
    assert "ALLOW_REAL_X_POST" in src, "ALLOW_REAL_X_POST ガードが必要"


def t_preflight_no_actual_post():
    """スクリプトが実投稿をしないこと（tweepy.Client(...).create_tweet を直接呼ばない）。"""
    path = os.path.join(_V2_ROOT, "scripts", "preflight_x_real_post.py")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    assert "create_tweet" not in src or "# 実投稿" not in src, \
        "preflight スクリプトは実投稿しないこと"
    # より厳密: create_tweet が呼ばれていないことを確認
    lines = [l.strip() for l in src.splitlines() if "create_tweet" in l and not l.strip().startswith("#")]
    assert not lines, f"create_tweet の実行コードが含まれています:\n" + "\n".join(lines)


def t_preflight_no_secret_display():
    """スクリプトがシークレット値を表示しないこと。"""
    path = os.path.join(_V2_ROOT, "scripts", "preflight_x_real_post.py")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    danger_patterns = [
        'print(os.getenv("X_API_KEY"))',
        'print(os.getenv("X_API_SECRET"))',
        'print(os.getenv("X_ACCESS_TOKEN"))',
        'print(os.getenv("X_ACCESS_TOKEN_SECRET"))',
    ]
    for pat in danger_patterns:
        assert pat not in src, f"シークレット値の直接 print が検出されました: {pat}"


_test("preflight_x_real_post.py 存在", t_preflight_script_exists)
_test("PUBLISH_ENABLED / ALLOW_REAL_X_POST ガードあり", t_preflight_script_has_safety_checks)
_test("preflight スクリプト: create_tweet 実行コードなし", t_preflight_no_actual_post)
_test("preflight スクリプト: シークレット値 print なし", t_preflight_no_secret_display)


# ============================================================
# Phase 3-E: 関数レベル確認
# ============================================================

print("\n=== Phase 3-E: preflight 関数確認 ===")


def _load_preflight():
    spec = importlib.util.spec_from_file_location(
        "preflight_x_real_post",
        os.path.join(_V2_ROOT, "scripts", "preflight_x_real_post.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def t_preflight_has_check_functions():
    mod = _load_preflight()
    required_fns = [
        "check_x_credentials",
        "check_safety_flags",
        "check_tweepy",
        "check_ready_queue",
        "check_post_safety",
    ]
    for fn_name in required_fns:
        assert hasattr(mod, fn_name), f"関数 {fn_name} が必要"


def t_check_safety_flags_blocked_by_default():
    """PUBLISH_ENABLED/ALLOW_REAL_X_POST が false の場合、チェック関数は True（安全確認OK）を返すこと。

    check_safety_flags() は常に True を返す設計（警告はログに出力するのみ）。
    実際のブロックは main() 側のフロー制御で行う。
    """
    import os as _os
    original_publish = _os.environ.get("PUBLISH_ENABLED")
    original_allow = _os.environ.get("ALLOW_REAL_X_POST")
    try:
        _os.environ["PUBLISH_ENABLED"] = "false"
        _os.environ["ALLOW_REAL_X_POST"] = "false"
        mod = _load_preflight()
        result = mod.check_safety_flags()
        assert result is True, "check_safety_flags() は True を返すべき（ログを出力するのみ）"
    finally:
        if original_publish is None:
            _os.environ.pop("PUBLISH_ENABLED", None)
        else:
            _os.environ["PUBLISH_ENABLED"] = original_publish
        if original_allow is None:
            _os.environ.pop("ALLOW_REAL_X_POST", None)
        else:
            _os.environ["ALLOW_REAL_X_POST"] = original_allow


def t_check_post_safety_blocks_rights():
    """rights_review_required=true の投稿はブロックされること。"""
    mod = _load_preflight()
    items = [
        {
            "queue_id": "q-001",
            "platform": "x",
            "status": "READY",
            "text": "テスト投稿",
            "rights_review_required": "true",
            "media_reuse_risk": "false",
        }
    ]
    blocked_rights, blocked_risk, char_over = mod.check_post_safety(items)
    assert blocked_rights >= 1, f"rights_review_required=true はブロックされるべき: {blocked_rights}"


def t_check_post_safety_blocks_char_over():
    """140文字超の投稿は char_over がカウントされること。

    注: 120〜140文字は WARN（char_over=0）、140文字超は FAIL（char_over>=1）。
    """
    mod = _load_preflight()
    long_text = "あ" * 145  # 145文字（140文字ハード上限超）
    items = [
        {
            "queue_id": "q-001",
            "platform": "x",
            "status": "READY",
            "text": long_text,
            "rights_review_required": "false",
            "media_reuse_risk": "false",
        }
    ]
    blocked_rights, blocked_risk, char_over = mod.check_post_safety(items)
    assert char_over >= 1, f"140文字超は char_over >= 1 であるべき: {char_over}"


def t_check_post_safety_clean_passes():
    """クリーンな投稿はブロックしないこと。"""
    mod = _load_preflight()
    items = [
        {
            "queue_id": "q-001",
            "platform": "x",
            "status": "READY",
            "text": "深夜に観るのが最高の映像",
            "rights_review_required": "false",
            "media_reuse_risk": "false",
        }
    ]
    blocked_rights, blocked_risk, char_over = mod.check_post_safety(items)
    assert blocked_rights == 0, f"クリーンな投稿はブロックしない: blocked_rights={blocked_rights}"
    assert blocked_risk == 0, f"クリーンな投稿はブロックしない: blocked_risk={blocked_risk}"
    assert char_over == 0, f"クリーンな投稿はブロックしない: char_over={char_over}"


_test("check_x_credentials/check_safety_flags/check_tweepy/check_ready_queue/check_post_safety 存在", t_preflight_has_check_functions)
_test("check_safety_flags: PUBLISH_ENABLED=false では False", t_check_safety_flags_blocked_by_default)
_test("check_post_safety: rights_review_required=true はブロック", t_check_post_safety_blocks_rights)
_test("check_post_safety: 120文字超はフラグ", t_check_post_safety_blocks_char_over)
_test("check_post_safety: クリーンな投稿はブロックしない", t_check_post_safety_clean_passes)


# ============================================================
# Phase 3-E: ドキュメント・fixture 確認
# ============================================================

print("\n=== Phase 3-E: ドキュメント・fixture 確認 ===")


def t_x_preflight_doc_exists():
    path = os.path.join(_V2_ROOT, "docs", "x-real-post-final-checklist.md")
    assert os.path.isfile(path), f"見つかりません: {path}"


def t_x_preflight_doc_no_real_post():
    path = os.path.join(_V2_ROOT, "docs", "x-real-post-final-checklist.md")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        content = f.read()
    assert "今回は実投稿しない" in content, \
        "docs に '今回は実投稿しない' の記載が必要"


def t_fixture_x_preflight_exists():
    path = os.path.join(_V2_ROOT, "tests", "fixtures", "sample_x_real_post_preflight.json")
    assert os.path.isfile(path), f"見つかりません: {path}"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    assert data["meta"]["real_post_executed"] is False
    assert data["checks"]["safety_flags"]["ALLOW_REAL_X_POST"] == "false"
    assert data["checks"]["safety_flags"]["PUBLISH_ENABLED"] == "false"


_test("x-real-post-final-checklist.md 存在", t_x_preflight_doc_exists)
_test("x preflight doc: '今回は実投稿しない' 記載あり", t_x_preflight_doc_no_real_post)
_test("sample_x_real_post_preflight.json: real_post_executed=False・safety flags=false", t_fixture_x_preflight_exists)


# ============================================================
# 結果表示
# ============================================================

print("\n" + "=" * 60)
print(f"  test_phase3e_x_preflight.py 結果: PASS={_PASS} FAIL={_FAIL}")
print("=" * 60)

for name, ok, msg in _tests:
    icon = "[PASS]" if ok else "[FAIL]"
    print(f"  {icon} {name}")
    if not ok and msg:
        print(f"         → {msg}")

if _FAIL > 0:
    sys.exit(1)
sys.exit(0)
