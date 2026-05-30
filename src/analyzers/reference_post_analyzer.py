"""
reference_post_analyzer.py — 参考投稿のパフォーマンス分析（Phase 2.11）

移植元: X_autopost_yoru/x_analyze_posts.py
スコア計算式: performance_score = likes + reposts×3 + reply_count×2 + bookmark_count×4 + impressions/100
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

JST = timezone(timedelta(hours=9))

DEFAULT_THRESHOLDS: dict[str, Any] = {
    "buzz_like_count": 100,
    "buzz_impression_count": 10000,
    "performance_score_per_100_buzz": 500,
    "relative_top_cutoff": 0.8,
}


def to_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (ValueError, TypeError):
        return 0


def to_bool(value: Any) -> bool:
    return str(value).strip().upper() in {"TRUE", "1", "YES"}


def detect_content_angle(text: str) -> str:
    lower = (text or "").lower()
    rules = [
        ("体験談", ["実際", "体験", "経験", "昔", "わたし", "自分"]),
        ("ノウハウ", ["方法", "コツ", "やり方", "ポイント", "攻略"]),
        ("暴露", ["裏", "暴露", "本音", "闇", "ぶっちゃけ"]),
        ("共感", ["あるある", "つらい", "わかる", "共感", "しんどい"]),
        ("質問", ["?", "？", "どう思う", "教えて", "ありますか"]),
    ]
    for label, patterns in rules:
        if any(pattern in lower for pattern in patterns):
            return label
    return "その他"


def detect_hook_style(text: str) -> str:
    first = (text or "").strip()
    if not first:
        return "不明"
    if first.startswith(("【", "[", "1.", "1 ", "・")):
        return "リスト型"
    if "?" in first[:40] or "？" in first[:40]:
        return "質問型"
    if any(word in first[:40] for word in ["実は", "ぶっちゃけ", "正直", "結論"]):
        return "暴露型"
    if any(word in first[:40] for word in ["今日", "昨日", "この前", "さっき"]):
        return "体験談型"
    return "断定型"


def text_length_bucket(length: int) -> str:
    if length <= 60:
        return "短文(0-60字)"
    if length <= 120:
        return "中短文(61-120字)"
    if length <= 180:
        return "中文(121-180字)"
    return "長文(181字以上)"


def media_label_from_post(post: dict[str, Any]) -> str:
    media_urls = str(post.get("media_urls") or "")
    if any(pat in media_urls for pat in [".mp4", ".mov", "amplify_video"]):
        return "動画あり"
    if media_urls.strip():
        return "画像あり"
    return "メディアなし"


def calculate_performance_score(post: dict[str, Any]) -> float:
    likes = to_int(post.get("likes"))
    reposts = to_int(post.get("reposts"))
    reply_count = to_int(post.get("reply_count"))
    bookmark_count = to_int(post.get("bookmark_count"))
    impressions = to_int(post.get("impressions"))
    return likes + reposts * 3 + reply_count * 2 + bookmark_count * 4 + impressions / 100.0


def calculate_buzz_score(
    performance_score: float, thresholds: dict[str, Any] | None = None
) -> float:
    divisor = (thresholds or DEFAULT_THRESHOLDS).get("performance_score_per_100_buzz", 500)
    return min(100.0, performance_score / divisor * 100.0)


def _percentile_rank(values: list[float], value: float) -> float:
    """pandas rank(pct=True, method='average') 相当のパーセンタイル順位。"""
    n = len(values)
    if n == 0:
        return 0.0
    below = sum(1 for v in values if v < value)
    equal = sum(1 for v in values if v == value)
    return (below + 0.5 * equal) / n


def why_it_grew(
    post: dict[str, Any],
    analysis: dict[str, Any],
    thresholds: dict[str, Any] | None = None,
) -> str:
    t = thresholds or DEFAULT_THRESHOLDS
    buzz_likes = t.get("buzz_like_count", 100)
    buzz_impressions = t.get("buzz_impression_count", 10000)
    cutoff = t.get("relative_top_cutoff", 0.8)
    reasons: list[str] = []
    if to_int(post.get("likes")) >= buzz_likes:
        reasons.append(f"いいね{buzz_likes}以上")
    if to_int(post.get("impressions")) >= buzz_impressions:
        reasons.append(f"インプレッション{buzz_impressions}以上")
    ml = analysis.get("media_label", "")
    if ml == "動画あり":
        reasons.append("動画あり")
    elif ml == "画像あり":
        reasons.append("画像あり")
    if analysis.get("account_percentile", 0.0) >= cutoff:
        reasons.append("同一アカウント内で上位20%")
    if analysis.get("keyword_percentile", 0.0) >= cutoff:
        reasons.append("同一キーワード群で上位20%")
    return "、".join(reasons)


def replay_tip(post: dict[str, Any], analysis: dict[str, Any]) -> str:
    parts: list[str] = []
    hook_style = analysis.get("hook_style", "")
    content_angle = analysis.get("content_angle", "")
    media_label = analysis.get("media_label", "")
    tl_bucket = analysis.get("text_length_bucket", "")
    if hook_style:
        parts.append(f"{hook_style}の書き出し")
    if content_angle:
        parts.append(f"{content_angle}の切り口")
    if "動画" in media_label:
        parts.append("動画付き")
    elif "画像" in media_label:
        parts.append("画像付き")
    if tl_bucket:
        parts.append(tl_bucket)
    return " / ".join(parts)


def analyze_reference_post(
    post: dict[str, Any],
    account_id: str | None = None,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """1件の参考投稿を分析してスコア行を返す。

    account_percentile / keyword_percentile は 0.0 プレースホルダー。
    analyze_reference_posts() でバッチ更新する。
    """
    t = thresholds or DEFAULT_THRESHOLDS
    text = str(post.get("text") or "")
    hook_source = str(post.get("extracted_hook") or text)

    perf = calculate_performance_score(post)
    likes = to_int(post.get("likes"))
    reposts = to_int(post.get("reposts"))
    reply_count = to_int(post.get("reply_count"))
    bookmark_count = to_int(post.get("bookmark_count"))
    impressions = to_int(post.get("impressions"))

    hook_style = detect_hook_style(hook_source)
    content_angle = detect_content_angle(text)
    ml = media_label_from_post(post)
    tl_bucket = text_length_bucket(len(text))
    buzz = calculate_buzz_score(perf, t)

    analysis: dict[str, Any] = {
        "score_id": str(uuid4()),
        "reference_post_id": str(post.get("id") or ""),
        "account_id": account_id or str(post.get("account_id") or ""),
        "performance_score": round(perf, 4),
        "buzz_score": round(buzz, 4),
        "like_score": likes,
        "reply_score": reply_count * 2,
        "repost_score": reposts * 3,
        "bookmark_score": bookmark_count * 4,
        "impression_score": round(impressions / 100.0, 4),
        "account_percentile": 0.0,
        "keyword_percentile": 0.0,
        "hook_style": hook_style,
        "content_angle": content_angle,
        "media_label": ml,
        "text_length_bucket": tl_bucket,
        "why_it_grew": "",
        "replay_tip": "",
        "analyzed_at": datetime.now(JST).isoformat(),
    }

    analysis["why_it_grew"] = why_it_grew(post, analysis, t)
    analysis["replay_tip"] = replay_tip(post, analysis)

    return analysis


def analyze_reference_posts(
    posts: list[dict[str, Any]],
    account_id: str | None = None,
    thresholds: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """複数の参考投稿をバッチ分析してスコアリストを返す。

    analyze_reference_post() を各投稿に適用した後、
    account_percentile / keyword_percentile をグループ内でバッチ更新する。
    """
    if not posts:
        return []

    t = thresholds or DEFAULT_THRESHOLDS
    results = [analyze_reference_post(p, account_id=account_id, thresholds=t) for p in posts]

    # account_percentile: account_id ごとにグループ化して計算
    account_groups: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(results):
        account_groups[r["account_id"]].append(i)

    for indices in account_groups.values():
        scores = [results[i]["performance_score"] for i in indices]
        for i in indices:
            results[i]["account_percentile"] = round(
                _percentile_rank(scores, results[i]["performance_score"]), 4
            )

    # keyword_percentile: keywords フィールドごとにグループ化して計算
    keyword_groups: dict[str, list[int]] = defaultdict(list)
    for i, p in enumerate(posts):
        kw = str(p.get("keywords") or "").strip() or "キーワードなし"
        keyword_groups[kw].append(i)

    for indices in keyword_groups.values():
        scores = [results[i]["performance_score"] for i in indices]
        for i in indices:
            results[i]["keyword_percentile"] = round(
                _percentile_rank(scores, results[i]["performance_score"]), 4
            )

    # percentile 確定後に why_it_grew / replay_tip を再計算
    for post, r in zip(posts, results):
        r["why_it_grew"] = why_it_grew(post, r, t)
        r["replay_tip"] = replay_tip(post, r)

    return results
