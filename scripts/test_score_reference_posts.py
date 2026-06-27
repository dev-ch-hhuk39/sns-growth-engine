#!/usr/bin/env python3
"""score_reference_posts の質的ルーブリック純粋ロジックを検証する（Sheets 不要）。"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/score_reference_posts.py"


def _load():
    spec = importlib.util.spec_from_file_location("score_reference_posts", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    mod = _load()
    checks: list[tuple[str, bool]] = []

    strong = {
        "post_id": "p_strong",
        "text": "なぜ夜職で病む人が多いのか？実は3つの理由がある→①睡眠②人間関係③お金。LINEで相談受付中",
        "rights_status": "owned", "can_reuse_media": True,
    }
    weak = {"post_id": "p_weak", "text": "おはよう", "rights_status": "owned", "can_reuse_media": True}

    s = mod.score_post(strong, "night_scout")
    w = mod.score_post(weak, "night_scout")
    checks.append(("強い投稿の total > 弱い投稿", s["total_score"] > w["total_score"]))
    checks.append(("hook 0..5", 0.0 <= s["hook_score"] <= 5.0))
    checks.append(("cta 検出（LINE）", s["cta_score"] > 0.0))
    checks.append(("弱い投稿の cta=0", w["cta_score"] == 0.0))

    # 権利未確認 / 流用不可 は必ず REFERENCE_ONLY
    unknown = {"post_id": "p_u", "text": "実は知らないコツがある→LINEへ", "rights_status": "unknown", "can_reuse_media": False}
    su = mod.score_post(unknown, "night_scout")
    checks.append(("権利未確認は REFERENCE_ONLY", su["recommended_use"] == mod.RECOMMEND_REFERENCE_ONLY))
    checks.append(("流用不可で reuse_risk>0", su["reuse_risk_score"] > 0.0))

    # 権利クリア & 低リスク → IDEA_SEED になりうる
    clear = {"post_id": "p_c", "text": "配信を伸ばすコツは継続→実は視聴維持が鍵。応募はDMへ", "rights_status": "owned", "can_reuse_media": True}
    sc = mod.score_post(clear, "liver_manager")
    checks.append(("権利クリア低リスクは IDEA_SEED", sc["recommended_use"] == mod.RECOMMEND_IDEA_SEED))

    rows = mod.build_scores([strong, unknown], "night_scout", "20260627000000")
    checks.append(("行数 = 入力数", len(rows) == 2))
    checks.append(("collected_post_id 紐付け", rows[0]["collected_post_id"] == "p_strong"))
    # 最重要安全不変条件: 採点行は投稿可能ステータスを持たない
    checks.append(("採点行に status を持たせない", all("status" not in r for r in rows)))
    checks.append(("必須列を含む", all(k in rows[0] for k in
                   ("score_id", "account_id", "hook_score", "total_score", "recommended_use", "scored_at"))))

    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {n}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
