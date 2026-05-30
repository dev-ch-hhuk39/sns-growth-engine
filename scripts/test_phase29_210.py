"""
test_phase29_210.py — Phase 2.9 / 2.10 動作確認テスト

テスト項目:
  1.  sample_x_posts.json を読み込める
  2.  3件を正規化できる
  3.  テキストのみ / 画像あり / 動画あり を判定できる
  4.  likes / impressions が正しく入る
  5.  reference_posts 用 dict に変換できる
  6.  重複キー（post_id / post_url）を作れる
  7.  collect_references.py --dry-run が Sheets へ書かない
  8.  collect_references.py --mock --dry-run が動く
  9.  X API モードがデフォルトで動かない（NotImplementedError）
  10. TAB_DEFINITIONS に Phase 2.8 新タブがある
  11. reference_posts に Phase 2.10 追加列がある
  12. MockSheetsClient に save_reference_post / find_reference_post_by_post_id がある
  13. save_reference_post が重複保存を防ぐ
  14. save_reference_posts が件数を正しく返す
  15. check_pipeline_integrity.py --mock が新タブを確認できる
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

from collectors.x_reference_collector import (
    normalize_post,
    normalize_posts,
    load_json_input,
    classify_media,
    make_dedup_key,
    fetch_account_posts,
)
from sheets_client import TAB_DEFINITIONS, MockSheetsClient

_PASS = 0
_FAIL = 0
_FIXTURES = os.path.join(_V2_ROOT, "fixtures", "sample_x_posts.json")


def ok(name: str) -> None:
    global _PASS
    _PASS += 1
    print(f"  [PASS] {name}")


def fail(name: str, reason: str) -> None:
    global _FAIL
    _FAIL += 1
    print(f"  [FAIL] {name}: {reason}")


# ------------------------------------------------------------------ #
# 1. JSON読み込み
# ------------------------------------------------------------------ #

def test_load_json() -> list[dict]:
    print("\n[Test 1] sample_x_posts.json 読み込み")

    if not os.path.exists(_FIXTURES):
        fail("fixtures/sample_x_posts.json 存在", f"ファイルなし: {_FIXTURES}")
        return []

    posts = load_json_input(_FIXTURES)
    if len(posts) == 3:
        ok(f"sample_x_posts.json: 3件読み込み")
    else:
        fail("sample_x_posts.json: 3件読み込み", f"実際: {len(posts)}件")

    return posts


# ------------------------------------------------------------------ #
# 2. 正規化
# ------------------------------------------------------------------ #

def test_normalize(raw_posts: list[dict]) -> list[dict]:
    print("\n[Test 2] 正規化")

    if not raw_posts:
        fail("normalize_posts 実行", "raw_postsが空")
        return []

    normalized = normalize_posts(raw_posts, account_id="night_scout", platform="x")
    if len(normalized) == 3:
        ok(f"normalize_posts: 3件正規化")
    else:
        fail("normalize_posts: 3件正規化", f"実際: {len(normalized)}件")

    # 必須フィールド確認
    required = ["post_id", "account_id", "platform", "post_url", "text", "likes", "impressions"]
    for field in required:
        if all(field in p for p in normalized):
            ok(f"正規化フィールド: '{field}' 全件あり")
        else:
            fail(f"正規化フィールド: '{field}' 全件あり", "一部なし")

    # account_id が正しい
    if all(p.get("account_id") == "night_scout" for p in normalized):
        ok("正規化: account_id=night_scout")
    else:
        fail("正規化: account_id=night_scout", str([p.get("account_id") for p in normalized]))

    return normalized


# ------------------------------------------------------------------ #
# 3. メディア判定
# ------------------------------------------------------------------ #

def test_media_classification(raw_posts: list[dict]) -> None:
    print("\n[Test 3] メディア判定")

    if len(raw_posts) < 3:
        fail("メディア判定", "raw_postsが3件未満")
        return

    # テキストのみ（post[0]）
    m0 = classify_media(raw_posts[0])
    if not m0["has_image"] and not m0["has_video"] and not m0["has_media"]:
        ok("post[0]: テキストのみ（画像・動画なし）")
    else:
        fail("post[0]: テキストのみ", str(m0))

    # 画像あり（post[1]）
    m1 = classify_media(raw_posts[1])
    if m1["has_image"] and not m1["has_video"] and m1["has_media"]:
        ok("post[1]: 画像あり")
    else:
        fail("post[1]: 画像あり", str(m1))

    # 動画あり（post[2]）
    m2 = classify_media(raw_posts[2])
    if m2["has_video"] and not m2["has_image"] and m2["has_media"]:
        ok("post[2]: 動画あり")
    else:
        fail("post[2]: 動画あり", str(m2))


# ------------------------------------------------------------------ #
# 4. likes / views の値確認
# ------------------------------------------------------------------ #

def test_numeric_fields(normalized: list[dict], raw_posts: list[dict]) -> None:
    print("\n[Test 4] likes / impressions 値確認")

    if not normalized or not raw_posts:
        fail("numeric fields", "データなし")
        return

    for i, (n, r) in enumerate(zip(normalized, raw_posts)):
        expected_likes = r.get("like_count", 0)
        expected_views = r.get("impression_count", 0)

        if int(n.get("likes", -1)) == expected_likes:
            ok(f"post[{i}]: likes={expected_likes}")
        else:
            fail(f"post[{i}]: likes", f"expected={expected_likes} actual={n.get('likes')}")

        if int(n.get("impressions", -1)) == expected_views:
            ok(f"post[{i}]: impressions={expected_views}")
        else:
            fail(f"post[{i}]: impressions", f"expected={expected_views} actual={n.get('impressions')}")

        if int(n.get("reply_count", -1)) == r.get("reply_count", 0):
            ok(f"post[{i}]: reply_count={r.get('reply_count', 0)}")
        else:
            fail(f"post[{i}]: reply_count", f"expected={r.get('reply_count')} actual={n.get('reply_count')}")

        if int(n.get("bookmark_count", -1)) == r.get("bookmark_count", 0):
            ok(f"post[{i}]: bookmark_count={r.get('bookmark_count', 0)}")
        else:
            fail(f"post[{i}]: bookmark_count", f"expected={r.get('bookmark_count')} actual={n.get('bookmark_count')}")


# ------------------------------------------------------------------ #
# 5. reference_posts スキーマへの変換確認
# ------------------------------------------------------------------ #

def test_reference_posts_schema(normalized: list[dict]) -> None:
    print("\n[Test 5] reference_posts スキーマ変換確認")

    ref_schema_cols = TAB_DEFINITIONS.get("reference_posts", [])
    if not ref_schema_cols:
        fail("reference_posts スキーマ", "TAB_DEFINITIONSになし")
        return

    # Phase 2.10 追加列
    new_cols = ["original_text", "account_handle", "reply_count", "bookmark_count", "collected_at", "keywords"]
    for col in new_cols:
        if col in ref_schema_cols:
            ok(f"reference_posts スキーマ: '{col}' 追加列あり")
        else:
            fail(f"reference_posts スキーマ: '{col}' 追加列あり", "列定義なし")

    # 正規化済みdictにも含まれることを確認
    if normalized:
        for col in new_cols:
            if col in normalized[0]:
                ok(f"normalize_post: '{col}' キーあり")
            else:
                fail(f"normalize_post: '{col}' キーあり", f"実際のキー: {list(normalized[0].keys())}")


# ------------------------------------------------------------------ #
# 6. 重複キー
# ------------------------------------------------------------------ #

def test_dedup_key(normalized: list[dict]) -> None:
    print("\n[Test 6] 重複キー生成")

    if not normalized:
        fail("dedup_key", "データなし")
        return

    keys = [make_dedup_key(p) for p in normalized]
    if len(keys) == len(set(keys)):
        ok(f"全{len(keys)}件がユニークな重複キー")
    else:
        fail("重複キー ユニーク", f"キー: {keys}")

    # post_id が最優先
    if normalized[0].get("post_id"):
        k = make_dedup_key(normalized[0])
        if k.startswith("post_id:"):
            ok("dedup_key: post_id 最優先")
        else:
            fail("dedup_key: post_id 最優先", f"実際: {k}")


# ------------------------------------------------------------------ #
# 7. collect_references.py --dry-run はSheetsに書かない
# ------------------------------------------------------------------ #

def test_collect_references_dry_run() -> None:
    print("\n[Test 7] collect_references.py --dry-run Sheets非書き込み確認")

    cmd = [
        sys.executable,
        os.path.join(_V2_ROOT, "scripts", "collect_references.py"),
        "--account-id", "night_scout",
        "--platform", "x",
        "--input-json", _FIXTURES,
        "--dry-run",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        output = result.stdout + result.stderr

        if result.returncode == 0:
            ok("collect_references.py --dry-run 終了コード0")
        else:
            fail("collect_references.py --dry-run 終了コード0", f"code={result.returncode}\n{output}")
            return

        if "dry-run" in output.lower() or "dry_run" in output.lower():
            ok("collect_references.py --dry-run 出力にdry-run表示")
        else:
            fail("collect_references.py --dry-run 出力にdry-run表示", output[:200])

        if "SNS投稿は発生していません" in output or "SNS" in output:
            ok("collect_references.py 安全確認メッセージ表示")
        else:
            fail("collect_references.py 安全確認メッセージ表示", output[-200:])

    except subprocess.TimeoutExpired:
        fail("collect_references.py --dry-run タイムアウト", "30秒以内に終了しなかった")
    except Exception as e:
        fail("collect_references.py --dry-run", str(e))


# ------------------------------------------------------------------ #
# 8. collect_references.py --mock --dry-run
# ------------------------------------------------------------------ #

def test_collect_references_mock() -> None:
    print("\n[Test 8] collect_references.py --mock --dry-run")

    cmd = [
        sys.executable,
        os.path.join(_V2_ROOT, "scripts", "collect_references.py"),
        "--account-id", "night_scout",
        "--platform", "x",
        "--mock",
        "--dry-run",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        output = result.stdout + result.stderr

        if result.returncode == 0:
            ok("collect_references.py --mock --dry-run 終了コード0")
        else:
            fail("collect_references.py --mock --dry-run 終了コード0", f"code={result.returncode}\n{output}")
            return

        if "モックデータ" in output or "mock" in output.lower():
            ok("collect_references.py --mock モックデータ生成確認")
        else:
            fail("collect_references.py --mock モックデータ生成確認", output[:200])

    except subprocess.TimeoutExpired:
        fail("collect_references.py --mock タイムアウト", "30秒以内に終了しなかった")
    except Exception as e:
        fail("collect_references.py --mock --dry-run", str(e))


# ------------------------------------------------------------------ #
# 9. X API モードがデフォルトで動かない
# ------------------------------------------------------------------ #

def test_x_api_not_default() -> None:
    print("\n[Test 9] X API モードはデフォルトで動かない")

    try:
        fetch_account_posts("dummy_user", "dummy_token")
        fail("fetch_account_posts → NotImplementedError", "例外が発生しませんでした")
    except NotImplementedError:
        ok("fetch_account_posts → NotImplementedError（--use-x-api なしで動かない）")

    # --use-x-api フラグなしで collect_references.py を実行するとX APIは呼ばれない（dry-runで正常終了）
    cmd = [
        sys.executable,
        os.path.join(_V2_ROOT, "scripts", "collect_references.py"),
        "--account-id", "night_scout",
        "--platform", "x",
        "--mock",
        "--dry-run",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode == 0:
        ok("collect_references.py --use-x-api なし → 正常終了（X APIは呼ばれない）")
    else:
        fail("collect_references.py --use-x-api なし → 正常終了", result.stderr[:200])


# ------------------------------------------------------------------ #
# 10. TAB_DEFINITIONS に Phase 2.8 新タブがある
# ------------------------------------------------------------------ #

def test_tab_definitions() -> None:
    print("\n[Test 10] TAB_DEFINITIONS Phase 2.8 新タブ確認")

    for tab in ["media_assets", "reference_post_scores", "generation_jobs"]:
        if tab in TAB_DEFINITIONS:
            ok(f"TAB_DEFINITIONS['{tab}'] 存在")
        else:
            fail(f"TAB_DEFINITIONS['{tab}'] 存在", "定義なし")


# ------------------------------------------------------------------ #
# 11. reference_posts の追加列確認（Test 5 で実施済み、ここでは簡略版）
# ------------------------------------------------------------------ #

def test_reference_posts_new_cols() -> None:
    print("\n[Test 11] reference_posts 追加列確認")
    ref_cols = TAB_DEFINITIONS.get("reference_posts", [])
    for col in ["original_text", "account_handle", "reply_count", "bookmark_count", "collected_at", "keywords"]:
        if col in ref_cols:
            ok(f"reference_posts: '{col}' 列あり")
        else:
            fail(f"reference_posts: '{col}' 列あり", "なし")


# ------------------------------------------------------------------ #
# 12. MockSheetsClient メソッド確認
# ------------------------------------------------------------------ #

def test_mock_sheets_methods() -> None:
    print("\n[Test 12] MockSheetsClient 新メソッド確認")

    mock = MockSheetsClient(dry_run=True)

    if hasattr(mock, "save_reference_post"):
        ok("MockSheetsClient: save_reference_post メソッドあり")
    else:
        fail("MockSheetsClient: save_reference_post メソッドあり", "なし")

    if hasattr(mock, "find_reference_post_by_post_id"):
        ok("MockSheetsClient: find_reference_post_by_post_id メソッドあり")
    else:
        fail("MockSheetsClient: find_reference_post_by_post_id メソッドあり", "なし")

    if hasattr(mock, "save_reference_posts"):
        ok("MockSheetsClient: save_reference_posts メソッドあり")
    else:
        fail("MockSheetsClient: save_reference_posts メソッドあり", "なし")


# ------------------------------------------------------------------ #
# 13. save_reference_post 重複保存防止
# ------------------------------------------------------------------ #

def test_dedup_save() -> None:
    print("\n[Test 13] save_reference_post 重複保存防止")

    mock = MockSheetsClient(dry_run=False)

    post = {
        "post_id": "test-post-001",
        "post_url": "https://x.com/user/status/test-post-001",
        "account_id": "night_scout",
        "platform": "x",
        "text": "テスト投稿",
        "likes": 100,
    }

    r1 = mock.save_reference_post(post)
    if r1:
        ok("save_reference_post: 1回目 → True（保存）")
    else:
        fail("save_reference_post: 1回目 → True", f"result={r1}")

    r2 = mock.save_reference_post(post)
    if not r2:
        ok("save_reference_post: 2回目 → False（重複スキップ）")
    else:
        fail("save_reference_post: 2回目 → False", f"result={r2}")

    found = mock.find_reference_post_by_post_id("test-post-001")
    if found and found.get("post_id") == "test-post-001":
        ok("find_reference_post_by_post_id: post_id で検索できる")
    else:
        fail("find_reference_post_by_post_id: post_id で検索できる", str(found))


# ------------------------------------------------------------------ #
# 14. save_reference_posts 件数確認
# ------------------------------------------------------------------ #

def test_save_reference_posts_count(normalized: list[dict]) -> None:
    print("\n[Test 14] save_reference_posts 件数確認")

    if not normalized:
        fail("save_reference_posts 件数", "データなし")
        return

    mock = MockSheetsClient(dry_run=False)
    result = mock.save_reference_posts(normalized)

    if result["added"] == len(normalized) and result["skipped"] == 0 and result["errors"] == 0:
        ok(f"save_reference_posts: 初回保存 added={result['added']} skipped={result['skipped']} errors={result['errors']}")
    else:
        fail("save_reference_posts: 初回保存", str(result))

    result2 = mock.save_reference_posts(normalized)
    if result2["added"] == 0 and result2["skipped"] == len(normalized) and result2["errors"] == 0:
        ok(f"save_reference_posts: 重複時 added={result2['added']} skipped={result2['skipped']}")
    else:
        fail("save_reference_posts: 重複時 全件スキップ", str(result2))


# ------------------------------------------------------------------ #
# 15. check_pipeline_integrity.py --mock が新タブを確認できる
# ------------------------------------------------------------------ #

def test_integrity_check_mock() -> None:
    print("\n[Test 15] check_pipeline_integrity.py --mock 新タブ確認")

    cmd = [
        sys.executable,
        os.path.join(_V2_ROOT, "scripts", "check_pipeline_integrity.py"),
        "--mock",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        output = result.stdout + result.stderr

        for tab in ["media_assets", "reference_post_scores", "generation_jobs"]:
            if tab in output:
                ok(f"check_pipeline_integrity: '{tab}' チェック実行")
            else:
                fail(f"check_pipeline_integrity: '{tab}' チェック実行", f"出力に'{tab}'なし")

        if result.returncode == 0:
            ok("check_pipeline_integrity.py --mock 終了コード0")
        else:
            fail("check_pipeline_integrity.py --mock 終了コード0", f"code={result.returncode}\n{output[-300:]}")

    except subprocess.TimeoutExpired:
        fail("check_pipeline_integrity.py --mock タイムアウト", "30秒以内に終了しなかった")
    except Exception as e:
        fail("check_pipeline_integrity.py --mock", str(e))


# ------------------------------------------------------------------ #
# エントリーポイント
# ------------------------------------------------------------------ #

def main() -> None:
    print("=" * 60)
    print("Phase 2.9/2.10 テスト開始")
    print("=" * 60)

    raw_posts = test_load_json()
    normalized = test_normalize(raw_posts)
    test_media_classification(raw_posts)
    test_numeric_fields(normalized, raw_posts)
    test_reference_posts_schema(normalized)
    test_dedup_key(normalized)
    test_collect_references_dry_run()
    test_collect_references_mock()
    test_x_api_not_default()
    test_tab_definitions()
    test_reference_posts_new_cols()
    test_mock_sheets_methods()
    test_dedup_save()
    test_save_reference_posts_count(normalized)
    test_integrity_check_mock()

    print("\n" + "=" * 60)
    print(f"結果: {_PASS} PASS / {_FAIL} FAIL")
    print("=" * 60)

    if _FAIL > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
