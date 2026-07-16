#!/usr/bin/env python3
"""process_one の dry-run で media が計画表示されること、media無し挙動が不変なこと、
duplicate guard が media_asset_id を考慮することを検証する（Sheets 書き込みなし・credentials不要）。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/process_threads_queue.py"


def _load():
    spec = importlib.util.spec_from_file_location("process_threads_queue", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class _FakeWS:
    def __init__(self, rows):
        self._rows = rows

    def get_all_records(self):
        return [dict(r) for r in self._rows]


class _FakeClient:
    """records() が読む social_derivatives / drafts / posted_results だけを返す。
    dry-run では append/update は呼ばれないので _ws のみ実装する。"""

    def __init__(self, tabs):
        self._tabs = tabs

    def _ws(self, logical):
        return _FakeWS(self._tabs.get(logical, []))


def main() -> int:
    mod = _load()
    checks: list[tuple[str, bool]] = []

    drafts = [{"draft_id": "d1", "body_md": "夜職で店を選ぶ時、時給だけで決める子はけっこう危ない。\n\n時給が高くても、客層や出勤ペース、相談しやすさが自分に合わないと続かない。\n\n大事なのは、条件が良い店より自分が無理なく続けられる店を選ぶこと。入る前に一度、譲れない条件を整理してみよう。"}]
    client = _FakeClient({"social_derivatives": [], "drafts": drafts, "posted_results": []})

    # 1. media無し queue → DRY_RUN, media_planned=False, 既存挙動
    row_plain = {"queue_id": "q1", "draft_id": "d1", "account_id": "night_scout", "platform": "threads"}
    out = mod.process_one(client, row_plain, dry_run=True, confirm_real_post=False)
    checks.append(("media無し→DRY_RUN", out["status"] == "DRY_RUN"))
    checks.append(("media無し→media_planned False", out["media_planned"] is False))
    checks.append(("media無し→DRY_RUN_PLAN_ONLY が付かない", "DRY_RUN_PLAN_ONLY" not in out["message"]))

    # 2. ATTACHED + url の queue → DRY_RUN, media_planned=True, 計画表示あり
    row_media = {**row_plain, "queue_id": "q2", "media_asset_id": "ma1",
                 "media_url": "https://res.cloudinary.com/x/card.png", "media_status": "ATTACHED"}
    out = mod.process_one(client, row_media, dry_run=True, confirm_real_post=False)
    checks.append(("media付き→DRY_RUN", out["status"] == "DRY_RUN"))
    checks.append(("media付き→media_planned True", out["media_planned"] is True))
    checks.append(("media付き→計画表示 DRY_RUN_PLAN_ONLY", "DRY_RUN_PLAN_ONLY" in out["message"]))
    checks.append(("media付き→media_asset_id 反映", out["media_asset_id"] == "ma1"))

    # 3. status が許可外（PENDING）→ media は計画されない（後方互換の text-only 扱い）
    row_pending = {**row_plain, "queue_id": "q3", "media_asset_id": "ma2",
                   "media_url": "https://x/p.png", "media_status": "PENDING"}
    out = mod.process_one(client, row_pending, dry_run=True, confirm_real_post=False)
    checks.append(("PENDING media→DRY_RUN", out["status"] == "DRY_RUN"))
    checks.append(("PENDING media→media_planned False", out["media_planned"] is False))

    # 4. duplicate guard: 同テキスト・同media_asset_id は重複
    dup = mod.duplicate_reason(
        queue_row={"queue_id": "qX", "account_id": "night_scout", "platform": "threads"},
        social=None, text="同じ投稿文",
        posted_rows=[{"status": "POSTED", "account_id": "night_scout", "platform": "threads",
                      "posted_text": "同じ投稿文", "media_asset_id": "maD"}],
        media_asset_id="maD",
    )
    checks.append(("同text+同media は重複検出", bool(dup)))

    # 5. duplicate guard: 同テキストでも media_asset_id が異なれば重複ではない
    dup2 = mod.duplicate_reason(
        queue_row={"queue_id": "qY", "account_id": "night_scout", "platform": "threads"},
        social=None, text="同じ投稿文",
        posted_rows=[{"status": "POSTED", "account_id": "night_scout", "platform": "threads",
                      "posted_text": "同じ投稿文", "media_asset_id": "maD"}],
        media_asset_id="maOTHER",
    )
    checks.append(("同textでもmedia違いは非重複", dup2 == ""))

    # 6. media無し同士（両方空）は従来通り重複検出（後方互換）
    dup3 = mod.duplicate_reason(
        queue_row={"queue_id": "qZ", "account_id": "night_scout", "platform": "threads"},
        social=None, text="同じ投稿文",
        posted_rows=[{"status": "POSTED", "account_id": "night_scout", "platform": "threads",
                      "posted_text": "同じ投稿文"}],
        media_asset_id="",
    )
    checks.append(("media無し同士は従来通り重複", bool(dup3)))

    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {n}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
