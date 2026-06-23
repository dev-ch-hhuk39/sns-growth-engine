#!/usr/bin/env python3
"""save_first_threads_post.py — 初回Threads実投稿の posted_results 保存スクリプト（一時使用）"""
from __future__ import annotations
import os, sys
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT); sys.path.insert(0, os.path.join(_ROOT, "src"))
try:
    from dotenv import load_dotenv; load_dotenv(os.path.join(_ROOT, ".env"))
except ImportError:
    pass

DRY_RUN = os.environ.get("SAVE_POSTED_RESULTS", "false").lower() not in ("1", "true")

from config_loader import get_config
from sheets_client import make_client

cfg = get_config()
client = make_client(cfg, dry_run=DRY_RUN)

result_id = client.save_result(
    draft_id="cli_direct_threads_first_post",
    account_id="night_scout",
    measurement_window="48h",
    platform="threads",
    post_id="18127402414723102",
    post_url="https://www.threads.com/@kyaba_consul_mizu/post/DZ6Drm5k9SL",
    posted_at="2026-06-23T00:00:00Z",
    status="POSTED",
    real_post="true",
    media_used="false",
    metrics_status="PENDING",
    text="キャバで指名が取れる子って、見た目だけじゃなくて「また会いたい」と思わせる接客ができる子。\n\n相手を気持ちよくさせる聞き方と返しを積み重ねられる子は、長く稼げるんだよね。",
    char_count=86,
    impressions=0, likes=0, reposts=0, replies=0,
    note="初回Threads実投稿 / permalink API取得済み / X は 402 ブロッカー維持",
)

mode = "DRY_RUN" if DRY_RUN else "REAL_WRITE"
print(f"[{mode}] save_result: result_id={result_id}")
if DRY_RUN:
    print("[INFO] 実書き込みは SAVE_POSTED_RESULTS=true で実行してください")
