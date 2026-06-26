#!/usr/bin/env python3
"""Validate rights-clear media attachment planning (no Sheets writes)."""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "src"))

from media.queue_media_attach import (
    is_media_rights_clear,
    plan_queue_media_attachment,
    resolve_media_url,
    select_attachable_media,
)

SELF_GEN = {
    "media_asset_id": "ma_self", "status": "SELF_GENERATED",
    "rights_policy": "owned", "reuse_policy": "allow_reuse", "media_policy": "owned",
}
SELF_GEN_UPLOADED = {**SELF_GEN, "media_asset_id": "ma_self2",
                     "cloudinary_url": "https://res.cloudinary.com/x/img.png"}
UNKNOWN_RIGHTS = {
    "media_asset_id": "ma_unknown", "status": "WAITING_REVIEW",
    "rights_policy": "unknown", "reuse_policy": "reference_only", "media_policy": "plan_only",
}
NO_REUSE = {
    "media_asset_id": "ma_noreuse", "status": "APPROVED",
    "rights_policy": "allowed", "reuse_policy": "no_reuse", "media_policy": "owned",
}
HIGH_RISK = {
    "media_asset_id": "ma_high", "status": "APPROVED",
    "rights_policy": "allowed", "reuse_policy": "allow_reuse", "media_policy": "owned",
    "media_reuse_risk": "high",
}


def main() -> int:
    checks: list[tuple[str, bool]] = []

    checks.append(("self_generated is clear", is_media_rights_clear(SELF_GEN)))
    checks.append(("uploaded self_gen clear", is_media_rights_clear(SELF_GEN_UPLOADED)))
    checks.append(("unknown rights blocked", not is_media_rights_clear(UNKNOWN_RIGHTS)))
    checks.append(("no_reuse blocked", not is_media_rights_clear(NO_REUSE)))
    checks.append(("high risk blocked", not is_media_rights_clear(HIGH_RISK)))

    sel = select_attachable_media([SELF_GEN, SELF_GEN_UPLOADED, UNKNOWN_RIGHTS, NO_REUSE, HIGH_RISK])
    checks.append(("select keeps only 2 clear", {a["media_asset_id"] for a in sel} == {"ma_self", "ma_self2"}))

    checks.append(("url pending for un-uploaded", resolve_media_url(SELF_GEN) == ""))
    checks.append(("url resolved for uploaded", resolve_media_url(SELF_GEN_UPLOADED).endswith("img.png")))

    queue_rows = [
        {"queue_id": "q1", "account_id": "night_scout", "media_asset_id": "ma_self"},
        {"queue_id": "q2", "account_id": "night_scout", "media_asset_id": "ma_self2"},
        {"queue_id": "q3", "account_id": "night_scout", "media_asset_id": "ma_unknown"},
        {"queue_id": "q4", "account_id": "night_scout", "media_asset_id": ""},
        {"queue_id": "q5", "account_id": "night_scout", "media_asset_id": "ma_missing"},
    ]
    assets_by_id = {a["media_asset_id"]: a for a in [SELF_GEN, SELF_GEN_UPLOADED, UNKNOWN_RIGHTS]}
    plans = {p["queue_id"]: p for p in plan_queue_media_attachment(queue_rows, assets_by_id)}

    checks.append(("q1 attachable pending", plans["q1"]["attachable"] and plans["q1"]["media_url_pending"]))
    checks.append(("q2 attachable with url", plans["q2"]["attachable"] and not plans["q2"]["media_url_pending"]))
    checks.append(("q3 not attachable (unknown)", not plans["q3"]["attachable"]))
    checks.append(("q4 text-only (no media_asset_id)", not plans["q4"]["attachable"]))
    checks.append(("q5 missing asset not attachable", not plans["q5"]["attachable"]))
    checks.append(("q2 url ends img.png", plans["q2"]["media_url"].endswith("img.png")))

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
