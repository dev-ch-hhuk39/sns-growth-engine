#!/usr/bin/env python3
"""save_threads_next_queue.py — Threads night_scout 次投稿候補3案を drafts/queue に保存

実行方法:
  python3 scripts/save_threads_next_queue.py          # dry-run（Sheets書き込みなし）
  SAVE_DRAFTS=true python3 scripts/save_threads_next_queue.py  # Sheets に実際に書き込む
"""
from __future__ import annotations
import os, sys, json, pathlib, datetime

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT); sys.path.insert(0, os.path.join(_ROOT, "src"))
try:
    from dotenv import load_dotenv; load_dotenv(os.path.join(_ROOT, ".env"))
except ImportError:
    pass

DRY_RUN = os.environ.get("SAVE_DRAFTS", "false").lower() not in ("1", "true")

# ----- 投稿候補 3案 -----
# トンマナ: night_scout (夜職スカウト)
# Threads フォーマット: 冒頭1行フック → 空行2行 → 本文
# 初回投稿(86字)テーマ「聞き方・返し」の継続展開 + 別テーマ

CANDIDATES = [
    {
        "title": "[night_scout Threads #2] LINEの返しテンポ",
        "body_md": (
            "キャバで稼ぐ子のLINEって、文章の長さがちょうどいい。"
            "\n\n\n"
            "長すぎると重く見える。短すぎると雑に見える。"
            "「次に会いたい」と思わせる返しのテンポが身についてる子は、やっぱり数字を持ってるんだよね。"
        ),
        "platform": "threads",
        "candidate_type": "継続(接客テーマ)",
        "char_count": None,  # 自動計算
    },
    {
        "title": "[night_scout Threads #3] 店選びの失敗",
        "body_md": (
            "夜職で稼げない原因の半分は、店選びのミス。"
            "\n\n\n"
            "バック率が高くても客層が悪ければ指名は入らない。"
            "面接でバック率だけ聞いて決めた子が、3ヶ月後に移籍したがってた。最初から聞くべきポイントがある。"
        ),
        "platform": "threads",
        "candidate_type": "新テーマ(店選び)",
        "char_count": None,
    },
    {
        "title": "[night_scout Threads #4] 辞めずに続けられる子の特徴",
        "body_md": (
            "夜職を長く続けられる子には、共通点がある。"
            "\n\n\n"
            "「向いてないかも」と思ったときに、すぐ辞めるんじゃなくて原因を分析できること。"
            "接客の何が合ってないかを整理して、改善できる子が伸びていくんだよね。"
        ),
        "platform": "threads",
        "candidate_type": "新テーマ(継続・成長)",
        "char_count": None,
    },
]

# char_count 計算（空行除く本文の文字数）
for c in CANDIDATES:
    text_no_newlines = c["body_md"].replace("\n", "")
    c["char_count"] = len(text_no_newlines)

# ----- ローカルJSON保存 -----
data_path = pathlib.Path(_ROOT) / "data" / "threads_night_scout_next_queue.json"
data_path.parent.mkdir(parents=True, exist_ok=True)
payload = {
    "generated_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    "account_id": "night_scout",
    "platform": "threads",
    "status": "WAITING_REVIEW",
    "note": "実投稿は 48h metrics 確認後。review 通過後 PUBLISH_ENABLED=true で実行。",
    "candidates": CANDIDATES,
}
data_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"[JSON] saved: {data_path}")
for i, c in enumerate(CANDIDATES, 1):
    print(f"  [{i}] {c['title']} ({c['char_count']}字)")

# ----- Sheets 保存 -----
from config_loader import get_config
from sheets_client import make_client

cfg = get_config()
client = make_client(cfg, dry_run=DRY_RUN)

mode = "DRY_RUN" if DRY_RUN else "REAL_WRITE"
print(f"\n[Sheets/{mode}] drafts タブへ保存:")

draft_ids = []
for c in CANDIDATES:
    did = client.save_draft(
        account_id="night_scout",
        title=c["title"],
        body_md=c["body_md"],
        status="WAITING_REVIEW",
        platform=c["platform"],
        char_count=str(c["char_count"]),
        candidate_type=c["candidate_type"],
    )
    draft_ids.append(did)
    print(f"  draft_id={did}  {c['title']}")

if DRY_RUN:
    print("\n[INFO] 実書き込みは SAVE_DRAFTS=true で実行してください")

print(f"\n次のアクション: Threads 初回投稿(48h後) → メトリクス確認 → review → 実投稿")
