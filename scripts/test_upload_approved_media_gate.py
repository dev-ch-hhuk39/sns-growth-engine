#!/usr/bin/env python3
"""Cloudinary upload の承認ゲート（evaluate_upload_gate）を検証する。

approval_status=APPROVED 以外・権利不明・no_reuse・risk=high・ローカル未存在・
フラグ不足のいずれでもブロックされること、env が無ければ実 upload に進まないことを確認する。
実 HTTP は一切行わない。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/upload_approved_media_to_cloudinary.py"


def _load():
    spec = importlib.util.spec_from_file_location("upload_approved_media_to_cloudinary", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    mod = _load()
    gate = mod.evaluate_upload_gate

    # 実在するローカルファイル（このテスト自身）を local_path に使い、ファイル存在条件を満たす
    real_file = str(SCRIPT)

    approved_owned = {
        "media_asset_id": "ma_ok", "approval_status": "APPROVED", "status": "APPROVED",
        "rights_policy": "owned", "reuse_policy": "allow_reuse", "media_policy": "owned",
        "permission_status": "approved", "local_path": real_file,
    }
    self_gen = {
        "media_asset_id": "ma_self", "status": "SELF_GENERATED",
        "rights_policy": "owned", "reuse_policy": "allow_reuse", "media_policy": "owned",
        "local_path": real_file,
    }
    not_approved = {**approved_owned, "media_asset_id": "ma_wait", "approval_status": "WAITING_REVIEW", "status": "WAITING_REVIEW"}
    no_reuse = {**approved_owned, "media_asset_id": "ma_nr", "reuse_policy": "no_reuse"}
    high_risk = {**approved_owned, "media_asset_id": "ma_hr", "media_reuse_risk": "high"}
    review_req = {**approved_owned, "media_asset_id": "ma_rr", "rights_review_required": "true"}
    no_file = {**approved_owned, "media_asset_id": "ma_nf", "local_path": "/no/such/file.png"}

    checks: list[tuple[str, bool]] = []

    # フラグ完備（upload+confirm+env）での許可判定
    g = gate(approved_owned, upload=True, confirm_upload=True, allow_env=True)
    checks.append(("APPROVED+owned+file は allowed", g["allowed"] is True))
    g = gate(self_gen, upload=True, confirm_upload=True, allow_env=True)
    checks.append(("self_generated は allowed", g["allowed"] is True))

    for name, asset in [("未承認", not_approved), ("no_reuse", no_reuse), ("risk=high", high_risk),
                        ("rights_review_required", review_req), ("file無し", no_file)]:
        g = gate(asset, upload=True, confirm_upload=True, allow_env=True)
        checks.append((f"{name} はブロック", g["allowed"] is False))

    # フラグ不足
    g = gate(approved_owned, upload=True, confirm_upload=False, allow_env=True)
    checks.append(("confirm無しはブロック", g["allowed"] is False and any("confirm-upload" in r for r in g["blocked_reasons"])))
    g = gate(approved_owned, upload=True, confirm_upload=True, allow_env=False)
    checks.append(("env無しはブロック", g["allowed"] is False and any("ALLOW_CLOUDINARY_UPLOAD" in r for r in g["blocked_reasons"])))
    g = gate(approved_owned, upload=False, confirm_upload=False, allow_env=True)
    checks.append(("upload未指定は plan only ブロック", g["allowed"] is False and any("plan only" in r for r in g["blocked_reasons"])))

    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {n}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
