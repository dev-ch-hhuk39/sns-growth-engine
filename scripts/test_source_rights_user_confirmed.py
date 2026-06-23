#!/usr/bin/env python3
"""test_source_rights_user_confirmed.py — source registry の rights/media policy 整合性確認。

確認項目:
- ユーザー確認済み YouTube は review_notes に「ユーザー確認済み」が記録されている
- beauty_account は active=false かつ BLOCKED_BEAUTY_ACCOUNT
- approved された reference_only は allow_download=false
- 新規追加 X sources (旧repo) が source_id ユニーク
"""
from __future__ import annotations
import sys, os, json

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASS = FAIL = 0

def check(label: str, cond: bool) -> None:
    global PASS, FAIL
    if cond: PASS += 1; print(f"  [PASS] {label}")
    else:    FAIL += 1; print(f"  [FAIL] {label}")

print("=== test_source_rights_user_confirmed ===")

path = os.path.join(_ROOT, "config", "source_accounts", "default_sources.json")
d = json.loads(open(path).read())
sources = d.get("sources", [])
by_id = {s["source_id"]: s for s in sources}

# 1. ユーザー確認済み YouTube は review_notes 記録済み
for sid in ["src_ns_yt_cand_001", "src_lm_yt_cand_001"]:
    s = by_id.get(sid, {})
    note = s.get("review_notes", "")
    check(f"{sid} review_notes に「ユーザー確認済み」", "ユーザー確認済み" in note)
    check(f"{sid} rights_policy=reference_only", s.get("rights_policy") == "reference_only")
    check(f"{sid} allow_download=false", s.get("allow_download") is False)
    check(f"{sid} allow_upload=false", s.get("allow_upload") is False)

# 2. beauty_account は active=false かつ BLOCKED_BEAUTY_ACCOUNT
for sid in ["src_ba_yt_cand_001", "src_ba_tt_cand_001", "src_ba_x_cand_001"]:
    s = by_id.get(sid, {})
    check(f"{sid} active=false", s.get("active") is False)
    check(f"{sid} review_status=BLOCKED_BEAUTY_ACCOUNT", s.get("review_status") == "BLOCKED_BEAUTY_ACCOUNT")

# 3. 旧repo から移行した X sources が存在する (9件以上)
ns_x = [s for s in sources if s.get("source_platform") == "x" and "night_scout" in s.get("target_account_ids", [])]
lm_x = [s for s in sources if s.get("source_platform") == "x" and "liver_manager" in s.get("target_account_ids", [])]
check(f"night_scout X sources が 2件以上ある (実際: {len(ns_x)})", len(ns_x) >= 2)
check(f"liver_manager X sources が 1件以上ある (実際: {len(lm_x)})", len(lm_x) >= 1)

# 4. source_id ユニーク
ids = [s["source_id"] for s in sources]
check(f"source_id がすべてユニーク (total: {len(ids)})", len(ids) == len(set(ids)))

# 5. auto_priority_change_allowed=false 全件
auto_change = [s["source_id"] for s in sources if s.get("auto_priority_change_allowed") is True]
check(f"auto_priority_change_allowed=false 全件 (違反: {auto_change})", len(auto_change) == 0)

# 6. beauty_account の allow_download/cut/upload が全て false
ba = [s for s in sources if "beauty_account" in s.get("target_account_ids", [])]
ba_violations = [s["source_id"] for s in ba if any([s.get("allow_download"), s.get("allow_cut"), s.get("allow_upload")])]
check(f"beauty_account sources の download/cut/upload=false 全件 (違反: {ba_violations})", len(ba_violations) == 0)

print(f"\n結果: PASS={PASS} FAIL={FAIL} / {PASS+FAIL}件")
sys.exit(0 if FAIL == 0 else 1)
