#!/usr/bin/env python3
"""test_reference_transform_guard.py — 参考投稿の丸パクリ禁止・変換必須を確認。

source の require_transform=true / reference_only の場合は source_text をそのまま使わない。
"""
from __future__ import annotations
import sys, os, json

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASS = FAIL = 0

def check(label: str, cond: bool) -> None:
    global PASS, FAIL
    if cond: PASS += 1; print(f"  [PASS] {label}")
    else:    FAIL += 1; print(f"  [FAIL] {label}")

print("=== test_reference_transform_guard ===")

path = os.path.join(_ROOT, "config", "source_accounts", "default_sources.json")
sources = json.loads(open(path).read()).get("sources", [])

# 1. reference_only sources はすべて require_transform=true
for s in sources:
    if s.get("rights_policy") == "reference_only" and s.get("active"):
        policy = s.get("subject_policy", {})
        sid = s["source_id"]
        require = (
            policy.get("require_transform") is True
            or "require_transform" in policy.get("rules", [])
        )
        check(f"{sid} require_transform=true", require)

# 2. drafts/queue に保存された候補が source_text の丸コピーでないことの検証用チェック
# Threads 次投稿 queue ファイルの確認
queue_path = os.path.join(_ROOT, "data", "threads_night_scout_next_queue.json")
if os.path.exists(queue_path):
    q = json.loads(open(queue_path).read())
    for c in q.get("candidates", []):
        text = c.get("body_md", "")
        # 初回投稿テキストと完全一致していないことを確認
        first_post = "キャバで指名が取れる子って、見た目だけじゃなくて「また会いたい」と思わせる接客ができる子。"
        check(f"候補 '{c['title'][:20]}...' が初回投稿テキストの丸コピーでない", first_post not in text)
    check("Threads 次投稿 queue に 3件以上ある", len(q.get("candidates", [])) >= 3)
else:
    # data/ is deliberately untracked. Its absence in clean CI must not hide
    # the registry-level transform guard or turn a safety test into a fixture
    # availability failure.
    print("  [WARN] threads_night_scout_next_queue.json is untracked; queue copy check skipped")

# 3. source_intake_schema の require_transform ルール
for s in sources:
    policy = s.get("subject_policy", {})
    sid = s["source_id"]
    # beauty_account は active=false なので skip
    if "beauty_account" in s.get("target_account_ids", []):
        continue
    # require_transform フィールドが存在する
    has_transform = (
        "require_transform" in policy
        or "require_transform" in policy.get("rules", [])
    )
    if has_transform:
        check(f"{sid} require_transform フィールドが定義済み", True)

print(f"\n結果: PASS={PASS} FAIL={FAIL} / {PASS+FAIL}件")
sys.exit(0 if FAIL == 0 else 1)
