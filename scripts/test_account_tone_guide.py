"""
test_account_tone_guide.py - アカウント別トンマナ強制テスト

テスト項目:
  1. ACCOUNT_NG_TONE_PATTERNS が seeds.py に定義されているか
  2. night_scout の NG パターン件数・内容が正しいか
  3. liver_manager の NG パターン件数・内容が正しいか
  4. check_ng_tone() が night_scout NG テキストを正しく検出するか
  5. check_ng_tone() が liver_manager NG テキストを正しく検出するか
  6. check_ng_tone() が OK テキストを誤検知しないか（night_scout）
  7. check_ng_tone() が OK テキストを誤検知しないか（liver_manager）
  8. get_derivative_template() が night_scout 専用 X テンプレートを優先返却するか
  9. PROMPT_TEMPLATE_SEEDS に night_scout 専用 X テンプレートが存在するか
  10. 専用テンプレートに NG トーン禁止事項が記述されているか
  11. 良い投稿例が NG パターンに引っかからないか
  12. _DRAFT_GEN_NIGHT_SCOUT に X/Threads スタイルガイドが含まれるか
  13. _DRAFT_GEN_NIGHT_SCOUT に NG トーン禁止事項が含まれるか
  14. _DRAFT_GEN_LIVER_MANAGER に NG トーン禁止事項が含まれるか
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# ------------------------------------------------------------------ #
# ユーティリティ
# ------------------------------------------------------------------ #

_pass = 0
_fail = 0


def ok(msg: str) -> None:
    global _pass
    _pass += 1
    print(f"  [PASS] {msg}")


def ng(msg: str) -> None:
    global _fail
    _fail += 1
    print(f"  [FAIL] {msg}")


# ------------------------------------------------------------------ #
# テスト1: ACCOUNT_NG_TONE_PATTERNS の存在確認
# ------------------------------------------------------------------ #

print("\n[テスト1] ACCOUNT_NG_TONE_PATTERNS の存在確認")
try:
    from seeds import ACCOUNT_NG_TONE_PATTERNS
    ok("ACCOUNT_NG_TONE_PATTERNS が seeds.py に存在する")
except ImportError as e:
    ng(f"ImportError: {e}")
    ACCOUNT_NG_TONE_PATTERNS = {}

# ------------------------------------------------------------------ #
# テスト2: night_scout NG パターン件数確認
# ------------------------------------------------------------------ #

print("\n[テスト2] night_scout NGパターン件数確認")
ns_patterns = ACCOUNT_NG_TONE_PATTERNS.get("night_scout", [])
if len(ns_patterns) >= 10:
    ok(f"night_scout: {len(ns_patterns)} 件のNGパターン定義済み")
else:
    ng(f"night_scout: NGパターン不足 ({len(ns_patterns)} 件、10件以上必要)")

required_ns = ["お疲れ様", "君はすごい", "ずっと応援"]
for pattern in required_ns:
    if any(pattern in p for p in ns_patterns) or pattern in ns_patterns:
        ok(f"night_scout NG に '{pattern}' が含まれる")
    else:
        ng(f"night_scout NG に '{pattern}' が含まれない")

# ------------------------------------------------------------------ #
# テスト3: liver_manager NG パターン件数確認
# ------------------------------------------------------------------ #

print("\n[テスト3] liver_manager NGパターン件数確認")
lm_patterns = ACCOUNT_NG_TONE_PATTERNS.get("liver_manager", [])
if len(lm_patterns) >= 5:
    ok(f"liver_manager: {len(lm_patterns)} 件のNGパターン定義済み")
else:
    ng(f"liver_manager: NGパターン不足 ({len(lm_patterns)} 件、5件以上必要)")

required_lm = ["誰でも稼げる", "スマホ1台で"]
for pattern in required_lm:
    if any(pattern in p for p in lm_patterns) or pattern in lm_patterns:
        ok(f"liver_manager NG に '{pattern}' が含まれる")
    else:
        ng(f"liver_manager NG に '{pattern}' が含まれない")

# ------------------------------------------------------------------ #
# テスト4: night_scout NG テキスト検出
# ------------------------------------------------------------------ #

print("\n[テスト4] check_ng_tone() night_scout NG テキスト検出")
try:
    from tone_checker import check_ng_tone

    ng_texts_ns = [
        ("お疲れ様", "今日もお疲れ様！頑張ってるね。"),
        ("応援系", "君はすごい、ずっと応援してるよ。自分を信じてね。"),
        ("美容系", "新しいリップやアイシャドウを試してみて！スキンケアも大事。"),
    ]
    for label, text in ng_texts_ns:
        result = check_ng_tone(text, "night_scout")
        if result.status == "FAIL":
            ok(f"night_scout '{label}' NGを正しく検出: {result.matched_patterns}")
        else:
            ng(f"night_scout '{label}' NGを検出できなかった (status={result.status})")
except ImportError as e:
    ng(f"tone_checker インポートエラー: {e}")

# ------------------------------------------------------------------ #
# テスト5: liver_manager NG テキスト検出
# ------------------------------------------------------------------ #

print("\n[テスト5] check_ng_tone() liver_manager NG テキスト検出")
try:
    from tone_checker import check_ng_tone

    ng_texts_lm = [
        ("勧誘系", "誰でも稼げる！スマホ1台でOK。副業感覚で始められる！"),
        ("応援系", "一緒に頑張ろう！可能性がある！諦めないで！"),
    ]
    for label, text in ng_texts_lm:
        result = check_ng_tone(text, "liver_manager")
        if result.status == "FAIL":
            ok(f"liver_manager '{label}' NGを正しく検出: {result.matched_patterns}")
        else:
            ng(f"liver_manager '{label}' NGを検出できなかった (status={result.status})")
except ImportError as e:
    ng(f"tone_checker インポートエラー: {e}")

# ------------------------------------------------------------------ #
# テスト6: night_scout OK テキスト誤検知なし
# ------------------------------------------------------------------ #

print("\n[テスト6] check_ng_tone() night_scout OK テキスト誤検知なし")
try:
    from tone_checker import check_ng_tone

    ok_texts_ns = [
        "キャバで長く稼げる子って、見た目だけじゃなくて「また話したい」と思わせる返しが上手い。LINEも接客も、相手を気持ちよくさせる一言を積み重ねられる子は強いんだよね。",
        "店選びを間違えると、同じ努力でも結果が半分になる。面接でバック率だけ聞いて決めた子が、3ヶ月後に移籍したがってた。最初から聞くべきポイントがある。",
        "指名が取れる子と取れない子の違い、正直に言うと接客スキルより「続ける意志」の差だと思う。辞めずに続けた子が必ず強くなってる。",
    ]
    for i, text in enumerate(ok_texts_ns, 1):
        result = check_ng_tone(text, "night_scout")
        if result.status == "OK":
            ok(f"night_scout OK例{i}: 誤検知なし")
        else:
            ng(f"night_scout OK例{i}: 誤検知あり → {result.matched_patterns} | {text[:40]}...")
except ImportError as e:
    ng(f"tone_checker インポートエラー: {e}")

# ------------------------------------------------------------------ #
# テスト7: liver_manager OK テキスト誤検知なし
# ------------------------------------------------------------------ #

print("\n[テスト7] check_ng_tone() liver_manager OK テキスト誤検知なし")
try:
    from tone_checker import check_ng_tone

    ok_texts_lm = [
        "TikTokライブで月20万稼いでいる人の共通点を3つ挙げると、配信頻度・コメント返し・ギフトの活用方法。逆にいうと、これだけ意識すれば未経験でも3ヶ月で結果が出る。",
        "フォロワー1000人いるのに月収3万しかない人の配信を見ると、コメントを拾えていない。ギフトをくれた人を名前で呼んでいない。リスナーが「返ってくる」体験を作れていない。",
    ]
    for i, text in enumerate(ok_texts_lm, 1):
        result = check_ng_tone(text, "liver_manager")
        if result.status == "OK":
            ok(f"liver_manager OK例{i}: 誤検知なし")
        else:
            ng(f"liver_manager OK例{i}: 誤検知あり → {result.matched_patterns} | {text[:40]}...")
except ImportError as e:
    ng(f"tone_checker インポートエラー: {e}")

# ------------------------------------------------------------------ #
# テスト8: get_derivative_template() アカウント固有テンプレート優先確認
# ------------------------------------------------------------------ #

print("\n[テスト8] get_derivative_template() night_scout 専用テンプレート優先確認")
try:
    from prompt_loader import get_derivative_template

    tmpl = get_derivative_template(None, "x", account_id="night_scout")
    if tmpl:
        name = tmpl.get("template_name", "")
        if "night_scout" in name:
            ok(f"night_scout 専用 X テンプレートを優先返却: {name}")
        else:
            ng(f"汎用テンプレートが返された: {name}（night_scout専用テンプレートが優先されるべき）")
    else:
        ng("テンプレートが返されなかった")

    tmpl_lm = get_derivative_template(None, "x", account_id="liver_manager")
    if tmpl_lm:
        ok(f"liver_manager→汎用フォールバック: {tmpl_lm.get('template_name')}")
    else:
        ng("liver_manager 用テンプレートが返されなかった")
except ImportError as e:
    ng(f"prompt_loader インポートエラー: {e}")

# ------------------------------------------------------------------ #
# テスト9: PROMPT_TEMPLATE_SEEDS に night_scout 専用 X テンプレート存在確認
# ------------------------------------------------------------------ #

print("\n[テスト9] PROMPT_TEMPLATE_SEEDS night_scout 専用 X テンプレート存在確認")
try:
    from seeds import PROMPT_TEMPLATE_SEEDS

    ns_x = [
        t for t in PROMPT_TEMPLATE_SEEDS
        if t.get("account_id") == "night_scout"
        and "social_derivative_x" in t.get("template_name", "")
    ]
    if ns_x:
        ok(f"night_scout 専用 X テンプレートが存在: {ns_x[0]['template_name']}")
    else:
        ng("night_scout 専用 X テンプレートが PROMPT_TEMPLATE_SEEDS に存在しない")
except ImportError as e:
    ng(f"seeds インポートエラー: {e}")

# ------------------------------------------------------------------ #
# テスト10: night_scout 専用テンプレートに NG 禁止事項記述確認
# ------------------------------------------------------------------ #

print("\n[テスト10] night_scout 専用テンプレートの NGトーン禁止事項記述確認")
try:
    from seeds import PROMPT_TEMPLATE_SEEDS

    ns_x = [
        t for t in PROMPT_TEMPLATE_SEEDS
        if t.get("account_id") == "night_scout"
        and "social_derivative_x" in t.get("template_name", "")
    ]
    if ns_x:
        prompt_text = ns_x[0].get("prompt_text", "")
        checks = [
            ("応援系NG記述", "応援"),
            ("美容系NG記述", "美容"),
            ("ポエムNG記述", "ポエム"),
            ("120字要件", "120文字"),
            ("ハッシュタグNG", "ハッシュタグなし"),
        ]
        for label, keyword in checks:
            if keyword in prompt_text:
                ok(f"専用テンプレートに '{label}' ({keyword}) が含まれる")
            else:
                ng(f"専用テンプレートに '{label}' ({keyword}) が含まれない")
    else:
        ng("night_scout 専用 X テンプレートが存在しない")
except ImportError as e:
    ng(f"seeds インポートエラー: {e}")

# ------------------------------------------------------------------ #
# テスト11: 良い投稿例が NG パターンに引っかからないか
# ------------------------------------------------------------------ #

print("\n[テスト11] 良い投稿例の NG パターンチェック（誤検知なし確認）")
try:
    from tone_checker import check_ng_tone

    good_examples = [
        ("night_scout", "キャバで長く稼げる子って、見た目だけじゃなくて「また話したい」と思わせる返しが上手い。LINEも接客も、相手を気持ちよくさせる一言を積み重ねられる子は強いんだよね。"),
        ("liver_manager", "TikTokライブで月20万稼いでいる人の共通点を3つ挙げると、配信頻度・コメント返し・ギフトの活用方法。逆にいうと、これだけ意識すれば未経験でも3ヶ月で結果が出る。"),
    ]
    for account_id, text in good_examples:
        result = check_ng_tone(text, account_id)
        if result.status == "OK":
            ok(f"[{account_id}] 良い例が誤検知されない")
        else:
            ng(f"[{account_id}] 良い例が誤検知された: {result.matched_patterns} | {text[:40]}...")
except ImportError as e:
    ng(f"tone_checker インポートエラー: {e}")

# ------------------------------------------------------------------ #
# テスト12: _DRAFT_GEN_NIGHT_SCOUT にスタイルガイドが含まれるか
# ------------------------------------------------------------------ #

print("\n[テスト12] _DRAFT_GEN_NIGHT_SCOUT スタイルガイド記述確認")
try:
    from seeds import _DRAFT_GEN_NIGHT_SCOUT

    style_checks = [
        ("投稿スタイルセクション", "投稿スタイル"),
        ("Xルール", "ハッシュタグなし"),
        ("X文字数ルール", "120文字以内"),
        ("Threadsルール", "冒頭1行"),
        ("良い例", "長く稼げる"),
    ]
    for label, keyword in style_checks:
        if keyword in _DRAFT_GEN_NIGHT_SCOUT:
            ok(f"_DRAFT_GEN_NIGHT_SCOUT に '{label}' ({keyword}) が含まれる")
        else:
            ng(f"_DRAFT_GEN_NIGHT_SCOUT に '{label}' ({keyword}) が含まれない")
except ImportError as e:
    ng(f"seeds インポートエラー: {e}")

# ------------------------------------------------------------------ #
# テスト13: _DRAFT_GEN_NIGHT_SCOUT に NG トーン禁止事項が含まれるか
# ------------------------------------------------------------------ #

print("\n[テスト13] _DRAFT_GEN_NIGHT_SCOUT NGトーン禁止事項記述確認")
try:
    from seeds import _DRAFT_GEN_NIGHT_SCOUT

    ng_checks = [
        ("応援系NG", "薄い応援"),
        ("美容系NG", "美容"),
        ("ポエム系NG", "ポエム"),
        ("自己啓発系NG", "汎用自己啓発"),
    ]
    for label, keyword in ng_checks:
        if keyword in _DRAFT_GEN_NIGHT_SCOUT:
            ok(f"_DRAFT_GEN_NIGHT_SCOUT に '{label}' ({keyword}) NG記述あり")
        else:
            ng(f"_DRAFT_GEN_NIGHT_SCOUT に '{label}' ({keyword}) NG記述なし")
except ImportError as e:
    ng(f"seeds インポートエラー: {e}")

# ------------------------------------------------------------------ #
# テスト14: _DRAFT_GEN_LIVER_MANAGER に NG トーン禁止事項が含まれるか
# ------------------------------------------------------------------ #

print("\n[テスト14] _DRAFT_GEN_LIVER_MANAGER NGトーン禁止事項記述確認")
try:
    from seeds import _DRAFT_GEN_LIVER_MANAGER

    lm_ng_checks = [
        ("誰でも稼げる系NG", "誰でも稼げる"),
        ("事務所営業NG", "事務所営業"),
        ("ポエム系NG", "ポエム"),
        ("汎用自己啓発NG", "汎用自己啓発"),
    ]
    for label, keyword in lm_ng_checks:
        if keyword in _DRAFT_GEN_LIVER_MANAGER:
            ok(f"_DRAFT_GEN_LIVER_MANAGER に '{label}' ({keyword}) NG記述あり")
        else:
            ng(f"_DRAFT_GEN_LIVER_MANAGER に '{label}' ({keyword}) NG記述なし")
except ImportError as e:
    ng(f"seeds インポートエラー: {e}")

# ------------------------------------------------------------------ #
# 結果集計
# ------------------------------------------------------------------ #

print("\n" + "=" * 55)
total = _pass + _fail
print(f"  テスト結果: PASS {_pass} / FAIL {_fail} / 合計 {total}")
if _fail == 0:
    print("  ✓ 全テスト PASS")
else:
    print(f"  ✗ {_fail} 件のテストが FAIL")
print("=" * 55)

sys.exit(0 if _fail == 0 else 1)
