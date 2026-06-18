"""
run_real_smoke_plan.py - Phase 5.0: Real Smoke Test Orchestrator

Cloudflare / Cloudinary / X / Threads 投稿の実テストを
順番・条件・安全ガード付きで確認する統合CLI。

デフォルトは完全dry-run。
実API / 実upload / 実postはこのスクリプトでは行わない。
各ステップの「準備状況」だけを確認する。

使い方:
  python scripts/run_real_smoke_plan.py --step all
  python scripts/run_real_smoke_plan.py --step cloudflare
  python scripts/run_real_smoke_plan.py --step cloudinary
  python scripts/run_real_smoke_plan.py --step x
  python scripts/run_real_smoke_plan.py --step threads
  python scripts/run_real_smoke_plan.py --step all --account-id night_scout
  python scripts/run_real_smoke_plan.py --step all --platform threads --account-id liver_manager

出力判定:
  READY              - 認証情報あり、安全ガードOK、実行可能
  READY_FOR_MANUAL_SMOKE - 認証情報あり、実API無効（手動確認後に実行可）
  NOT_READY          - 認証情報なし、または条件不足
  BLOCKED            - 安全ガードで実行禁止

禁止事項:
  - 実API呼び出し
  - 実アップロード
  - 実投稿
  - シークレット値の表示
  - posted_results の変更
  - queue.status の変更
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_V2_ROOT, ".env"))
except ImportError:
    pass

DAILY_TRANSCRIPTION_MINUTES_LIMIT_DEFAULT = 120


# ------------------------------------------------------------------ #
# 結果型
# ------------------------------------------------------------------ #

@dataclass
class StepResult:
    service: str
    verdict: str = "NOT_READY"   # READY / READY_FOR_MANUAL_SMOKE / NOT_READY / BLOCKED
    checks: list[tuple[str, str, str]] = field(default_factory=list)  # (level, label, msg)

    def add(self, level: str, label: str, msg: str) -> None:
        self.checks.append((level, label, msg))

    def print_checks(self) -> None:
        for level, label, msg in self.checks:
            print(f"  [{level}] {label}: {msg}")


# ------------------------------------------------------------------ #
# ユーティリティ
# ------------------------------------------------------------------ #

def _env_bool(key: str, default: str = "false") -> bool:
    return os.environ.get(key, default).strip().lower() in ("true", "1", "yes")


def _env_str(key: str) -> str:
    return os.environ.get(key, "").strip()


def _masked(val: str) -> str:
    if not val:
        return "(未設定)"
    if len(val) <= 6:
        return "****"
    return val[:3] + "****"


# ------------------------------------------------------------------ #
# Cloudflare チェック
# ------------------------------------------------------------------ #

def check_cloudflare(account_id: str | None) -> StepResult:
    r = StepResult(service="Cloudflare")

    # 認証情報
    cf_account_id = _env_str("CLOUDFLARE_ACCOUNT_ID")
    cf_api_token = _env_str("CLOUDFLARE_API_TOKEN")

    cred_ok = True
    if cf_account_id:
        r.add("PASS", "CLOUDFLARE_ACCOUNT_ID", f"設定済み ({_masked(cf_account_id)})")
    else:
        r.add("FAIL", "CLOUDFLARE_ACCOUNT_ID", "未設定")
        cred_ok = False

    if cf_api_token:
        r.add("PASS", "CLOUDFLARE_API_TOKEN", f"設定済み ({_masked(cf_api_token)})")
    else:
        r.add("FAIL", "CLOUDFLARE_API_TOKEN", "未設定")
        cred_ok = False

    # 安全ガードフラグ
    allow_api = _env_bool("ALLOW_TRANSCRIPTION_API", "false")
    if allow_api:
        r.add("WARN", "ALLOW_TRANSCRIPTION_API", "true（実API有効）")
    else:
        r.add("PASS", "ALLOW_TRANSCRIPTION_API", "false（実API無効）")

    # 日次上限
    limit_str = _env_str("DAILY_TRANSCRIPTION_MINUTES_LIMIT")
    try:
        limit = int(limit_str) if limit_str else DAILY_TRANSCRIPTION_MINUTES_LIMIT_DEFAULT
    except ValueError:
        limit = DAILY_TRANSCRIPTION_MINUTES_LIMIT_DEFAULT

    if limit <= DAILY_TRANSCRIPTION_MINUTES_LIMIT_DEFAULT:
        r.add("PASS", "DAILY_TRANSCRIPTION_MINUTES_LIMIT", f"{limit}分/日（上限OK）")
    else:
        r.add("WARN", "DAILY_TRANSCRIPTION_MINUTES_LIMIT", f"{limit}分/日（{DAILY_TRANSCRIPTION_MINUTES_LIMIT_DEFAULT}分以下を推奨）")

    # 30秒音声ファイルの確認
    sample_dir = os.path.join(_V2_ROOT, "tests", "fixtures")
    audio_samples = [
        f for f in os.listdir(sample_dir)
        if f.endswith((".mp3", ".wav", ".m4a", ".ogg", ".flac"))
    ] if os.path.isdir(sample_dir) else []

    if audio_samples:
        r.add("PASS", "smoke用音声ファイル", f"tests/fixtures/ に {len(audio_samples)}件あり")
    else:
        r.add("WARN", "smoke用音声ファイル", "30秒以内の音声ファイルが必要（tests/fixtures/に配置してください）")

    # 判定
    if not cred_ok:
        r.verdict = "NOT_READY"
    elif allow_api:
        r.verdict = "READY"
    else:
        r.verdict = "READY_FOR_MANUAL_SMOKE"

    return r


# ------------------------------------------------------------------ #
# Cloudinary チェック
# ------------------------------------------------------------------ #

def check_cloudinary(account_id: str | None) -> StepResult:
    r = StepResult(service="Cloudinary")

    cloud_name = _env_str("CLOUDINARY_CLOUD_NAME")
    api_key = _env_str("CLOUDINARY_API_KEY")
    api_secret = _env_str("CLOUDINARY_API_SECRET")

    cred_ok = True
    for var, val in [
        ("CLOUDINARY_CLOUD_NAME", cloud_name),
        ("CLOUDINARY_API_KEY", api_key),
        ("CLOUDINARY_API_SECRET", api_secret),
    ]:
        if val:
            r.add("PASS", var, f"設定済み ({_masked(val)})")
        else:
            r.add("FAIL", var, "未設定")
            cred_ok = False

    # 安全ガード
    allow_upload = _env_bool("ALLOW_CLOUDINARY_UPLOAD", "false")
    if allow_upload:
        r.add("WARN", "ALLOW_CLOUDINARY_UPLOAD", "true（実アップロード有効）")
    else:
        r.add("PASS", "ALLOW_CLOUDINARY_UPLOAD", "false（実アップロード無効）")

    # 小さいファイルの確認
    fixtures_dir = os.path.join(_V2_ROOT, "tests", "fixtures")
    small_media = [
        f for f in os.listdir(fixtures_dir)
        if f.endswith((".jpg", ".jpeg", ".png", ".gif", ".mp4", ".webp"))
    ] if os.path.isdir(fixtures_dir) else []

    if small_media:
        r.add("PASS", "smoke用小ファイル", f"tests/fixtures/ に {len(small_media)}件あり")
    else:
        r.add("WARN", "smoke用小ファイル", "小さい画像/動画ファイルが必要（tests/fixtures/に配置してください）")

    # 判定
    if not cred_ok:
        r.verdict = "NOT_READY"
    elif allow_upload:
        r.verdict = "READY"
    else:
        r.verdict = "READY_FOR_MANUAL_SMOKE"

    return r


# ------------------------------------------------------------------ #
# X チェック
# ------------------------------------------------------------------ #

def check_x(account_id: str | None) -> StepResult:
    r = StepResult(service="X")

    # draft_only アカウントのブロック
    if account_id:
        try:
            from accounts.account_config import load_account_config
            cfg = load_account_config(account_id)
            if cfg.is_draft_only():
                r.add("FAIL", "account_status", f"{account_id} は draft_only アカウントです。X実投稿 preflight は実行できません。")
                r.verdict = "BLOCKED"
                return r
        except FileNotFoundError:
            pass

    x_api_key = _env_str("X_API_KEY")
    x_api_secret = _env_str("X_API_SECRET")
    x_access_token = _env_str("X_ACCESS_TOKEN")
    x_access_token_secret = _env_str("X_ACCESS_TOKEN_SECRET")

    cred_ok = True
    for var, val in [
        ("X_API_KEY", x_api_key),
        ("X_API_SECRET", x_api_secret),
        ("X_ACCESS_TOKEN", x_access_token),
        ("X_ACCESS_TOKEN_SECRET", x_access_token_secret),
    ]:
        if val:
            r.add("PASS", var, "設定済み（値は非表示）")
        else:
            r.add("FAIL", var, "未設定")
            cred_ok = False

    # 安全ガード
    publish_enabled = _env_bool("PUBLISH_ENABLED", "false")
    allow_x_post = _env_bool("ALLOW_REAL_X_POST", "false")

    if publish_enabled:
        r.add("WARN", "PUBLISH_ENABLED", "true（本番投稿有効）")
    else:
        r.add("PASS", "PUBLISH_ENABLED", "false（本番投稿無効）")

    if allow_x_post:
        r.add("WARN", "ALLOW_REAL_X_POST", "true（X実投稿有効）")
    else:
        r.add("PASS", "ALLOW_REAL_X_POST", "false（X実投稿無効）")

    # READY queue 候補確認（MockSheetsClient経由）
    ready_candidates: list[dict] = []
    try:
        from sheets_client import MockSheetsClient, SheetsClient
        from config_loader import get_config
        try:
            cfg = get_config()
            sheets = SheetsClient(sheet_id=cfg["sheet_id"], sa_dict=cfg["sa_dict"], dry_run=True)
        except (ValueError, Exception):
            sheets = MockSheetsClient(dry_run=True)

        raw_queue = getattr(sheets, "_queue", [])
        for item in raw_queue:
            if str(item.get("status", "")).upper() == "READY":
                account_match = (account_id is None or item.get("account_id") == account_id)
                if account_match:
                    # 安全チェック
                    text = str(item.get("text", item.get("body", "")))
                    rights = str(item.get("rights_review_required", "false")).lower()
                    risk = str(item.get("media_reuse_risk", "")).lower()
                    char_count = len(text)

                    if rights == "true":
                        continue
                    if risk == "high":
                        continue
                    if char_count > 120:
                        continue
                    ready_candidates.append(item)
    except Exception:
        pass

    if ready_candidates:
        r.add("PASS", "安全なREADY候補", f"{len(ready_candidates)}件")
    else:
        r.add("WARN", "安全なREADY候補", "条件を満たすREADY queue候補なし")

    # posted_results 変更禁止確認
    r.add("INFO", "posted_results", "このスクリプトは変更しません（実行禁止）")

    # 判定
    if not cred_ok:
        r.verdict = "NOT_READY"
    elif publish_enabled or allow_x_post:
        r.verdict = "READY"
    elif not ready_candidates:
        r.verdict = "BLOCKED"
    else:
        r.verdict = "READY_FOR_MANUAL_SMOKE"

    return r


# ------------------------------------------------------------------ #
# Threads チェック
# ------------------------------------------------------------------ #

def check_threads(account_id: str | None) -> StepResult:
    r = StepResult(service="Threads")

    if account_id:
        try:
            from accounts.account_config import load_account_config
            cfg = load_account_config(account_id)
            if cfg.is_draft_only():
                r.add("FAIL", "account_status", f"{account_id} は draft_only アカウントです。Threads実投稿 preflight は実行できません。")
                r.verdict = "BLOCKED"
                return r
            if not cfg.allows_platform("threads"):
                r.add("FAIL", "threads_platform", f"{account_id} は threads プラットフォームを未設定です")
                r.verdict = "BLOCKED"
                return r
        except FileNotFoundError:
            r.add("WARN", "account_config", f"{account_id} の設定ファイルが見つかりません")

    required_creds = [
        "THREADS_ACCESS_TOKEN",
        "THREADS_USER_ID",
    ]
    optional_creds = [
        "THREADS_APP_ID",
        "THREADS_APP_SECRET",
    ]

    cred_ok = True
    for var in required_creds:
        if _env_str(var):
            r.add("PASS", var, "設定済み（値は非表示）")
        else:
            r.add("FAIL", var, "未設定")
            cred_ok = False

    for var in optional_creds:
        if _env_str(var):
            r.add("PASS", var, "設定済み（値は非表示）")
        else:
            r.add("WARN", var, "未設定（実投稿前に確認推奨）")

    publish_enabled = _env_bool("PUBLISH_ENABLED", "false")
    allow_threads_post = _env_bool("ALLOW_REAL_THREADS_POST", "false")

    if publish_enabled:
        r.add("WARN", "PUBLISH_ENABLED", "true（本番投稿有効）")
    else:
        r.add("PASS", "PUBLISH_ENABLED", "false（本番投稿無効）")

    if allow_threads_post:
        r.add("WARN", "ALLOW_REAL_THREADS_POST", "true（Threads実投稿有効）")
    else:
        r.add("PASS", "ALLOW_REAL_THREADS_POST", "false（Threads実投稿無効）")

    ready_candidates: list[dict] = []
    try:
        from sheets_client import MockSheetsClient, SheetsClient
        from config_loader import get_config
        try:
            cfg = get_config()
            sheets = SheetsClient(sheet_id=cfg["sheet_id"], sa_dict=cfg["sa_dict"], dry_run=True)
        except (ValueError, Exception):
            sheets = MockSheetsClient(dry_run=True)

        raw_queue = getattr(sheets, "_queue", [])
        for item in raw_queue:
            if str(item.get("platform", "")).lower() != "threads":
                continue
            if str(item.get("status", "")).upper() != "READY":
                continue
            if account_id is not None and item.get("account_id") != account_id:
                continue

            text = str(item.get("text", item.get("body", "")))
            rights = str(item.get("rights_review_required", "false")).lower()
            risk = str(item.get("media_reuse_risk", "")).lower()

            if rights == "true":
                continue
            if risk == "high":
                continue
            if len(text) > 500:
                continue
            ready_candidates.append(item)
    except Exception:
        pass

    if ready_candidates:
        r.add("PASS", "安全なThreads READY候補", f"{len(ready_candidates)}件")
    else:
        r.add("WARN", "安全なThreads READY候補", "条件を満たすREADY queue候補なし")

    r.add("INFO", "posted_results", "このスクリプトは変更しません（実行禁止）")

    if not cred_ok:
        r.verdict = "NOT_READY"
    elif publish_enabled or allow_threads_post:
        r.verdict = "READY"
    elif not ready_candidates:
        r.verdict = "BLOCKED"
    else:
        r.verdict = "READY_FOR_MANUAL_SMOKE"

    return r


# ------------------------------------------------------------------ #
# 結果出力
# ------------------------------------------------------------------ #

VERDICT_ICONS = {
    "READY": "[READY]",
    "READY_FOR_MANUAL_SMOKE": "[READY_FOR_MANUAL_SMOKE]",
    "NOT_READY": "[NOT_READY]",
    "BLOCKED": "[BLOCKED]",
}

VERDICT_MESSAGES = {
    "READY": "認証情報あり、実API/実行フラグ有効。--confirm-xxx で実行可能（慎重に）。",
    "READY_FOR_MANUAL_SMOKE": "認証情報あり、実APIは無効。ALLOW_xxx=true の設定後、実スモーク可能。",
    "NOT_READY": "認証情報が不足しています。.envを確認してください。",
    "BLOCKED": "安全ガードまたはキュー条件により実行できません。",
}


def print_summary(results: list[StepResult]) -> None:
    print("\n" + "=" * 65)
    print("  Real Smoke Plan サマリー")
    print("=" * 65)
    for r in results:
        icon = VERDICT_ICONS.get(r.verdict, r.verdict)
        msg = VERDICT_MESSAGES.get(r.verdict, "")
        print(f"\n  {icon} [{r.service}]")
        print(f"    {msg}")

    print("\n[INFO] 実API / 実upload / 実投稿はこのスクリプトでは行いません。")
    print("[INFO] 実行手順は docs/manual-smoke-test-sequence.md を参照してください。")
    print("=" * 65)


def build_json_output(results: list[StepResult]) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": True,
        "note": "実API/実upload/実投稿は行いません",
        "steps": [
            {
                "service": r.service,
                "verdict": r.verdict,
                "checks": [
                    {"level": level, "label": label, "msg": msg}
                    for level, label, msg in r.checks
                ],
            }
            for r in results
        ],
    }


# ------------------------------------------------------------------ #
# メイン
# ------------------------------------------------------------------ #

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 5.0: Real Smoke Test Orchestrator（dry-run専用）"
    )
    parser.add_argument(
        "--step",
        choices=["cloudflare", "cloudinary", "x", "threads", "all"],
        default="all",
        help="確認するステップ（デフォルト: all）",
    )
    parser.add_argument("--account-id", help="対象アカウントID")
    parser.add_argument("--platform", default="", help="互換引数（dry-run表示用。実投稿には使わない）")
    parser.add_argument("--dry-run", action="store_true", default=True, help="互換引数。常にdry-run専用")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")
    args = parser.parse_args()

    print("=" * 65)
    print("  run_real_smoke_plan.py - Phase 5.0: Real Smoke Test Orchestrator")
    print("  ※ デフォルト完全dry-run。実API/実upload/実投稿はしません。")
    print("=" * 65)

    publisher_step = "threads" if args.platform.strip().lower() == "threads" else "x"
    steps_to_run = (
        ["cloudflare", "cloudinary", publisher_step]
        if args.step == "all"
        else [args.step]
    )

    results: list[StepResult] = []
    step_map = {
        "cloudflare": check_cloudflare,
        "cloudinary": check_cloudinary,
        "x": check_x,
        "threads": check_threads,
    }

    for step_name in steps_to_run:
        fn = step_map[step_name]
        print(f"\n{'─' * 40}")
        print(f"  [{step_name.upper()}] チェック開始")
        print("─" * 40)
        result = fn(args.account_id)
        result.print_checks()
        results.append(result)
        icon = VERDICT_ICONS.get(result.verdict, result.verdict)
        print(f"\n  => {icon}: {VERDICT_MESSAGES.get(result.verdict, '')}")

    if args.json:
        print("\n--- JSON OUTPUT ---")
        print(json.dumps(build_json_output(results), ensure_ascii=False, indent=2))

    print_summary(results)

    # NOT_READY / BLOCKED があれば終了コード1
    bad_verdicts = {"NOT_READY", "BLOCKED"}
    if any(r.verdict in bad_verdicts for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
