#!/usr/bin/env python3
"""参考投稿を質的ルーブリックで採点する標準 CLI（内容適合の人手評価軸・genuinely new）。

既存の analyze_references.py は「アカウントトーン適合 + バズ/実績軸」を採点する。
本 CLI はそれとは別の、投稿内容そのものの質を見る質的ルーブリックを追加する:

  - hook_score        : 冒頭フックの強さ（最初の一行で読者を掴めるか）
  - insight_score     : 悩み解決・気づきの深さ
  - cta_score         : LINE / DM / プロフィール導線の自然さ
  - originality_score : 独自性（模倣リスクの裏返し）
  - reuse_risk_score  : 素材・表現の流用リスク（高いほど危険）
  - total_score       : 加重合算
  - recommended_use   : REFERENCE_ONLY / IDEA_SEED

結果は `reference_post_scores` タブの質的ルーブリック列に書き込む。

安全方針（プロジェクト CLAUDE.md 準拠）:
  - 既定は採点プランのみ（PLAN_ONLY）。本番 Sheets 書き込みは --apply かつ --confirm-score の両方が必要。
  - beauty_account は対象外（draft_only）。
  - 流用リスクが高い / 権利未確認 / 第三者メディア流用不可 の投稿は recommended_use=REFERENCE_ONLY。
    自動投稿対象には一切しない（採点は参考分析であり投稿生成ではない）。
  - secret 値・本文生データは出力しない（出力は採点結果の要約のみ）。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

ALLOWED_ACCOUNTS = {"night_scout", "liver_manager"}

# 投稿生成に使ってよいかの推奨。REFERENCE_ONLY は「参考のみ・流用不可」。
RECOMMEND_REFERENCE_ONLY = "REFERENCE_ONLY"
RECOMMEND_IDEA_SEED = "IDEA_SEED"

# アカウント別ルーブリック。CTA 導線と刺さる文脈のキーワードを定義する。
RUBRICS: dict[str, dict[str, list[str]]] = {
    "night_scout": {
        # 夜職女性に刺さる文脈
        "audience": ["夜職", "ホスト", "キャバ", "風俗", "水商売", "ナイトワーク", "病み", "メンタル", "恋", "お金"],
        # 悩み解決・気づきの文脈
        "insight": ["解決", "理由", "方法", "コツ", "実は", "知らない", "失敗", "後悔", "対処", "抜け出"],
        # 自然な導線
        "cta": ["line", "ライン", "dm", "プロフ", "プロフィール", "相談", "公式", "受付", "メッセージ"],
    },
    "liver_manager": {
        "audience": ["配信", "ライバー", "ギフト", "リスナー", "事務所", "マネージャ", "デビュー", "顔出し", "稼ぐ", "副業"],
        "insight": ["伸ば", "コツ", "方法", "理由", "実は", "知らない", "失敗", "継続", "視聴維持", "実践"],
        "cta": ["line", "ライン", "dm", "プロフ", "プロフィール", "相談", "応募", "面談", "募集"],
    },
}

# 第三者メディア流用リスクを示すマーカー（本文中の引用・転載の気配）。
REUSE_RISK_MARKERS = ["引用", "転載", "出典", "リポスト", "repost", "via @", "©", "(c)", "画像お借り", "拝借"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clip(value: float, lo: float = 0.0, hi: float = 5.0) -> float:
    return max(lo, min(hi, value))


def _text_of(post: dict[str, Any]) -> str:
    return str(post.get("text", "") or post.get("content", "") or post.get("body", ""))


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in ("true", "1", "yes", "y"):
        return True
    if s in ("false", "0", "no", "n", ""):
        return False
    return default


def _count_hits(text: str, words: list[str]) -> int:
    low = text.lower()
    return sum(1 for w in words if w.lower() in low)


def score_hook(text: str) -> float:
    """冒頭フックの強さ。最初の一行に疑問・数字・強い切り出しがあるか（純粋関数）。"""
    if not text.strip():
        return 0.0
    first = text.strip().splitlines()[0]
    score = 1.0
    if "?" in first or "？" in first:
        score += 1.5
    if any(ch.isdigit() for ch in first):
        score += 1.0
    if any(k in first for k in ("実は", "知らない", "なぜ", "衝撃", "本当は", "知って", "やめ")):
        score += 1.5
    if len(first) <= 40:  # 短く鋭い冒頭は掴みやすい
        score += 0.5
    return _clip(score)


def score_insight(text: str, account_id: str) -> float:
    """悩み解決・気づきの深さ（純粋関数）。"""
    rubric = RUBRICS.get(account_id, RUBRICS["night_scout"])
    hits = _count_hits(text, rubric["insight"])
    score = min(3.0, hits * 1.0)
    if len(text) >= 120:  # ある程度の本文量＝具体性
        score += 1.0
    if "→" in text or "ステップ" in text or "①" in text:  # 構造化された解説
        score += 1.0
    return _clip(score)


def score_cta(text: str, account_id: str) -> float:
    """LINE/DM 等への導線の自然さ（純粋関数）。"""
    rubric = RUBRICS.get(account_id, RUBRICS["night_scout"])
    hits = _count_hits(text, rubric["cta"])
    if hits == 0:
        return 0.0
    score = min(4.0, 1.5 + hits * 1.0)
    # 押し売り感（連続CTA・煽り）は減点
    if text.count("!") + text.count("！") >= 4:
        score -= 1.0
    return _clip(score)


def score_originality(text: str, account_id: str) -> float:
    """独自性。型どおりのテンプレ感が薄いほど高い（純粋関数）。"""
    rubric = RUBRICS.get(account_id, RUBRICS["night_scout"])
    audience_hits = _count_hits(text, rubric["audience"])
    score = 2.0 + min(2.0, audience_hits * 0.7)  # 文脈固有語があるほど独自
    if any(m in text for m in ("テンプレ", "コピペ", "まとめ", "ランキング")):
        score -= 1.0
    if len(set(text)) < 20:  # 極端に単調
        score -= 1.0
    return _clip(score)


def score_reuse_risk(text: str, post: dict[str, Any]) -> float:
    """素材・表現の流用リスク（高いほど危険・純粋関数）。"""
    score = 0.0
    # 第三者メディア流用不可フラグが立っている / 許諾未確認
    if not _as_bool(post.get("can_reuse_media"), default=False):
        score += 1.5
    rights = str(post.get("rights_status", "unknown")).strip().lower()
    if rights in ("", "unknown"):
        score += 1.5
    # 本文中の引用・転載マーカー
    score += min(2.0, _count_hits(text, REUSE_RISK_MARKERS) * 1.0)
    return _clip(score)


def score_post(post: dict[str, Any], account_id: str) -> dict[str, Any]:
    """1 投稿を質的ルーブリックで採点する（純粋関数・Sheets 不要）。"""
    text = _text_of(post)
    hook = score_hook(text)
    insight = score_insight(text, account_id)
    cta = score_cta(text, account_id)
    originality = score_originality(text, account_id)
    reuse_risk = score_reuse_risk(text, post)

    # 加重合算。reuse_risk は減点として効かせる。
    total = round(hook * 1.0 + insight * 1.2 + cta * 1.0 + originality * 0.8 - reuse_risk * 1.0, 2)
    total = max(0.0, total)

    rights = str(post.get("rights_status", "unknown")).strip().lower()
    can_reuse = _as_bool(post.get("can_reuse_media"), default=False)
    # 流用リスクが高い / 権利未確認 / 流用不可 は必ず参考のみ
    if reuse_risk >= 2.5 or rights in ("", "unknown") or not can_reuse:
        recommended = RECOMMEND_REFERENCE_ONLY
    else:
        recommended = RECOMMEND_IDEA_SEED

    reason_parts = [
        f"hook={hook}", f"insight={insight}", f"cta={cta}",
        f"originality={originality}", f"reuse_risk={reuse_risk}",
    ]
    if recommended == RECOMMEND_REFERENCE_ONLY:
        reason_parts.append("流用リスク/権利未確認のため参考のみ")
    reason = "; ".join(reason_parts)

    return {
        "hook_score": hook,
        "insight_score": insight,
        "cta_score": cta,
        "originality_score": originality,
        "reuse_risk_score": reuse_risk,
        "total_score": total,
        "recommended_use": recommended,
        "reason": reason,
    }


def build_scores(posts: list[dict[str, Any]], account_id: str, stamp: str) -> list[dict[str, Any]]:
    """採点行（reference_post_scores 用）を組み立てる（純粋関数）。"""
    scored_at = now_iso()
    rows: list[dict[str, Any]] = []
    for i, post in enumerate(posts, 1):
        s = score_post(post, account_id)
        collected_post_id = str(post.get("post_id", "") or post.get("collected_post_id", ""))
        rows.append({
            "score_id": f"qscore_{account_id}_{stamp}_{i:03d}",
            "account_id": account_id,
            "collected_post_id": collected_post_id,
            "hook_score": s["hook_score"],
            "insight_score": s["insight_score"],
            "cta_score": s["cta_score"],
            "originality_score": s["originality_score"],
            "reuse_risk_score": s["reuse_risk_score"],
            "total_score": s["total_score"],
            "reason": s["reason"],
            "recommended_use": s["recommended_use"],
            "scored_at": scored_at,
        })
    # 安全不変条件: 採点は投稿生成ではない（status 列を持たせない / 投稿対象化しない）。
    for r in rows:
        assert "status" not in r, "score rows must not carry a postable status"
    return rows


def _load_posts(input_json: str | None, apply: bool, account_id: str):
    if input_json:
        with open(input_json, encoding="utf-8") as f:
            data = json.load(f)
        return None, data.get("posts", data.get("source_account_posts", []))
    if apply:
        from config_loader import get_config
        from sheets_client import SheetsClient
        cfg = get_config()
        client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
        rows = [dict(r) for r in client._ws("source_account_posts").get_all_records()
                if str(r.get("account_id", "")) in ("", account_id)]
        return client, rows
    return None, []


def _append_many(client, logical: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    sheet = client._ws(logical)
    headers = sheet.row_values(1)
    sheet.append_rows(
        [[str(row.get(h, "")) for h in headers] for row in rows],
        value_input_option="USER_ENTERED",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="score reference posts with a qualitative rubric (gated)")
    parser.add_argument("--account-id", required=True, choices=["night_scout", "liver_manager", "beauty_account"])
    parser.add_argument("--input-json", help='{"posts":[...]} for offline scoring/testing')
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--apply", action="store_true", help="write scores to Sheets (needs --confirm-score)")
    parser.add_argument("--confirm-score", action="store_true", help="explicit confirmation for real write")
    args = parser.parse_args()

    if args.account_id == "beauty_account":
        print(json.dumps({"status": "BLOCKED", "reason": "beauty_account は対象外（draft_only）"}, ensure_ascii=False))
        return 1

    client, posts = _load_posts(args.input_json, args.apply, args.account_id)
    posts = posts[: max(0, args.limit)]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    rows = build_scores(posts, args.account_id, stamp)

    ref_only = sum(1 for r in rows if r["recommended_use"] == RECOMMEND_REFERENCE_ONLY)
    summary = {
        "account_id": args.account_id,
        "scored_count": len(rows),
        "reference_only_count": ref_only,
        "idea_seed_count": len(rows) - ref_only,
        "top_total": max((r["total_score"] for r in rows), default=None),
    }

    if not args.apply:
        print(json.dumps({"status": "PLAN_ONLY", **summary,
                          "notes": "書き込み未実行。本番書き込みは --apply --confirm-score。"},
                         ensure_ascii=False, indent=2))
        return 0
    if not args.confirm_score:
        print(json.dumps({"status": "BLOCKED", "reason": "--apply には --confirm-score が必要", **summary},
                         ensure_ascii=False))
        return 1
    if client is None:
        print(json.dumps({"status": "BLOCKED", "reason": "--apply は本番 Sheets 用です（--input-json と併用不可）"},
                         ensure_ascii=False))
        return 1
    if not rows:
        print(json.dumps({"status": "NO_DATA", "reason": "採点対象の source_account_posts がありません"},
                         ensure_ascii=False))
        return 1

    _append_many(client, "reference_post_scores", rows)
    print(json.dumps({"status": "SCORED", **summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
