#!/usr/bin/env python3
"""queue 行からの media フィールド読み取り（resolve_queue_media）を検証する。

queue タブに存在する列は media_asset_id のみで、media_url / media_status /
media_required は列が無いことがある。.get() で安全に読めること、
ATTACHED / UPLOADED かつ media_url があるときだけ「使える media」と
判定されることを確認する。
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


def main() -> int:
    mod = _load()
    rqm = mod.resolve_queue_media
    checks: list[tuple[str, bool]] = []

    # 1. media 列が一切無い行（既存の text-only 行）→ 何も使わない
    m = rqm({"queue_id": "q1", "account_id": "night_scout"})
    checks.append(("media列なしは media_usable=False", m["media_usable"] is False))
    checks.append(("media列なしは block_reason 空", m["block_reason"] == ""))
    checks.append(("media列なしは effective_media_url 空", m["effective_media_url"] == ""))

    # 2. ATTACHED + url → 使える
    m = rqm({"media_asset_id": "ma1", "media_url": "https://x/img.png", "media_status": "ATTACHED"})
    checks.append(("ATTACHED+url は usable", m["media_usable"] is True))
    checks.append(("usable は effective_media_url を返す", m["effective_media_url"].endswith("img.png")))

    # 3. UPLOADED + url → 使える
    m = rqm({"media_asset_id": "ma2", "media_url": "https://x/u.png", "media_status": "uploaded"})
    checks.append(("UPLOADED(小文字)+url は usable", m["media_usable"] is True))
    checks.append(("media_status は大文字化される", m["media_status"] == "UPLOADED"))

    # 4. status が許可外 → 使えない
    m = rqm({"media_asset_id": "ma3", "media_url": "https://x/p.png", "media_status": "PENDING"})
    checks.append(("PENDING は usable=False", m["media_usable"] is False))
    checks.append(("PENDING は effective_media_url 空", m["effective_media_url"] == ""))

    # 5. status は ATTACHED だが url 無し → 使えない
    m = rqm({"media_asset_id": "ma4", "media_url": "", "media_status": "ATTACHED"})
    checks.append(("url無しは usable=False", m["media_usable"] is False))

    # 6. media_asset_id は常に読み取れる
    m = rqm({"media_asset_id": " ma5 ", "media_status": "ATTACHED", "media_url": "https://x/y.png"})
    checks.append(("media_asset_id は trim される", m["media_asset_id"] == "ma5"))

    # 7. media_required の真偽解釈
    m = rqm({"media_required": "true", "media_url": "https://x/z.png", "media_status": "ATTACHED"})
    checks.append(("media_required=true 解釈", m["media_required"] is True))
    m = rqm({"media_required": "false"})
    checks.append(("media_required=false 解釈", m["media_required"] is False))

    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {n}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
