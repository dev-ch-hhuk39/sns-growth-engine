#!/usr/bin/env python3
"""test_ready_queue_requires_rights_clear_media.py — media を使う投稿は権利クリア素材のみ、
media_required な行は使える media が無ければ投稿ブロックされることを固定する。"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from media.queue_media_attach import is_media_rights_clear  # noqa: E402
import scripts.process_threads_queue as ptq  # noqa: E402

PASS = FAIL = 0


def check(label: str, cond: bool) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}")


print("=== test_ready_queue_requires_rights_clear_media ===\n")

# 権利判定
clear = {"status": "APPROVED", "rights_policy": "owned", "reuse_policy": "reuse_ok", "media_policy": "ok"}
ref_only = {"status": "APPROVED", "rights_policy": "owned", "reuse_policy": "no_reuse"}
unknown_rights = {"status": "APPROVED", "rights_policy": "unknown"}
plan_only = {"status": "APPROVED", "rights_policy": "owned", "media_policy": "plan_only"}
high_risk = {"status": "APPROVED", "rights_policy": "owned", "media_reuse_risk": "high"}

check("owned/approved 素材は権利クリア", is_media_rights_clear(clear) is True)
check("reuse_policy=no_reuse は権利クリアでない", is_media_rights_clear(ref_only) is False)
check("rights_policy=unknown は権利クリアでない", is_media_rights_clear(unknown_rights) is False)
check("media_policy=plan_only は権利クリアでない", is_media_rights_clear(plan_only) is False)
check("media_reuse_risk=high は権利クリアでない", is_media_rights_clear(high_risk) is False)

# media_required だが使える media が無い行 → ブロック
row_missing = {"queue_id": "q1", "media_required": "true", "media_url": "", "media_status": ""}
r1 = ptq.resolve_queue_media(row_missing)
check("media_required で media 無し → MEDIA_REQUIRED_MISSING でブロック", r1["block_reason"] == "MEDIA_REQUIRED_MISSING")
check("media_required で media 無し → media_usable=False", r1["media_usable"] is False)

# media_status が ATTACHED でないと使えない
row_pending = {"queue_id": "q2", "media_required": "true", "media_url": "https://x/y.jpg", "media_status": "PENDING"}
r2 = ptq.resolve_queue_media(row_pending)
check("media_status=PENDING は media_usable=False", r2["media_usable"] is False)

# 正常系（ATTACHED + url）
row_ok = {"queue_id": "q3", "media_required": "true", "media_url": "https://x/y.jpg", "media_status": "ATTACHED"}
r3 = ptq.resolve_queue_media(row_ok)
check("ATTACHED + url なら media_usable=True かつブロックなし", r3["media_usable"] is True and r3["block_reason"] == "")

print("\n--- 結果 ---")
print(f"PASS: {PASS} / FAIL: {FAIL}")
sys.exit(0 if FAIL == 0 else 1)
