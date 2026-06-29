#!/usr/bin/env python3
"""generate_threads_ideas_from_references.build_plan の安全ゲートを検証する。

最重要: 本 CLI は生成専用で投稿経路を持たず、実投稿は三重ゲート（全禁止）が必要。
候補は WAITING_REVIEW（worker 非対象=READY のみ）で書かれ、自動投稿はされない。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/generate_threads_ideas_from_references.py"


def _load():
    spec = importlib.util.spec_from_file_location("generate_threads_ideas_from_references", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _args(**kw):
    base = dict(account_id="night_scout", platform="threads", source="references",
                top_n=3, apply=False, confirm_generate=False)
    base.update(kw)
    return SimpleNamespace(**base)


def main() -> int:
    mod = _load()
    checks: list[tuple[str, bool]] = []

    p = mod.build_plan(_args())
    checks.append(("既定は PLAN_ONLY", p["status"] == "PLAN_ONLY"))
    # 最重要安全不変条件: 本 CLI は生成専用で投稿経路を持たない
    checks.append(("委譲先は投稿しない（生成専用）", p["safety"]["delegate_posts"] is False))
    checks.append(("実投稿は現状不可能", p["safety"]["real_post_possible_now"] is False))
    # 候補は WAITING_REVIEW で書かれる（正直な現実）
    checks.append(("候補 status は WAITING_REVIEW", p["safety"]["candidate_status"] == "WAITING_REVIEW"))
    checks.append(("WAITING_REVIEW は worker 非対象（READY のみ）", p["safety"]["worker_selectable"] is False))
    # 実投稿に必要なゲートが明示されている
    checks.append(("実投稿ゲートに ALLOW_REAL_THREADS_POST 含む",
                   "ALLOW_REAL_THREADS_POST=true" in p["safety"]["real_post_requires"]))
    checks.append(("人間ゲートは approve_queue", "approve_queue.py" in p["safety"]["human_gate"]))

    # source 切り替え
    checks.append(("references → generate_from_references",
                   p["delegate_script"] == "scripts/generate_from_references.py"))
    pc = mod.build_plan(_args(source="clips"))
    checks.append(("clips → generate_from_video_clips",
                   pc["delegate_script"] == "scripts/generate_from_video_clips.py"))

    # 実行ゲート
    p3 = mod.build_plan(_args(apply=True, confirm_generate=True))
    checks.append(("apply+confirm は WILL_RUN", p3["status"] == "WILL_RUN"))
    checks.append(("PLAN_ONLY(references) は --mock --dry-run",
                   "--mock" in p["delegate_argv"] and "--dry-run" in p["delegate_argv"]))

    checks.append(("x は BLOCKED", mod.build_plan(_args(platform="x"))["status"] == "BLOCKED"))
    checks.append(("beauty は BLOCKED", mod.build_plan(_args(account_id="beauty_account"))["status"] == "BLOCKED"))
    checks.append(("不正 source は BLOCKED", mod.build_plan(_args(source="bogus"))["status"] == "BLOCKED"))

    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {n}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
