"""認証情報 readiness チェック。

値は表示せず SET / MISSING のみ報告する。
exit code 0 = READY、exit code 1 = MISSING あり。

Usage:
    python3 scripts/check_credentials_readiness.py
    python3 scripts/check_credentials_readiness.py --account-id night_scout
    python3 scripts/check_credentials_readiness.py --dry-run   # 同じ動作（非破壊的）
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

CHECK_MARK = "✓"
CROSS_MARK = "✗"


def _is_set(name: str) -> bool:
    return bool(os.environ.get(name, "").strip())


def _status(name: str, required: bool = True) -> tuple[str, bool]:
    ok = _is_set(name)
    mark = CHECK_MARK if ok else CROSS_MARK
    label = "SET    " if ok else ("MISSING" if required else "MISSING(opt)")
    return f"  {mark} {label}  {name}", ok


def check_section(title: str, checks: list[tuple[str, bool]]) -> tuple[list[str], int, int]:
    lines = [f"\n[{title}]"]
    ok_count = miss_count = 0
    for name, required in checks:
        line, ok = _status(name, required)
        lines.append(line)
        if ok:
            ok_count += 1
        elif required:
            miss_count += 1
    return lines, ok_count, miss_count


def main() -> None:
    parser = argparse.ArgumentParser(description="認証情報 readiness チェック（値は表示しない）")
    parser.add_argument("--account-id", help="特定アカウントのみ確認")
    parser.add_argument("--dry-run", action="store_true", help="非破壊モード（動作は同じ）")
    args = parser.parse_args()

    all_lines: list[str] = []
    total_ok = total_miss = 0

    # ---- X night_scout ----
    if not args.account_id or args.account_id == "night_scout":
        lines, ok, miss = check_section("X (night_scout)", [
            ("X_API_KEY", True),
            ("X_API_SECRET", True),
            ("X_ACCESS_TOKEN", True),
            ("X_ACCESS_TOKEN_SECRET", True),
        ])
        all_lines.extend(lines)
        total_ok += ok; total_miss += miss

    # ---- Threads night_scout ----
    if not args.account_id or args.account_id == "night_scout":
        # アカウント別変数またはフォールバックのどちらかが設定されていればOK
        threads_ns_token = _is_set("THREADS_ACCESS_TOKEN_NIGHT_SCOUT") or _is_set("THREADS_ACCESS_TOKEN")
        threads_ns_uid = _is_set("THREADS_USER_ID_NIGHT_SCOUT") or _is_set("THREADS_USER_ID")
        lines = ["\n[Threads (night_scout)]"]
        for label, ok_val in [
            ("THREADS_ACCESS_TOKEN_NIGHT_SCOUT (or THREADS_ACCESS_TOKEN)", threads_ns_token),
            ("THREADS_USER_ID_NIGHT_SCOUT (or THREADS_USER_ID)", threads_ns_uid),
            ("THREADS_APP_ID", False),
            ("THREADS_APP_SECRET", False),
        ]:
            if "(or" in label:
                mark = CHECK_MARK if ok_val else CROSS_MARK
                status = "SET    " if ok_val else "MISSING"
                lines.append(f"  {mark} {status}  {label}")
                if ok_val:
                    total_ok += 1
                else:
                    total_miss += 1
            else:
                line, ok = _status(label.split("(")[0].strip(), required=False)
                lines.append(line)
                if ok:
                    total_ok += 1
        all_lines.extend(lines)

    # ---- Threads liver_manager ----
    if not args.account_id or args.account_id == "liver_manager":
        threads_lm_token = _is_set("THREADS_ACCESS_TOKEN_LIVER_MANAGER")
        threads_lm_uid = _is_set("THREADS_USER_ID_LIVER_MANAGER")
        lines = ["\n[Threads (liver_manager)]"]
        for label, ok_val in [
            ("THREADS_ACCESS_TOKEN_LIVER_MANAGER", threads_lm_token),
            ("THREADS_USER_ID_LIVER_MANAGER", threads_lm_uid),
        ]:
            mark = CHECK_MARK if ok_val else CROSS_MARK
            status = "SET    " if ok_val else "MISSING"
            lines.append(f"  {mark} {status}  {label}")
            if ok_val:
                total_ok += 1
            else:
                total_miss += 1
        all_lines.extend(lines)

    # ---- Google Sheets ----
    lines, ok, miss = check_section("Google Sheets", [
        ("SNS_MASTER_SHEET_ID", True),
        ("SA_JSON_BASE64", False),
        ("GCP_SA_JSON", False),
    ])
    # SA_JSON_BASE64 か GCP_SA_JSON のどちらかがあればよい
    sa_ok = _is_set("SA_JSON_BASE64") or _is_set("GCP_SA_JSON")
    lines_final = lines[:2]  # [Google Sheets] ヘッダー + SNS_MASTER_SHEET_ID
    mark = CHECK_MARK if sa_ok else CROSS_MARK
    status = "SET    " if sa_ok else "MISSING"
    lines_final.append(f"  {mark} {status}  SA_JSON_BASE64 (or GCP_SA_JSON)")
    # SNS_MASTER_SHEET_ID
    sm_ok = _is_set("SNS_MASTER_SHEET_ID")
    all_lines.extend(lines_final)
    total_ok += (1 if sm_ok else 0) + (1 if sa_ok else 0)
    total_miss += (0 if sm_ok else 1) + (0 if sa_ok else 1)

    # ---- Gemini ----
    lines, ok, miss = check_section("Gemini", [
        ("GEMINI_API_KEY", True),
        ("GEMINI_MODEL", False),
    ])
    all_lines.extend(lines)
    total_ok += ok; total_miss += miss

    # ---- Cloudinary ----
    lines, ok, miss = check_section("Cloudinary (無効化中 — ALLOW_CLOUDINARY_UPLOAD=false で保護)", [
        ("CLOUDINARY_CLOUD_NAME", False),
        ("CLOUDINARY_API_KEY", False),
        ("CLOUDINARY_API_SECRET", False),
    ])
    all_lines.extend(lines)
    total_ok += ok
    # Cloudinary は optional なので miss にカウントしない

    # ---- Cloudflare transcription ----
    lines, ok, miss = check_section("Cloudflare Workers AI / transcription (無効化中)", [
        ("CLOUDFLARE_ACCOUNT_ID", False),
        ("CLOUDFLARE_API_TOKEN", False),
    ])
    all_lines.extend(lines)
    total_ok += ok
    # transcription も optional

    # ---- Safety flags ----
    lines = ["\n[Safety flags (全て未設定 or false が正常)]"]
    safety_flags = [
        "PUBLISH_ENABLED",
        "ALLOW_REAL_X_POST",
        "ALLOW_REAL_THREADS_POST",
        "ALLOW_CLOUDINARY_UPLOAD",
        "ALLOW_TRANSCRIPTION_API",
    ]
    for flag in safety_flags:
        val = os.environ.get(flag, "").strip().lower()
        if val in ("true", "1", "yes"):
            lines.append(f"  ! WARN   {flag}={val}  (本番投稿モード — .envのみに設定し永続commitしないこと)")
        else:
            lines.append(f"  {CHECK_MARK} OK     {flag}=false/unset")
    all_lines.extend(lines)

    # ---- 出力 ----
    print("=" * 60)
    print("SNS Growth Engine — 認証情報 Readiness チェック")
    print("=" * 60)
    for line in all_lines:
        print(line)
    print()
    print("=" * 60)

    required_ok = total_ok
    required_miss = total_miss
    if required_miss == 0:
        status_str = "READY"
        print(f"ステータス: {status_str}  (必須 {required_ok} 件すべて設定済み)")
    else:
        status_str = "MISSING"
        print(f"ステータス: {status_str}  (必須 {required_miss} 件が未設定)")
    print("=" * 60)
    print()
    print("注意: このスクリプトは認証情報の値を表示しません。")
    if required_miss > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
