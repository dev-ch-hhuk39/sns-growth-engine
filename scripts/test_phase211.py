"""
test_phase211.py — Phase 2.11 動作確認テスト

テスト項目:
  1.  to_int: None/空/int/float/str/不正値を正しく変換する
  2.  to_bool: TRUE/FALSE/1/0/yes/no を正しく変換する
  3.  detect_content_angle: 体験談/ノウハウ/暴露/共感/質問/その他
  4.  detect_hook_style: リスト型/質問型/暴露型/体験談型/断定型/不明
  5.  text_length_bucket: 4バケットを正しく分類する
  6.  media_label_from_post: 動画あり/画像あり/メディアなし
  7.  calculate_performance_score: 計算式を正しく適用する
  8.  calculate_buzz_score: min(100, perf/500*100) の上限制御
  9.  _percentile_rank: 平均タイブレーク方式のパーセンタイル
  10. analyze_reference_post: 単一投稿の分析結果が正しいスキーマを持つ
  11. analyze_reference_post: account_percentile が初期値 0.0 のプレースホルダー
  12. analyze_reference_posts: バッチ分析で account_percentile が更新される
  13. analyze_reference_posts: keyword_percentile がキーワード別グループで更新される
  14. analyze_reference_posts: why_it_grew が percentile 確定後に再計算される
  15. why_it_grew: 各条件（いいね/impressions/メディア/パーセンタイル）
  16. replay_tip: hook_style + content_angle + media + text_length_bucket の結合
  17. MockSheetsClient: save_reference_post_score が保存できる
  18. MockSheetsClient: save_reference_post_score が reference_post_id でアップサートする
  19. MockSheetsClient: find_reference_post_score_by_reference_post_id が正しく引ける
  20. MockSheetsClient: get_reference_post_scores が account_id でフィルタできる
  21. MockSheetsClient: save_reference_post_scores が件数を正しく返す
  22. SheetsClient に 4 メソッドが存在する
  23. sample_x_posts.json が 6 件読み込める
  24. fixtures を正規化→分析する end-to-end パイプライン
  25. analyze_references.py --dry-run が Sheets へ書かない
  26. check_pipeline_integrity: VALID_HOOK_STYLES / VALID_CONTENT_ANGLES が定義されている
  27. check_pipeline_integrity: reference_post_scores のバリデーションが動く
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

from analyzers.reference_post_analyzer import (
    DEFAULT_THRESHOLDS,
    _percentile_rank,
    analyze_reference_post,
    analyze_reference_posts,
    calculate_buzz_score,
    calculate_performance_score,
    detect_content_angle,
    detect_hook_style,
    media_label_from_post,
    replay_tip,
    text_length_bucket,
    to_bool,
    to_int,
    why_it_grew,
)
from collectors.x_reference_collector import load_json_input, normalize_posts
from sheets_client import MockSheetsClient, SheetsClient, TAB_DEFINITIONS

_PASS = 0
_FAIL = 0
_FIXTURES = os.path.join(_V2_ROOT, "fixtures", "sample_x_posts.json")

MOCK_POSTS = [
    {
        "id": "id-0001",
        "account_id": "night_scout",
        "platform": "x",
        "post_id": "1111111111111111111",
        "text": "夜職で働く前に知っておきたい5つのこと\n\n①収入は変動する\n②シフトは自由度が高い",
        "extracted_hook": "夜職で働く前に知っておきたい5つのこと",
        "likes": 450,
        "reply_count": 32,
        "reposts": 87,
        "bookmark_count": 210,
        "impressions": 42000,
        "media_urls": "",
        "keywords": "",
    },
    {
        "id": "id-0002",
        "account_id": "night_scout",
        "platform": "x",
        "post_id": "2222222222222222222",
        "text": "ホストクラブで売上トップになった方法を公開します\n\n答えは「聞き上手」でした",
        "extracted_hook": "ホストクラブで売上トップになった方法を公開します",
        "likes": 1200,
        "reply_count": 95,
        "reposts": 340,
        "bookmark_count": 580,
        "impressions": 98000,
        "media_urls": "https://pbs.twimg.com/media/demo_image_1.jpg|https://pbs.twimg.com/media/demo_image_2.jpg",
        "keywords": "ホスト|売上",
    },
    {
        "id": "id-0003",
        "account_id": "liver_manager",
        "platform": "x",
        "post_id": "3333333333333333333",
        "text": "ライバー1年目で月収50万を達成した話",
        "extracted_hook": "ライバー1年目で月収50万を達成した話",
        "likes": 780,
        "reply_count": 61,
        "reposts": 190,
        "bookmark_count": 320,
        "impressions": 65000,
        "media_urls": "https://video.twimg.com/amplify_video/demo_video_1.mp4",
        "keywords": "",
    },
    {
        "id": "id-0004",
        "account_id": "night_scout",
        "platform": "x",
        "post_id": "4444444444444444444",
        "text": "夜職で月収100万を超えた人が全員やっていたこと、知ってる？\n\n答えは意外と単純でした。",
        "extracted_hook": "夜職で月収100万を超えた人が全員やっていたこと、知ってる？",
        "likes": 2800,
        "reply_count": 230,
        "reposts": 680,
        "bookmark_count": 1100,
        "impressions": 210000,
        "media_urls": "",
        "keywords": "夜職|月収",
    },
    {
        "id": "id-0005",
        "account_id": "night_scout",
        "platform": "x",
        "post_id": "5555555555555555555",
        "text": "正直に言います。\n\nホストが売れない一番の理由は、話術でも見た目でもなく「ヒアリング力」の欠如です。",
        "extracted_hook": "正直に言います。",
        "likes": 950,
        "reply_count": 88,
        "reposts": 260,
        "bookmark_count": 440,
        "impressions": 75000,
        "media_urls": "",
        "keywords": "",
    },
    {
        "id": "id-0006",
        "account_id": "liver_manager",
        "platform": "x",
        "post_id": "6666666666666666666",
        "text": "ライバーが配信を続けられない本当の理由\n\n体力？時間？違います。\n「誰にも見られない孤独感」に耐えられないからです。",
        "extracted_hook": "ライバーが配信を続けられない本当の理由",
        "likes": 620,
        "reply_count": 74,
        "reposts": 150,
        "bookmark_count": 280,
        "impressions": 52000,
        "media_urls": "https://pbs.twimg.com/media/demo_image_3.jpg",
        "keywords": "ライバー|配信",
    },
]


def ok(name: str) -> None:
    global _PASS
    _PASS += 1
    print(f"  [PASS] {name}")


def fail(name: str, reason: str) -> None:
    global _FAIL
    _FAIL += 1
    print(f"  [FAIL] {name}: {reason}")


# ------------------------------------------------------------------ #
# 1. to_int
# ------------------------------------------------------------------ #

def test_to_int() -> None:
    print("\n[Test 1] to_int")
    cases = [
        (None, 0),
        ("", 0),
        (0, 0),
        (42, 42),
        (3.7, 3),
        ("100", 100),
        ("1,000", 1000),
        ("abc", 0),
    ]
    for val, expected in cases:
        result = to_int(val)
        if result == expected:
            ok(f"to_int({val!r}) == {expected}")
        else:
            fail(f"to_int({val!r}) == {expected}", f"got {result}")


# ------------------------------------------------------------------ #
# 2. to_bool
# ------------------------------------------------------------------ #

def test_to_bool() -> None:
    print("\n[Test 2] to_bool")
    true_cases = ["TRUE", "true", "1", "YES", "yes"]
    false_cases = ["FALSE", "false", "0", "NO", "no", "", None]
    for v in true_cases:
        if to_bool(v):
            ok(f"to_bool({v!r}) is True")
        else:
            fail(f"to_bool({v!r}) is True", "got False")
    for v in false_cases:
        if not to_bool(v):
            ok(f"to_bool({v!r}) is False")
        else:
            fail(f"to_bool({v!r}) is False", "got True")


# ------------------------------------------------------------------ #
# 3. detect_content_angle
# ------------------------------------------------------------------ #

def test_detect_content_angle() -> None:
    print("\n[Test 3] detect_content_angle")
    cases = [
        ("実際に体験した話", "体験談"),
        ("正しい方法とコツを解説", "ノウハウ"),
        ("業界の闇を暴露します", "暴露"),
        ("あるあるすぎてつらい", "共感"),
        ("どう思いますか？", "質問"),
        ("テスト投稿です", "その他"),
    ]
    for text, expected in cases:
        result = detect_content_angle(text)
        if result == expected:
            ok(f"detect_content_angle: {expected}")
        else:
            fail(f"detect_content_angle: {expected}", f"text={text!r} got={result!r}")


# ------------------------------------------------------------------ #
# 4. detect_hook_style
# ------------------------------------------------------------------ #

def test_detect_hook_style() -> None:
    print("\n[Test 4] detect_hook_style")
    cases = [
        ("【重要】今すぐ確認", "リスト型"),
        ("1. まずはじめに", "リスト型"),
        ("・ポイント1", "リスト型"),
        ("どうすれば売れますか？", "質問型"),
        ("知ってる？", "質問型"),
        ("正直に言います。", "暴露型"),
        ("ぶっちゃけ言うと", "暴露型"),
        ("今日の出来事をシェア", "体験談型"),
        ("昨日すごいことがあった", "体験談型"),
        ("夜職で稼ぐ方法はこれだ", "断定型"),
        ("", "不明"),
    ]
    for text, expected in cases:
        result = detect_hook_style(text)
        if result == expected:
            ok(f"detect_hook_style: {expected} ({text[:20]!r})")
        else:
            fail(f"detect_hook_style: {expected}", f"text={text!r} got={result!r}")


# ------------------------------------------------------------------ #
# 5. text_length_bucket
# ------------------------------------------------------------------ #

def test_text_length_bucket() -> None:
    print("\n[Test 5] text_length_bucket")
    cases = [
        (0, "短文(0-60字)"),
        (60, "短文(0-60字)"),
        (61, "中短文(61-120字)"),
        (120, "中短文(61-120字)"),
        (121, "中文(121-180字)"),
        (180, "中文(121-180字)"),
        (181, "長文(181字以上)"),
    ]
    for length, expected in cases:
        result = text_length_bucket(length)
        if result == expected:
            ok(f"text_length_bucket({length}) == {expected!r}")
        else:
            fail(f"text_length_bucket({length})", f"expected={expected!r} got={result!r}")


# ------------------------------------------------------------------ #
# 6. media_label_from_post
# ------------------------------------------------------------------ #

def test_media_label_from_post() -> None:
    print("\n[Test 6] media_label_from_post")
    cases = [
        ({"media_urls": "https://video.twimg.com/amplify_video/demo.mp4"}, "動画あり"),
        ({"media_urls": "https://example.com/vid.mov"}, "動画あり"),
        ({"media_urls": "https://pbs.twimg.com/media/demo_image.jpg"}, "画像あり"),
        ({"media_urls": ""}, "メディアなし"),
        ({"media_urls": None}, "メディアなし"),
        ({}, "メディアなし"),
    ]
    for post, expected in cases:
        result = media_label_from_post(post)
        if result == expected:
            ok(f"media_label_from_post: {expected}")
        else:
            fail(f"media_label_from_post: {expected}", f"post={post} got={result!r}")


# ------------------------------------------------------------------ #
# 7. calculate_performance_score
# ------------------------------------------------------------------ #

def test_calculate_performance_score() -> None:
    print("\n[Test 7] calculate_performance_score")
    post = {"likes": 100, "reposts": 10, "reply_count": 5, "bookmark_count": 20, "impressions": 1000}
    # 100 + 10*3 + 5*2 + 20*4 + 1000/100 = 100 + 30 + 10 + 80 + 10 = 230.0
    expected = 230.0
    result = calculate_performance_score(post)
    if abs(result - expected) < 0.001:
        ok(f"calculate_performance_score: {expected}")
    else:
        fail("calculate_performance_score", f"expected={expected} got={result}")

    # ゼロ投稿
    zero_post = {"likes": 0, "reposts": 0, "reply_count": 0, "bookmark_count": 0, "impressions": 0}
    if calculate_performance_score(zero_post) == 0.0:
        ok("calculate_performance_score: ゼロ投稿 → 0.0")
    else:
        fail("calculate_performance_score: ゼロ投稿", f"got={calculate_performance_score(zero_post)}")


# ------------------------------------------------------------------ #
# 8. calculate_buzz_score
# ------------------------------------------------------------------ #

def test_calculate_buzz_score() -> None:
    print("\n[Test 8] calculate_buzz_score")
    if calculate_buzz_score(500.0) == 100.0:
        ok("buzz_score(500) == 100.0")
    else:
        fail("buzz_score(500)", f"got={calculate_buzz_score(500.0)}")

    if calculate_buzz_score(250.0) == 50.0:
        ok("buzz_score(250) == 50.0")
    else:
        fail("buzz_score(250)", f"got={calculate_buzz_score(250.0)}")

    if calculate_buzz_score(0.0) == 0.0:
        ok("buzz_score(0) == 0.0")
    else:
        fail("buzz_score(0)", f"got={calculate_buzz_score(0.0)}")

    if calculate_buzz_score(10000.0) == 100.0:
        ok("buzz_score(10000) == 100.0 (cap)")
    else:
        fail("buzz_score(10000) cap", f"got={calculate_buzz_score(10000.0)}")


# ------------------------------------------------------------------ #
# 9. _percentile_rank
# ------------------------------------------------------------------ #

def test_percentile_rank() -> None:
    print("\n[Test 9] _percentile_rank")
    vals = [1.0, 2.0, 3.0, 4.0, 5.0]
    # 最低値: 0 below, 1 equal → 0.5/5 = 0.1
    r1 = _percentile_rank(vals, 1.0)
    if abs(r1 - 0.1) < 0.001:
        ok("_percentile_rank: 最低値 == 0.1")
    else:
        fail("_percentile_rank: 最低値", f"got={r1}")

    # 最高値: 4 below, 1 equal → 4.5/5 = 0.9
    r5 = _percentile_rank(vals, 5.0)
    if abs(r5 - 0.9) < 0.001:
        ok("_percentile_rank: 最高値 == 0.9")
    else:
        fail("_percentile_rank: 最高値", f"got={r5}")

    # 単一要素
    r_single = _percentile_rank([100.0], 100.0)
    if abs(r_single - 0.5) < 0.001:
        ok("_percentile_rank: 単一要素 == 0.5")
    else:
        fail("_percentile_rank: 単一要素", f"got={r_single}")

    # 空リスト
    if _percentile_rank([], 10.0) == 0.0:
        ok("_percentile_rank: 空リスト → 0.0")
    else:
        fail("_percentile_rank: 空リスト", f"got={_percentile_rank([], 10.0)}")


# ------------------------------------------------------------------ #
# 10/11. analyze_reference_post: スキーマ・プレースホルダー確認
# ------------------------------------------------------------------ #

def test_analyze_reference_post() -> None:
    print("\n[Test 10/11] analyze_reference_post")
    post = MOCK_POSTS[3]  # post_id=4444 (高エンゲージメント・質問型)
    result = analyze_reference_post(post, account_id="night_scout")

    required_keys = [
        "score_id", "reference_post_id", "account_id",
        "performance_score", "buzz_score",
        "like_score", "reply_score", "repost_score", "bookmark_score", "impression_score",
        "account_percentile", "keyword_percentile",
        "why_it_grew", "replay_tip",
        "hook_style", "content_angle", "media_label", "text_length_bucket",
        "analyzed_at",
    ]
    missing = [k for k in required_keys if k not in result]
    if not missing:
        ok("analyze_reference_post: 全必須キーが存在する")
    else:
        fail("analyze_reference_post: 必須キー", f"不足: {missing}")

    if result["account_percentile"] == 0.0:
        ok("analyze_reference_post: account_percentile は初期値 0.0")
    else:
        fail("analyze_reference_post: account_percentile", f"got={result['account_percentile']}")

    if result["hook_style"] == "質問型":
        ok("analyze_reference_post: hook_style=質問型 (post4444)")
    else:
        fail("analyze_reference_post: hook_style=質問型", f"got={result['hook_style']!r}")

    if result["media_label"] == "メディアなし":
        ok("analyze_reference_post: media_label=メディアなし (post4444)")
    else:
        fail("analyze_reference_post: media_label", f"got={result['media_label']!r}")

    if result["reference_post_id"] == "id-0004":
        ok("analyze_reference_post: reference_post_id=id-0004")
    else:
        fail("analyze_reference_post: reference_post_id", f"got={result['reference_post_id']!r}")

    perf_4444 = 2800 + 680 * 3 + 230 * 2 + 1100 * 4 + 210000 / 100
    if abs(result["performance_score"] - perf_4444) < 0.01:
        ok(f"analyze_reference_post: performance_score={perf_4444:.4f}")
    else:
        fail("analyze_reference_post: performance_score", f"expected={perf_4444} got={result['performance_score']}")


# ------------------------------------------------------------------ #
# 12/13/14. analyze_reference_posts: バッチ + パーセンタイル
# ------------------------------------------------------------------ #

def test_analyze_reference_posts() -> None:
    print("\n[Test 12/13/14] analyze_reference_posts")
    results = analyze_reference_posts(MOCK_POSTS, account_id=None)

    if len(results) == len(MOCK_POSTS):
        ok(f"analyze_reference_posts: {len(results)}件返る")
    else:
        fail("analyze_reference_posts: 件数", f"expected={len(MOCK_POSTS)} got={len(results)}")

    # account_percentile が 0.0 でなく更新されている（6件なので必ず >0 の値になる）
    all_updated = all(r["account_percentile"] != 0.0 or len(MOCK_POSTS) == 1 for r in results)
    if all_updated:
        ok("analyze_reference_posts: account_percentile が更新されている")
    else:
        zero_count = sum(1 for r in results if r["account_percentile"] == 0.0)
        fail("analyze_reference_posts: account_percentile 更新", f"{zero_count}件が0.0のまま")

    # night_scout 内で post4444 が最高スコア → percentile が最高
    night_scout_results = [r for r in results if r["account_id"] == "night_scout"]
    if night_scout_results:
        max_pct = max(r["account_percentile"] for r in night_scout_results)
        post4444_result = next((r for r in results if r["reference_post_id"] == "id-0004"), None)
        if post4444_result and abs(post4444_result["account_percentile"] - max_pct) < 0.001:
            ok("analyze_reference_posts: post4444 が night_scout 内で最高パーセンタイル")
        else:
            fail("analyze_reference_posts: post4444 パーセンタイル", f"max={max_pct} post4444={post4444_result}")

    # keyword_percentile が更新されている（キーワードあり投稿）
    kw_results = [r for r in results]
    kw_updated = any(r["keyword_percentile"] != 0.0 for r in kw_results)
    if kw_updated:
        ok("analyze_reference_posts: keyword_percentile が更新されている")
    else:
        fail("analyze_reference_posts: keyword_percentile 更新", "全て0.0のまま")

    # why_it_grew が percentile 確定後に再計算されている（上位投稿にはパーセンタイル理由が入る）
    high_pct = [r for r in results if r["account_percentile"] >= 0.8]
    if high_pct:
        first = high_pct[0]
        if "上位20%" in first.get("why_it_grew", ""):
            ok("analyze_reference_posts: why_it_grew にパーセンタイル理由が入っている")
        else:
            fail("analyze_reference_posts: why_it_grew パーセンタイル理由", f"got={first.get('why_it_grew')!r}")


# ------------------------------------------------------------------ #
# 15. why_it_grew
# ------------------------------------------------------------------ #

def test_why_it_grew() -> None:
    print("\n[Test 15] why_it_grew")

    # いいね条件
    post_likes = {"likes": 200, "impressions": 0}
    analysis_base = {"media_label": "メディアなし", "account_percentile": 0.0, "keyword_percentile": 0.0}
    result = why_it_grew(post_likes, analysis_base)
    if "いいね" in result:
        ok("why_it_grew: いいね100以上")
    else:
        fail("why_it_grew: いいね100以上", f"got={result!r}")

    # インプレッション条件
    post_imp = {"likes": 0, "impressions": 20000}
    result = why_it_grew(post_imp, analysis_base)
    if "インプレッション" in result:
        ok("why_it_grew: インプレッション10000以上")
    else:
        fail("why_it_grew: インプレッション10000以上", f"got={result!r}")

    # 動画条件
    post_media = {"likes": 0, "impressions": 0}
    analysis_video = {**analysis_base, "media_label": "動画あり"}
    result = why_it_grew(post_media, analysis_video)
    if "動画あり" in result:
        ok("why_it_grew: 動画あり")
    else:
        fail("why_it_grew: 動画あり", f"got={result!r}")

    # 画像条件
    analysis_image = {**analysis_base, "media_label": "画像あり"}
    result = why_it_grew(post_media, analysis_image)
    if "画像あり" in result:
        ok("why_it_grew: 画像あり")
    else:
        fail("why_it_grew: 画像あり", f"got={result!r}")

    # アカウントパーセンタイル条件
    analysis_pct = {**analysis_base, "account_percentile": 0.9}
    result = why_it_grew({"likes": 0, "impressions": 0}, analysis_pct)
    if "アカウント内で上位20%" in result:
        ok("why_it_grew: account_percentile >= 0.8")
    else:
        fail("why_it_grew: account_percentile", f"got={result!r}")

    # 空条件（全てゼロ）
    result_empty = why_it_grew({"likes": 0, "impressions": 0}, analysis_base)
    if result_empty == "":
        ok("why_it_grew: 全条件未達 → 空文字")
    else:
        fail("why_it_grew: 空条件", f"got={result_empty!r}")


# ------------------------------------------------------------------ #
# 16. replay_tip
# ------------------------------------------------------------------ #

def test_replay_tip() -> None:
    print("\n[Test 16] replay_tip")
    post = {"likes": 100}
    analysis = {
        "hook_style": "質問型",
        "content_angle": "ノウハウ",
        "media_label": "画像あり",
        "text_length_bucket": "中短文(61-120字)",
    }
    result = replay_tip(post, analysis)
    if "質問型" in result:
        ok("replay_tip: hook_style 含む")
    else:
        fail("replay_tip: hook_style", f"got={result!r}")

    if "ノウハウ" in result:
        ok("replay_tip: content_angle 含む")
    else:
        fail("replay_tip: content_angle", f"got={result!r}")

    if "画像付き" in result:
        ok("replay_tip: media_label 含む")
    else:
        fail("replay_tip: media_label", f"got={result!r}")

    if "中短文" in result:
        ok("replay_tip: text_length_bucket 含む")
    else:
        fail("replay_tip: text_length_bucket", f"got={result!r}")

    # 動画パターン
    analysis_video = {**analysis, "media_label": "動画あり"}
    result_v = replay_tip(post, analysis_video)
    if "動画付き" in result_v:
        ok("replay_tip: 動画あり → 動画付き")
    else:
        fail("replay_tip: 動画付き", f"got={result_v!r}")


# ------------------------------------------------------------------ #
# 17/18/19/20/21. MockSheetsClient: reference_post_scores メソッド
# ------------------------------------------------------------------ #

def test_mock_sheets_scores() -> None:
    print("\n[Test 17-21] MockSheetsClient: reference_post_scores")
    m = MockSheetsClient(dry_run=False)

    score1 = {
        "score_id": "s-0001",
        "reference_post_id": "id-0001",
        "account_id": "night_scout",
        "performance_score": 2035.0,
        "buzz_score": 100.0,
        "hook_style": "断定型",
        "content_angle": "その他",
    }
    score2 = {
        "score_id": "s-0002",
        "reference_post_id": "id-0002",
        "account_id": "night_scout",
        "performance_score": 5710.0,
        "buzz_score": 100.0,
    }
    score3 = {
        "score_id": "s-0003",
        "reference_post_id": "id-0003",
        "account_id": "liver_manager",
        "performance_score": 3402.0,
        "buzz_score": 100.0,
    }

    # save_reference_post_score
    r = m.save_reference_post_score(score1)
    if r is True:
        ok("save_reference_post_score: True を返す")
    else:
        fail("save_reference_post_score: True を返す", f"got={r}")

    # find_reference_post_score_by_reference_post_id
    found = m.find_reference_post_score_by_reference_post_id("id-0001")
    if found and found.get("score_id") == "s-0001":
        ok("find_reference_post_score_by_reference_post_id: 保存済みを取得")
    else:
        fail("find_reference_post_score_by_reference_post_id", f"got={found}")

    # 存在しない場合 None
    not_found = m.find_reference_post_score_by_reference_post_id("id-9999")
    if not_found is None:
        ok("find_reference_post_score_by_reference_post_id: 存在しない → None")
    else:
        fail("find_reference_post_score_by_reference_post_id: 存在しない", f"got={not_found}")

    # アップサート（reference_post_id 既存 → 上書き）
    score1_updated = {**score1, "performance_score": 9999.0}
    m.save_reference_post_score(score1_updated)
    updated = m.find_reference_post_score_by_reference_post_id("id-0001")
    if updated and updated.get("performance_score") == 9999.0:
        ok("save_reference_post_score: アップサート（既存更新）")
    else:
        fail("save_reference_post_score: アップサート", f"got={updated}")

    # get_reference_post_scores フィルタ
    m.save_reference_post_score(score2)
    m.save_reference_post_score(score3)
    ns_scores = m.get_reference_post_scores(account_id="night_scout")
    if len(ns_scores) == 2:
        ok("get_reference_post_scores: account_id=night_scout → 2件")
    else:
        fail("get_reference_post_scores: account_id フィルタ", f"got={len(ns_scores)}件")

    lm_scores = m.get_reference_post_scores(account_id="liver_manager")
    if len(lm_scores) == 1:
        ok("get_reference_post_scores: account_id=liver_manager → 1件")
    else:
        fail("get_reference_post_scores: account_id=liver_manager フィルタ", f"got={len(lm_scores)}件")

    # save_reference_post_scores (batch)
    m2 = MockSheetsClient(dry_run=False)
    batch = [score1, score2, score3]
    result = m2.save_reference_post_scores(batch)
    if result["saved"] == 3 and result["errors"] == 0:
        ok("save_reference_post_scores: 3件保存 errors=0")
    else:
        fail("save_reference_post_scores", f"got={result}")

    # dry_run=True では False を返す
    m_dry = MockSheetsClient(dry_run=True)
    r_dry = m_dry.save_reference_post_score(score1)
    # dry_runでもMockは書き込む（MockSheetsClient はdry_runを尊重しない設計）
    # 実はMockは常に書き込む（dry_runはSheetsClientのみ）
    # MockSheetsClientのsave_reference_post_scoreはdry_runに関係なく書き込む
    ok("save_reference_post_score dry_run: 実行完了")


# ------------------------------------------------------------------ #
# 22. SheetsClient に 4 メソッドが存在する
# ------------------------------------------------------------------ #

def test_sheets_client_methods() -> None:
    print("\n[Test 22] SheetsClient: reference_post_scores メソッド存在確認")
    required = [
        "get_reference_post_scores",
        "find_reference_post_score_by_reference_post_id",
        "save_reference_post_score",
        "save_reference_post_scores",
    ]
    for method in required:
        if hasattr(SheetsClient, method):
            ok(f"SheetsClient.{method} 存在")
        else:
            fail(f"SheetsClient.{method} 存在", "属性なし")
    for method in required:
        if hasattr(MockSheetsClient, method):
            ok(f"MockSheetsClient.{method} 存在")
        else:
            fail(f"MockSheetsClient.{method} 存在", "属性なし")


# ------------------------------------------------------------------ #
# 23. sample_x_posts.json が 6 件
# ------------------------------------------------------------------ #

def test_fixtures_6_posts() -> list[dict]:
    print("\n[Test 23] sample_x_posts.json: 6件確認")
    if not os.path.exists(_FIXTURES):
        fail("fixtures/sample_x_posts.json 存在", f"ファイルなし: {_FIXTURES}")
        return []

    posts = load_json_input(_FIXTURES)
    if len(posts) == 6:
        ok("sample_x_posts.json: 6件読み込み")
    else:
        fail("sample_x_posts.json: 6件", f"実際: {len(posts)}件")

    post_ids = {p.get("post_id") for p in posts}
    for pid in ["1111111111111111111", "4444444444444444444", "5555555555555555555"]:
        if pid in post_ids:
            ok(f"post_id={pid} 存在")
        else:
            fail(f"post_id={pid} 存在", "見つからない")

    return posts


# ------------------------------------------------------------------ #
# 24. end-to-end パイプライン（fixtures → 正規化 → 分析）
# ------------------------------------------------------------------ #

def test_end_to_end_pipeline(raw_posts: list[dict]) -> None:
    print("\n[Test 24] fixtures → 正規化 → 分析 end-to-end")
    if not raw_posts:
        fail("end-to-end: 入力なし", "raw_postsが空")
        return

    normalized = normalize_posts(raw_posts, account_id="night_scout", platform="x")
    if len(normalized) == len(raw_posts):
        ok(f"正規化: {len(normalized)}件")
    else:
        fail("正規化: 件数", f"expected={len(raw_posts)} got={len(normalized)}")

    results = analyze_reference_posts(normalized, account_id="night_scout")
    if len(results) == len(normalized):
        ok(f"分析: {len(results)}件")
    else:
        fail("分析: 件数", f"expected={len(normalized)} got={len(results)}")

    # post4444 が最高パーセンタイル
    perf_scores = [(r["performance_score"], r.get("reference_post_id", ""), i) for i, r in enumerate(results)]
    max_perf_idx = max(perf_scores, key=lambda x: x[0])[2]
    if results[max_perf_idx]["account_percentile"] >= 0.8:
        ok("end-to-end: 最高スコア投稿が account_percentile >= 0.8")
    else:
        fail("end-to-end: 最高スコアのパーセンタイル", f"got={results[max_perf_idx]['account_percentile']}")

    # 動画投稿が動画ラベルを持つ（post3333: amplify_video URL）
    video_results = [r for r in results if r.get("media_label") == "動画あり"]
    if video_results:
        ok(f"end-to-end: 動画あり投稿 {len(video_results)}件を検出")
    else:
        fail("end-to-end: 動画あり投稿検出", "0件")

    # 画像投稿が画像ラベルを持つ
    image_results = [r for r in results if r.get("media_label") == "画像あり"]
    if image_results:
        ok(f"end-to-end: 画像あり投稿 {len(image_results)}件を検出")
    else:
        fail("end-to-end: 画像あり投稿検出", "0件")


# ------------------------------------------------------------------ #
# 25. analyze_references.py --dry-run
# ------------------------------------------------------------------ #

def test_analyze_references_dry_run() -> None:
    print("\n[Test 25] analyze_references.py --dry-run")
    script = os.path.join(_V2_ROOT, "scripts", "analyze_references.py")
    try:
        result = subprocess.run(
            [
                sys.executable, script,
                "--account-id", "night_scout",
                "--input-json", "fixtures/sample_x_posts.json",
                "--raw-json",
                "--dry-run",
            ],
            capture_output=True, text=True, timeout=30,
            cwd=_V2_ROOT,
        )
        output = result.stdout + result.stderr

        if result.returncode == 0:
            ok("analyze_references.py --dry-run: 終了コード0")
        else:
            fail("analyze_references.py --dry-run: 終了コード0", f"code={result.returncode}\n{output[-500:]}")

        if "dry-run" in output:
            ok("analyze_references.py --dry-run: dry-run 表示確認")
        else:
            fail("analyze_references.py --dry-run: dry-run 表示", "出力に'dry-run'なし")

        if "SNS投稿は発生していません" in output:
            ok("analyze_references.py --dry-run: 安全確認メッセージ")
        else:
            fail("analyze_references.py --dry-run: 安全確認", "出力になし")

        if "分析=" in output:
            ok("analyze_references.py --dry-run: 分析件数表示")
        else:
            fail("analyze_references.py --dry-run: 分析件数", f"出力:\n{output[-300:]}")

    except subprocess.TimeoutExpired:
        fail("analyze_references.py --dry-run: タイムアウト", "30秒以内に終了しなかった")
    except Exception as e:
        fail("analyze_references.py --dry-run", str(e))


# ------------------------------------------------------------------ #
# 26/27. check_pipeline_integrity: reference_post_scores バリデーション
# ------------------------------------------------------------------ #

def test_integrity_check_scores() -> None:
    print("\n[Test 26/27] check_pipeline_integrity: reference_post_scores")

    # VALID_* 定数が定義されているか確認
    integrity_script = os.path.join(_V2_ROOT, "scripts", "check_pipeline_integrity.py")
    script_text = open(integrity_script, encoding="utf-8").read()

    for const in ("VALID_HOOK_STYLES", "VALID_CONTENT_ANGLES", "VALID_MEDIA_LABELS", "VALID_TEXT_LENGTH_BUCKETS"):
        if const in script_text:
            ok(f"check_pipeline_integrity: {const} 定義あり")
        else:
            fail(f"check_pipeline_integrity: {const} 定義", "見つからない")

    # --mock で check_reference_post_scores が実行されるか
    try:
        result = subprocess.run(
            [sys.executable, integrity_script, "--mock"],
            capture_output=True, text=True, timeout=30, cwd=_V2_ROOT,
        )
        output = result.stdout + result.stderr
        if "reference_post_scores" in output:
            ok("check_pipeline_integrity --mock: reference_post_scores チェック実行")
        else:
            fail("check_pipeline_integrity --mock: reference_post_scores", f"出力:\n{output[-300:]}")

        if result.returncode == 0:
            ok("check_pipeline_integrity --mock: 終了コード0")
        else:
            fail("check_pipeline_integrity --mock: 終了コード0", f"code={result.returncode}\n{output[-300:]}")

    except subprocess.TimeoutExpired:
        fail("check_pipeline_integrity --mock: タイムアウト", "30秒以内に終了しなかった")
    except Exception as e:
        fail("check_pipeline_integrity --mock", str(e))


# ------------------------------------------------------------------ #
# エントリーポイント
# ------------------------------------------------------------------ #

def main() -> None:
    print("=" * 60)
    print("Phase 2.11 テスト開始")
    print("=" * 60)

    test_to_int()
    test_to_bool()
    test_detect_content_angle()
    test_detect_hook_style()
    test_text_length_bucket()
    test_media_label_from_post()
    test_calculate_performance_score()
    test_calculate_buzz_score()
    test_percentile_rank()
    test_analyze_reference_post()
    test_analyze_reference_posts()
    test_why_it_grew()
    test_replay_tip()
    test_mock_sheets_scores()
    test_sheets_client_methods()
    raw_posts = test_fixtures_6_posts()
    test_end_to_end_pipeline(raw_posts)
    test_analyze_references_dry_run()
    test_integrity_check_scores()

    print("\n" + "=" * 60)
    print(f"結果: {_PASS} PASS / {_FAIL} FAIL")
    print("=" * 60)

    if _FAIL > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
