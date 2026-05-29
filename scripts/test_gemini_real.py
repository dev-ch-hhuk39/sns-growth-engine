"""
test_gemini_real.py - Gemini 実 API 接続確認 + 品質チェック

GEMINI_API_KEY が未設定の場合は sys.exit(0) でスキップ（CI 友好的）。

チェック内容:
  1. シンプルな JSON 生成
  2. 下書き生成フォーマット確認
  3. night_scout 品質チェック（一人称「僕」、夜職用語、NG表現なし、フォーマット）
  4. liver_manager 品質チェック（ライバー用語、怪しくない、専門性）
  5. X 派生投稿フォーマット確認（120文字以内）
  6. Threads 派生投稿フォーマット確認（2行空け）

使い方:
  python scripts/test_gemini_real.py
  python scripts/test_gemini_real.py --account night_scout
  python scripts/test_gemini_real.py --account liver_manager
  python scripts/test_gemini_real.py --quick   # 品質チェックなし
"""
from __future__ import annotations

import argparse
import os
import sys

# 実 API を呼ぶためモックを強制 off
os.environ["DRY_RUN"] = "false"
os.environ["MOCK_LLM"] = "false"

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_V2_ROOT, ".env"))
except ImportError:
    pass

from config_loader import get_config_partial
from llm_client import call_gemini_json


# ------------------------------------------------------------------ #
# 品質チェック関数
# ------------------------------------------------------------------ #

def _qcheck(label: str, condition: bool, ok_msg: str, warn_msg: str) -> tuple[str, str, str]:
    """(status, label, detail) を返す。"""
    if condition:
        return ("PASS", label, ok_msg)
    return ("WARN", label, warn_msg)


def check_night_scout_quality(text: str) -> list[tuple[str, str, str]]:
    """night_scout 投稿テキストの品質チェック。(status, label, detail) のリストを返す。"""
    results = []

    # 一人称「僕」
    results.append(_qcheck(
        "一人称「僕」",
        "僕" in text,
        "「僕」が含まれています",
        "「僕」が見つかりません（テンプレート設定を確認）",
    ))

    # 夜職関連用語
    night_terms = ["キャバ", "夜職", "スカウト", "夜の仕事", "ナイト", "ガルバ", "水商売", "club", "Club"]
    found = [t for t in night_terms if t in text]
    results.append(_qcheck(
        "夜職関連用語",
        bool(found),
        f"確認: {found}",
        "夜職関連用語が見当たりません（ターゲット外の内容かも）",
    ))

    # NG 表現チェック（FAIL 相当に設定）
    ng_phrases = ["絶対稼げる", "確実に稼", "詐欺", "ぼったくり"]
    found_ng = [p for p in ng_phrases if p in text]
    if found_ng:
        results.append(("FAIL", "NG表現なし", f"NG表現が含まれています: {found_ng}"))
    else:
        results.append(("PASS", "NG表現なし", "NGワード検出なし"))

    # Threads フォーマット（2行空け）
    has_double_break = "\n\n\n" in text or "\n\n" in text
    results.append(_qcheck(
        "Threads形式（段落区切り）",
        has_double_break,
        "段落区切りあり",
        "2行空きの段落区切りが見つかりません（フォーマット確認を）",
    ))

    # 文字数（Threads は 500 字以内）
    length = len(text)
    results.append(_qcheck(
        "Threads 文字数",
        length <= 600,
        f"{length}文字（OK）",
        f"{length}文字（500文字を超えている可能性）",
    ))

    return results


def check_liver_manager_quality(text: str) -> list[tuple[str, str, str]]:
    """liver_manager 投稿テキストの品質チェック。"""
    results = []

    # ライバー・配信関連用語
    liver_terms = ["ライバー", "ライブ", "TikTok", "配信", "ギフト", "事務所", "収益", "ファン"]
    found = [t for t in liver_terms if t in text]
    results.append(_qcheck(
        "ライバー関連用語",
        bool(found),
        f"確認: {found}",
        "ライバー・配信関連用語が見当たりません",
    ))

    # 怪しくない（NG表現チェック）
    ng_phrases = ["絶対稼げる", "確実に稼", "詐欺", "ぼったくり", "誰でも月100万"]
    found_ng = [p for p in ng_phrases if p in text]
    if found_ng:
        results.append(("FAIL", "NG表現なし", f"NG表現が含まれています: {found_ng}"))
    else:
        results.append(("PASS", "NG表現なし", "NGワード検出なし"))

    # 事務所営業っぽくない（過度な勧誘ワードチェック）
    sales_phrases = ["今すぐ入会", "限定募集", "残り〇名", "急いで"]
    found_sales = [p for p in sales_phrases if p in text]
    results.append(_qcheck(
        "事務所営業感なし",
        not bool(found_sales),
        "過度な勧誘表現なし",
        f"事務所営業感のある表現あり: {found_sales}",
    ))

    # 文字数
    length = len(text)
    results.append(_qcheck(
        "文字数",
        length <= 600,
        f"{length}文字（OK）",
        f"{length}文字（長すぎる可能性）",
    ))

    return results


def check_x_quality(text: str) -> list[tuple[str, str, str]]:
    """X 投稿テキストの品質チェック。"""
    results = []
    length = len(text)

    if length <= 120:
        results.append(("PASS", "X 文字数（120字以内）", f"{length}文字 ✓"))
    elif length <= 140:
        results.append(("WARN", "X 文字数（120字以内）",
                        f"{length}文字（120字超過。Xの制限140字以内ではあるが要確認）"))
    else:
        results.append(("FAIL", "X 文字数（120字以内）", f"{length}文字（制限超過）"))

    ng_phrases = ["絶対稼げる", "確実に稼", "詐欺"]
    found_ng = [p for p in ng_phrases if p in text]
    if found_ng:
        results.append(("FAIL", "NG表現なし", f"NG表現: {found_ng}"))
    else:
        results.append(("PASS", "NG表現なし", "NGワード検出なし"))

    return results


def check_threads_quality(text: str) -> list[tuple[str, str, str]]:
    """Threads 投稿テキストの品質チェック。"""
    results = []

    has_double_break = "\n\n\n" in text or "\n\n" in text
    results.append(_qcheck(
        "Threads形式（2行空け）",
        has_double_break,
        "2行空きの段落区切りあり",
        "フォーマット仕様の2行空きが見当たりません",
    ))

    length = len(text)
    results.append(_qcheck(
        "Threads 文字数（500字以内推奨）",
        length <= 600,
        f"{length}文字（OK）",
        f"{length}文字（長すぎる可能性）",
    ))

    return results


# ------------------------------------------------------------------ #
# テスト実行関数
# ------------------------------------------------------------------ #

def _print_quality(checks: list[tuple[str, str, str]]) -> int:
    """品質チェック結果を表示し、FAIL 数を返す。"""
    fails = 0
    for status, label, detail in checks:
        icon = {"PASS": "✓", "WARN": "!", "FAIL": "✗"}.get(status, "?")
        print(f"    [{status}] {icon} {label}: {detail}")
        if status == "FAIL":
            fails += 1
    return fails


def run_tests(args) -> tuple[int, int]:
    """テストを実行し (passed, failed) を返す。"""
    passed = 0
    failed = 0
    run_ns = args.account in (None, "night_scout")
    run_lm = args.account in (None, "liver_manager")

    # ---- Test 1: シンプルな JSON 生成 ----
    print("\n[Test 1] シンプルな JSON 生成")
    try:
        result = call_gemini_json(
            'Return ONLY the following JSON, no other text: {"status": "ok", "message": "接続確認成功"}',
            temperature=0.1,
        )
        if "_error" in result:
            print(f"  [FAIL] JSON抽出失敗: {result.get('_raw', '')[:200]}")
            failed += 1
        else:
            print(f"  [PASS] status={result.get('status')!r} message={result.get('message', '?')!r}")
            passed += 1
    except Exception as e:
        print(f"  [FAIL] 例外: {e}")
        failed += 1

    # ---- Test 2: night_scout 品質チェック ----
    if run_ns and not args.quick:
        print("\n[Test 2] night_scout 下書き生成 + 品質チェック")
        ns_prompt = (
            "あなたは夜職スカウトマンです。一人称は「僕」を使ってください。\n"
            "キャバ嬢・夜職女性向けのSNS投稿を以下のJSONフォーマットで生成してください。\n"
            "フォーマット要件: body_md の1行目はキャッチーなフック（1文）、その後2行空ける、本文。\n"
            "怪しい・情報商材感・「絶対稼げる」等の表現は絶対NG。\n"
            "JSONのみを返してください。\n"
            "{\n"
            '  "title": "夜職女性向けタイトル（20字以内）",\n'
            '  "body_md": "Threads形式本文（1行フック\\n\\n\\n本文）",\n'
            '  "score": 70,\n'
            '  "brand_risk_score": 10,\n'
            '  "post_mode": "trust"\n'
            "}"
        )
        try:
            result = call_gemini_json(ns_prompt, temperature=0.8)
            if "_error" in result:
                print(f"  [FAIL] JSON抽出失敗: {result.get('_raw', '')[:200]}")
                failed += 1
            else:
                body = result.get("body_md", "")
                title = result.get("title", "?")
                score = result.get("score", "?")
                print(f"  title: {title!r}")
                print(f"  score: {score}  risk: {result.get('brand_risk_score', '?')}")
                print(f"  body_md 先頭80字: {body[:80]!r}")
                print("  --- 品質チェック ---")
                qfails = _print_quality(check_night_scout_quality(body))
                if qfails == 0:
                    print(f"  [PASS] night_scout 品質チェック通過")
                    passed += 1
                else:
                    print(f"  [WARN] night_scout 品質: {qfails}件のFAILあり")
                    failed += 1
        except Exception as e:
            print(f"  [FAIL] 例外: {e}")
            failed += 1

    # ---- Test 3: liver_manager 品質チェック ----
    if run_lm and not args.quick:
        print("\n[Test 3] liver_manager 下書き生成 + 品質チェック")
        lm_prompt = (
            "あなたはTikTokライバーマネージャーです。\n"
            "ライバー候補向けSNS投稿を以下のJSONフォーマットで生成してください。\n"
            "信頼感があり怪しくない雰囲気で。事務所営業っぽくしない。\n"
            "JSONのみを返してください。\n"
            "{\n"
            '  "title": "TikTokライバー向けタイトル（20字以内）",\n'
            '  "body_md": "Threads形式本文（1行フック\\n\\n\\n本文）",\n'
            '  "score": 70,\n'
            '  "brand_risk_score": 10,\n'
            '  "post_mode": "trust"\n'
            "}"
        )
        try:
            result = call_gemini_json(lm_prompt, temperature=0.8)
            if "_error" in result:
                print(f"  [FAIL] JSON抽出失敗: {result.get('_raw', '')[:200]}")
                failed += 1
            else:
                body = result.get("body_md", "")
                title = result.get("title", "?")
                print(f"  title: {title!r}")
                print(f"  score: {result.get('score', '?')}  risk: {result.get('brand_risk_score', '?')}")
                print(f"  body_md 先頭80字: {body[:80]!r}")
                print("  --- 品質チェック ---")
                qfails = _print_quality(check_liver_manager_quality(body))
                if qfails == 0:
                    print(f"  [PASS] liver_manager 品質チェック通過")
                    passed += 1
                else:
                    print(f"  [WARN] liver_manager 品質: {qfails}件のFAILあり")
                    failed += 1
        except Exception as e:
            print(f"  [FAIL] 例外: {e}")
            failed += 1

    # ---- Test 4: X 派生投稿（120文字確認） ----
    print("\n[Test 4] X 派生投稿 フォーマット確認（120文字以内）")
    x_prompt = (
        "以下のJSONでX（旧Twitter）向け投稿文を生成してください。\n"
        "要件: 120文字以内（厳守）、強い1文、怪しくない。JSONのみ返してください。\n"
        "{\n"
        '  "platform": "x",\n'
        '  "text": "X向け投稿文（120文字以内）",\n'
        '  "hashtags": "",\n'
        '  "status": "READY",\n'
        '  "reason": "通常投稿"\n'
        "}"
    )
    try:
        result = call_gemini_json(x_prompt, platform="x", temperature=0.7)
        if "_error" in result:
            print(f"  [FAIL] JSON抽出失敗: {result.get('_raw', '')[:200]}")
            failed += 1
        else:
            text = result.get("text", "")
            print(f"  text ({len(text)}文字): {text!r}")
            print("  --- 品質チェック ---")
            qfails = _print_quality(check_x_quality(text))
            if qfails == 0:
                passed += 1
            else:
                failed += 1
    except Exception as e:
        print(f"  [FAIL] 例外: {e}")
        failed += 1

    # ---- Test 5: Threads 派生投稿（2行空け確認） ----
    if not args.quick:
        print("\n[Test 5] Threads 派生投稿 フォーマット確認（2行空け）")
        th_prompt = (
            "以下のJSONでThreads向け投稿文を生成してください。\n"
            "要件: 1行目はキャッチーなフック、その後2行空ける、本文。怪しくない。\n"
            "JSONのみ返してください。\n"
            "{\n"
            '  "platform": "threads",\n'
            '  "text": "Threads形式投稿文（1行フック\\n\\n\\n本文）",\n'
            '  "hashtags": "",\n'
            '  "status": "READY",\n'
            '  "reason": "通常投稿"\n'
            "}"
        )
        try:
            result = call_gemini_json(th_prompt, platform="threads", temperature=0.7)
            if "_error" in result:
                print(f"  [FAIL] JSON抽出失敗: {result.get('_raw', '')[:200]}")
                failed += 1
            else:
                text = result.get("text", "")
                first_line = text.split("\n")[0] if text else ""
                print(f"  1行目フック: {first_line!r}")
                print(f"  全文({len(text)}文字) 先頭100字: {text[:100]!r}")
                print("  --- 品質チェック ---")
                qfails = _print_quality(check_threads_quality(text))
                if qfails == 0:
                    passed += 1
                else:
                    failed += 1
        except Exception as e:
            print(f"  [FAIL] 例外: {e}")
            failed += 1

    return passed, failed


# ------------------------------------------------------------------ #
# メイン
# ------------------------------------------------------------------ #

def main() -> None:
    parser = argparse.ArgumentParser(description="Gemini 実 API 接続確認 + 品質チェック")
    parser.add_argument("--account", choices=["night_scout", "liver_manager"],
                        help="品質チェックするアカウント（省略時は両方）")
    parser.add_argument("--quick", action="store_true",
                        help="フォーマット確認のみ（品質チェックの詳細生成をスキップ）")
    args = parser.parse_args()

    cfg = get_config_partial()
    if not cfg.get("gemini_api_key"):
        print("[SKIP] GEMINI_API_KEY が未設定のため test_gemini_real.py をスキップします")
        sys.exit(0)

    print("=" * 60)
    print("Gemini 実 API 接続確認 + 品質チェック")
    mode = "--quick モード" if args.quick else "フル品質チェックモード"
    print(f"モード: {mode}")
    print("=" * 60)

    passed, failed = run_tests(args)

    print("\n" + "=" * 60)
    print(f"結果: {passed} PASS / {failed} FAIL")
    if failed == 0:
        print("✓ すべてのテストが通過しました")
    else:
        print("! 一部テストに問題があります。Geminiの出力を確認してください")
        print("  品質WARNはプロンプトテンプレートの調整で改善できます")
    print("=" * 60)

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
