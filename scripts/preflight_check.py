"""
preflight_check.py - Phase 3 移行前 総合診断

チェック項目:
  1.  Python バージョン（3.11+）
  2.  必要パッケージ import
  3.  .env 読み込み確認
  4.  SNS_MASTER_SHEET_ID 設定確認
  5.  GCP 認証情報（SA_JSON_BASE64 / GCP_SA_JSON）設定確認
  6.  GEMINI_API_KEY 設定確認
  7.  Gemini モデル設定表示
  8.  安全ガード変数確認（MOCK_LLM / MOCK_SHEETS / DRY_RUN）
  9.  PUBLISH_ENABLED=false であること
  10. Gemini API 疎通確認（--skip-gemini でスキップ）
  11. Sheets API 疎通確認（--skip-sheets でスキップ）
  12. 12タブ存在確認
  13. accounts シード確認（night_scout / liver_manager）
  14. content_categories 確認
  15. prompt_templates 確認
  16. run_pipeline dry-run 実行可能確認
  17. 既存3プロジェクト確認

総合判定:
  READY_FOR_TEST_WRITE     - Gemini実 + Sheets実 + 全データ確認済み
  READY_FOR_REAL_DRY_RUN   - Gemini実 + Sheets実読み取り可能
  NOT_READY                - 一部WARN/FAIL（詳細確認要）
  BLOCKED_BY_ENV           - 必須環境変数が未設定

使い方:
  python scripts/preflight_check.py
  python scripts/preflight_check.py --quick          # API呼び出しなし
  python scripts/preflight_check.py --skip-gemini    # Gemini疎通スキップ
  python scripts/preflight_check.py --skip-sheets    # Sheets疎通スキップ
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass, field

# --- 先にパス設定と .env 読み込み ---
_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_V2_ROOT, ".env"))
except ImportError:
    pass


# ------------------------------------------------------------------ #
# 結果型
# ------------------------------------------------------------------ #

@dataclass
class CheckResult:
    name: str
    status: str   # PASS / FAIL / WARN / SKIP
    detail: str


def _fmt(r: CheckResult) -> str:
    icons = {"PASS": "✓", "FAIL": "✗", "WARN": "!", "SKIP": "-"}
    icon = icons.get(r.status, "?")
    return f"  [{r.status}] {icon} {r.name}: {r.detail}"


# ------------------------------------------------------------------ #
# 個別チェック関数
# ------------------------------------------------------------------ #

def check_python_version() -> CheckResult:
    vi = sys.version_info
    version_str = f"{vi.major}.{vi.minor}.{vi.micro}"
    if vi >= (3, 11):
        return CheckResult("Python バージョン", "PASS", f"{version_str} (3.11+)")
    elif vi >= (3, 9):
        return CheckResult("Python バージョン", "WARN",
                           f"{version_str} (3.9+ OK だが 3.11+ を推奨。zoneinfo 互換性に注意)")
    else:
        return CheckResult("Python バージョン", "FAIL",
                           f"{version_str} (3.9+ が必要)")


def check_packages() -> CheckResult:
    required = ["gspread", "google.oauth2", "requests"]
    missing = []
    for pkg in required:
        try:
            __import__(pkg.replace(".", "_") if "." in pkg else pkg)
        except ImportError:
            try:
                parts = pkg.split(".")
                mod = __import__(parts[0])
                for part in parts[1:]:
                    mod = getattr(mod, part)
            except (ImportError, AttributeError):
                missing.append(pkg)
    optional_missing = []
    try:
        from dotenv import load_dotenv  # noqa: F401
    except ImportError:
        optional_missing.append("python-dotenv")

    if missing:
        return CheckResult("必要パッケージ", "FAIL",
                           f"未インストール: {missing} → pip install gspread google-auth requests")
    if optional_missing:
        return CheckResult("必要パッケージ", "WARN",
                           f"任意パッケージ未インストール: {optional_missing} (pip install python-dotenv を推奨)")
    return CheckResult("必要パッケージ", "PASS", "gspread, google-auth, requests 確認OK")


def check_env_file() -> CheckResult:
    env_path = os.path.join(_V2_ROOT, ".env")
    template_path = os.path.join(_V2_ROOT, ".env.template")
    if os.path.exists(env_path):
        return CheckResult(".env ファイル", "PASS", f"存在確認 ({env_path})")
    if os.path.exists(template_path):
        return CheckResult(".env ファイル", "WARN",
                           ".env が存在しません。cp .env.template .env を実行してください")
    return CheckResult(".env ファイル", "WARN",
                       ".env も .env.template も見つかりません")


def check_sheet_id() -> CheckResult:
    val = (
        os.environ.get("SNS_MASTER_SHEET_ID", "").strip()
        or os.environ.get("NOTE_MASTER_SHEET_ID", "").strip()
    )
    if val:
        short = val[:8] + "..." if len(val) > 8 else val
        return CheckResult("SNS_MASTER_SHEET_ID", "PASS", f"設定済み ({short})")
    return CheckResult("SNS_MASTER_SHEET_ID", "FAIL", "未設定 → .env に SNS_MASTER_SHEET_ID を設定してください")


def check_gcp_auth() -> CheckResult:
    b64 = os.environ.get("SA_JSON_BASE64", "").strip()
    raw = os.environ.get("GCP_SA_JSON", "").strip()
    if b64:
        return CheckResult("GCP 認証情報", "PASS", "SA_JSON_BASE64 設定済み")
    if raw:
        return CheckResult("GCP 認証情報", "PASS", "GCP_SA_JSON 設定済み")
    return CheckResult("GCP 認証情報", "FAIL",
                       "SA_JSON_BASE64 または GCP_SA_JSON が未設定")


def check_gemini_key() -> CheckResult:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key:
        return CheckResult("GEMINI_API_KEY", "PASS", "設定済み")
    return CheckResult("GEMINI_API_KEY", "FAIL", "未設定 → .env に GEMINI_API_KEY を設定してください")


def check_gemini_model() -> CheckResult:
    model = os.environ.get("GEMINI_MODEL", "").strip()
    candidates = os.environ.get("GEMINI_MODEL_CANDIDATES", "").strip()
    display = model or "gemini-2.5-flash (デフォルト)"
    if candidates:
        display += f" (candidates: {candidates[:40]}...)" if len(candidates) > 40 else f" (candidates: {candidates})"
    return CheckResult("Gemini モデル設定", "PASS", display)


def check_safety_guards() -> CheckResult:
    publish = os.environ.get("PUBLISH_ENABLED", "false").strip().lower()
    dry = os.environ.get("DRY_RUN", "false").strip().lower()
    mock_llm = os.environ.get("MOCK_LLM", "false").strip().lower()
    mock_sheets = os.environ.get("MOCK_SHEETS", "false").strip().lower()

    details = f"PUBLISH_ENABLED={publish} DRY_RUN={dry} MOCK_LLM={mock_llm} MOCK_SHEETS={mock_sheets}"

    if publish in ("1", "true", "yes"):
        return CheckResult("安全ガード (PUBLISH_ENABLED)", "WARN",
                           f"PUBLISH_ENABLED=true になっています。Phase 3 実装前は false を維持してください")
    return CheckResult("安全ガード (PUBLISH_ENABLED)", "PASS",
                       f"PUBLISH_ENABLED=false (SNS投稿無効) | {details}")


def check_gemini_connectivity() -> CheckResult:
    """Gemini 実 API に接続できるか確認する。"""
    os.environ["DRY_RUN"] = "false"
    os.environ["MOCK_LLM"] = "false"

    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        return CheckResult("Gemini 疎通確認", "SKIP", "GEMINI_API_KEY 未設定のためスキップ")

    try:
        from llm_client import call_gemini_json
        result = call_gemini_json(
            'Return ONLY this JSON: {"ok": true}',
            temperature=0.1,
        )
        if result.get("ok") or "_error" not in result:
            return CheckResult("Gemini 疎通確認", "PASS", f"接続OK (モデル応答を受信)")
        return CheckResult("Gemini 疎通確認", "WARN",
                           f"応答は受信したがJSON解析に問題: {str(result)[:80]}")
    except Exception as e:
        return CheckResult("Gemini 疎通確認", "FAIL", f"接続エラー: {str(e)[:120]}")
    finally:
        os.environ.pop("DRY_RUN", None)
        os.environ.pop("MOCK_LLM", None)


def check_sheets_connectivity() -> CheckResult:
    """Google Sheets に接続できるか確認する。"""
    from config_loader import get_config_partial
    cfg = get_config_partial()

    if not cfg.get("sa_dict"):
        return CheckResult("Sheets 疎通確認", "SKIP", "GCP認証情報未設定のためスキップ")
    if not cfg.get("sheet_id"):
        return CheckResult("Sheets 疎通確認", "SKIP", "SNS_MASTER_SHEET_ID未設定のためスキップ")

    try:
        from sheets_client import SheetsClient
        sheets = SheetsClient(
            sheet_id=cfg["sheet_id"],
            sa_dict=cfg["sa_dict"],
            dry_run=True,
        )
        _ = sheets.list_tabs()
        return CheckResult("Sheets 疎通確認", "PASS", "Google Sheets API 接続OK")
    except Exception as e:
        return CheckResult("Sheets 疎通確認", "FAIL", f"接続エラー: {str(e)[:120]}")


def check_tabs_existence() -> CheckResult:
    """12タブがすべて存在するか確認する。"""
    from config_loader import get_config_partial
    from sheets_client import TAB_DEFINITIONS
    cfg = get_config_partial()

    expected_tabs = set(TAB_DEFINITIONS.keys())
    expected_count = len(expected_tabs)

    if not cfg.get("sa_dict") or not cfg.get("sheet_id"):
        return CheckResult(f"タブ存在確認 ({expected_count}タブ)", "SKIP",
                           "認証情報またはシートID未設定のためスキップ")

    try:
        from sheets_client import SheetsClient
        sheets = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=True)
        existing = set(sheets.list_tabs())
        missing = expected_tabs - existing
        extra = existing - expected_tabs

        if missing:
            return CheckResult(f"タブ存在確認", "FAIL",
                               f"不足タブ: {missing} → setup_and_verify.py --setup を実行してください")
        note = f" (追加タブ: {extra})" if extra else ""
        return CheckResult(f"タブ存在確認 ({expected_count}タブ)", "PASS",
                           f"全{expected_count}タブ存在確認OK{note}")
    except Exception as e:
        return CheckResult("タブ存在確認", "FAIL", f"エラー: {str(e)[:100]}")


def check_accounts_seed() -> CheckResult:
    """accounts タブに night_scout / liver_manager が存在するか確認する。"""
    from config_loader import get_config_partial
    cfg = get_config_partial()

    if not cfg.get("sa_dict") or not cfg.get("sheet_id"):
        return CheckResult("accounts シード", "SKIP", "認証情報未設定のためスキップ")

    try:
        from sheets_client import SheetsClient
        sheets = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=True)
        accounts = sheets.get_active_accounts()
        ids = {a.get("account_id") for a in accounts}
        missing = {"night_scout", "liver_manager"} - ids

        if missing:
            return CheckResult("accounts シード", "WARN",
                               f"未登録: {missing} → setup_and_verify.py --setup を実行してください")
        return CheckResult("accounts シード", "PASS",
                           f"night_scout / liver_manager 両方確認OK ({len(accounts)} 件)")
    except Exception as e:
        return CheckResult("accounts シード", "FAIL", f"エラー: {str(e)[:100]}")


def check_categories() -> CheckResult:
    """content_categories にシードが存在するか確認する。"""
    from config_loader import get_config_partial
    cfg = get_config_partial()

    if not cfg.get("sa_dict") or not cfg.get("sheet_id"):
        return CheckResult("content_categories", "SKIP", "認証情報未設定のためスキップ")

    try:
        from sheets_client import SheetsClient
        sheets = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=True)
        cats_ns = sheets.get_active_categories("night_scout")
        cats_lm = sheets.get_active_categories("liver_manager")
        total = len(cats_ns) + len(cats_lm)

        if total == 0:
            return CheckResult("content_categories", "WARN",
                               "カテゴリが空です → setup_and_verify.py --setup を実行してください")
        return CheckResult("content_categories", "PASS",
                           f"night_scout:{len(cats_ns)}件 liver_manager:{len(cats_lm)}件")
    except Exception as e:
        return CheckResult("content_categories", "FAIL", f"エラー: {str(e)[:100]}")


def check_prompt_templates() -> CheckResult:
    """prompt_templates にシードが存在するか確認する。"""
    from config_loader import get_config_partial
    cfg = get_config_partial()

    if not cfg.get("sa_dict") or not cfg.get("sheet_id"):
        return CheckResult("prompt_templates", "SKIP", "認証情報未設定のためスキップ")

    try:
        from sheets_client import SheetsClient
        sheets = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=True)
        templates = sheets.get_prompt_templates()

        if not templates:
            return CheckResult("prompt_templates", "WARN",
                               "テンプレートが空です → setup_and_verify.py --setup を実行してください")
        names = [t.get("template_name", "?") for t in templates[:3]]
        return CheckResult("prompt_templates", "PASS",
                           f"{len(templates)} 件確認OK (例: {names})")
    except Exception as e:
        return CheckResult("prompt_templates", "FAIL", f"エラー: {str(e)[:100]}")


def check_tone_patterns() -> CheckResult:
    """seeds.py に ACCOUNT_NG_TONE_PATTERNS が定義されているか確認する。"""
    try:
        from seeds import ACCOUNT_NG_TONE_PATTERNS
        ns_count = len(ACCOUNT_NG_TONE_PATTERNS.get("night_scout", []))
        lm_count = len(ACCOUNT_NG_TONE_PATTERNS.get("liver_manager", []))
        if ns_count == 0 and lm_count == 0:
            return CheckResult("NGトーンパターン定義", "WARN",
                               "ACCOUNT_NG_TONE_PATTERNS が空です → seeds.py を確認してください")
        return CheckResult("NGトーンパターン定義", "PASS",
                           f"night_scout:{ns_count}件 liver_manager:{lm_count}件")
    except ImportError as e:
        return CheckResult("NGトーンパターン定義", "FAIL", f"インポートエラー: {e}")


def check_tone_checker_module() -> CheckResult:
    """tone_checker.py が import できるか確認する。"""
    try:
        from tone_checker import check_ng_tone  # noqa: F401
        return CheckResult("tone_checker モジュール", "PASS",
                           "tone_checker.check_ng_tone import OK")
    except ImportError as e:
        return CheckResult("tone_checker モジュール", "FAIL", f"import エラー: {e}")


def check_pipeline_dry_run() -> CheckResult:
    """run_pipeline の dry-run が実行可能か確認する（インポートのみ）。"""
    try:
        from draft_generator import generate_drafts  # noqa: F401
        from social_derivative_generator import generate_social_derivatives  # noqa: F401
        from queue_builder import build_queue  # noqa: F401
        return CheckResult("pipeline dry-run 実行可能", "PASS",
                           "必要モジュールのインポートOK")
    except ImportError as e:
        return CheckResult("pipeline dry-run 実行可能", "FAIL", f"インポートエラー: {e}")


def check_existing_projects() -> CheckResult:
    """既存3プロジェクトのディレクトリが存在するか確認する。"""
    project_root = os.path.dirname(_V2_ROOT)
    targets = ["夜職_x", "夜職_threads", "ライバー"]
    missing = [p for p in targets if not os.path.isdir(os.path.join(project_root, p))]

    if missing:
        return CheckResult("既存3プロジェクト", "WARN",
                           f"ディレクトリが見つかりません: {missing}（移動または削除された可能性）")
    return CheckResult("既存3プロジェクト", "PASS",
                       f"夜職_x / 夜職_threads / ライバー 全ディレクトリ存在確認OK")


# ------------------------------------------------------------------ #
# 総合判定
# ------------------------------------------------------------------ #

def compute_verdict(results: list[CheckResult], has_gemini: bool, has_sheets: bool) -> str:
    statuses = {r.status for r in results}
    if "FAIL" in statuses:
        # 必須環境変数系のFAILは BLOCKED_BY_ENV
        env_checks = {"SNS_MASTER_SHEET_ID", "GCP 認証情報", "GEMINI_API_KEY"}
        fail_names = {r.name for r in results if r.status == "FAIL"}
        if fail_names & env_checks:
            return "BLOCKED_BY_ENV"
        return "NOT_READY"

    if "WARN" in statuses:
        return "NOT_READY"

    gemini_ok = any(r.name == "Gemini 疎通確認" and r.status == "PASS" for r in results)
    sheets_ok = any(r.name == "Sheets 疎通確認" and r.status == "PASS" for r in results)
    tabs_ok = any("タブ存在確認" in r.name and r.status == "PASS" for r in results)
    accounts_ok = any(r.name == "accounts シード" and r.status == "PASS" for r in results)

    if gemini_ok and sheets_ok and tabs_ok and accounts_ok:
        return "READY_FOR_TEST_WRITE"
    if gemini_ok and sheets_ok:
        return "READY_FOR_REAL_DRY_RUN"
    if gemini_ok or sheets_ok:
        return "READY_FOR_REAL_DRY_RUN"

    return "NOT_READY"


def print_verdict(verdict: str) -> None:
    print("\n" + "=" * 55)
    print("  総合判定")
    print("=" * 55)
    messages = {
        "READY_FOR_TEST_WRITE": (
            "  ✓ READY_FOR_TEST_WRITE\n"
            "    Gemini実API + Sheets実接続 + データ確認済み。\n"
            "    --test-write での実書き込み確認が可能です。"
        ),
        "READY_FOR_REAL_DRY_RUN": (
            "  ✓ READY_FOR_REAL_DRY_RUN\n"
            "    Gemini実API または Sheets実接続が確認できました。\n"
            "    --dry-run --use-sheets でのパイプライン検証が可能です。"
        ),
        "NOT_READY": (
            "  ! NOT_READY\n"
            "    一部チェックに WARN または FAIL があります。\n"
            "    上記の詳細を確認して修正してください。"
        ),
        "BLOCKED_BY_ENV": (
            "  ✗ BLOCKED_BY_ENV\n"
            "    必須環境変数が設定されていません。\n"
            "    .env を設定してから再実行してください。\n"
            "    → python scripts/print_env_status.py で確認できます"
        ),
    }
    print(messages.get(verdict, f"  ? {verdict}"))
    print("=" * 55)


# ------------------------------------------------------------------ #
# メイン
# ------------------------------------------------------------------ #

def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 3 移行前 総合診断")
    parser.add_argument("--quick", action="store_true",
                        help="API呼び出しなし（環境変数・インポートのみ確認）")
    parser.add_argument("--skip-gemini", action="store_true",
                        help="Gemini API 疎通確認をスキップ")
    parser.add_argument("--skip-sheets", action="store_true",
                        help="Sheets API 疎通確認をスキップ")
    args = parser.parse_args()

    skip_api = args.quick
    skip_gemini = skip_api or args.skip_gemini
    skip_sheets = skip_api or args.skip_sheets

    print("=" * 55)
    print("  preflight_check.py - Phase 3 移行前 総合診断")
    if args.quick:
        print("  モード: --quick (API呼び出しなし)")
    print("=" * 55)

    results: list[CheckResult] = []

    # --- グループ1: ローカル環境チェック ---
    print("\n[グループ1] ローカル環境")
    for fn in [check_python_version, check_packages, check_env_file]:
        r = fn()
        results.append(r)
        print(_fmt(r))

    # --- グループ2: 環境変数チェック ---
    print("\n[グループ2] 環境変数")
    for fn in [check_sheet_id, check_gcp_auth, check_gemini_key,
               check_gemini_model, check_safety_guards]:
        r = fn()
        results.append(r)
        print(_fmt(r))

    # --- グループ3: API疎通確認 ---
    print("\n[グループ3] API疎通確認")
    if skip_gemini:
        r = CheckResult("Gemini 疎通確認", "SKIP", "--skip-gemini / --quick のためスキップ")
    else:
        r = check_gemini_connectivity()
    results.append(r)
    print(_fmt(r))

    if skip_sheets:
        r = CheckResult("Sheets 疎通確認", "SKIP", "--skip-sheets / --quick のためスキップ")
    else:
        r = check_sheets_connectivity()
    results.append(r)
    print(_fmt(r))

    # --- グループ4: データ整合性確認 ---
    print("\n[グループ4] データ整合性（Sheets接続が必要）")
    data_checks = [
        (check_tabs_existence, "タブ存在確認"),
        (check_accounts_seed, "accounts シード"),
        (check_categories, "content_categories"),
        (check_prompt_templates, "prompt_templates"),
    ]
    for fn, display_name in data_checks:
        r = fn() if not skip_sheets else CheckResult(
            display_name, "SKIP", "--skip-sheets / --quick のためスキップ"
        )
        results.append(r)
        print(_fmt(r))

    # --- グループ5: パイプライン確認 ---
    print("\n[グループ5] パイプライン・既存プロジェクト")
    for fn in [check_pipeline_dry_run, check_existing_projects]:
        r = fn()
        results.append(r)
        print(_fmt(r))

    # --- グループ6: トンマナ確認 ---
    print("\n[グループ6] トンマナ・NGトーン確認")
    for fn in [check_tone_patterns, check_tone_checker_module]:
        r = fn()
        results.append(r)
        print(_fmt(r))

    # --- 統計 ---
    from collections import Counter
    count = Counter(r.status for r in results)
    print(f"\n  PASS:{count['PASS']}  FAIL:{count['FAIL']}  WARN:{count['WARN']}  SKIP:{count['SKIP']}")

    has_gemini = any(r.name == "Gemini 疎通確認" and r.status == "PASS" for r in results)
    has_sheets = any(r.name == "Sheets 疎通確認" and r.status == "PASS" for r in results)
    verdict = compute_verdict(results, has_gemini, has_sheets)
    print_verdict(verdict)

    # 次のステップ提案
    print("\n【次のステップ提案】")
    if verdict == "BLOCKED_BY_ENV":
        print("  1. python scripts/print_env_status.py  # 未設定項目を確認")
        print("  2. .env に必須項目を設定")
        print("  3. python scripts/preflight_check.py --quick  # 再チェック")
    elif verdict == "NOT_READY":
        fail_warns = [r for r in results if r.status in ("FAIL", "WARN")]
        for r in fail_warns[:3]:
            print(f"  → [{r.status}] {r.name}: {r.detail[:60]}")
    elif verdict in ("READY_FOR_REAL_DRY_RUN", "READY_FOR_TEST_WRITE"):
        if not has_sheets:
            print("  → python scripts/setup_and_verify.py --setup --verify")
        else:
            print("  → python scripts/run_pipeline.py --account-id night_scout --dry-run --use-sheets")
        if verdict == "READY_FOR_REAL_DRY_RUN":
            print("  → python scripts/setup_and_verify.py --test-write  # 書き込みテスト")
        if verdict == "READY_FOR_TEST_WRITE":
            print("  → Phase 3 チェックリスト: docs/phase3-readiness-checklist.md")

    sys.exit(0 if count["FAIL"] == 0 else 1)


if __name__ == "__main__":
    main()
