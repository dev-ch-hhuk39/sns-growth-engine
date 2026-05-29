"""
print_env_status.py - .env 設定状況の安全確認

APIキーや認証情報の値は絶対に表示しない。
set / missing のみ表示する。

使い方:
  python scripts/print_env_status.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except ImportError:
    pass


def _s(val: str) -> str:
    return "set" if val.strip() else "missing"


def _bool_display(key: str, default: str = "false") -> str:
    val = os.environ.get(key, "").strip()
    return val if val else f"{default} (デフォルト)"


def main() -> None:
    print("=" * 55)
    print("  環境変数 設定状況チェック")
    print("=" * 55)

    sheet_id = (
        os.environ.get("SNS_MASTER_SHEET_ID", "").strip()
        or os.environ.get("NOTE_MASTER_SHEET_ID", "").strip()
    )
    sa_b64 = os.environ.get("SA_JSON_BASE64", "").strip()
    gcp_json = os.environ.get("GCP_SA_JSON", "").strip()
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    gcp_auth_ok = bool(sa_b64 or gcp_json)

    print("\n【必須設定】")
    print(f"  SNS_MASTER_SHEET_ID  : {_s(sheet_id)}")
    print(f"  SA_JSON_BASE64       : {_s(sa_b64)}")
    print(f"  GCP_SA_JSON          : {_s(gcp_json)}")
    print(f"  GCP認証 (いずれか)   : {'set' if gcp_auth_ok else 'missing'}")
    print(f"  GEMINI_API_KEY       : {_s(gemini_key)}")

    model_val = os.environ.get("GEMINI_MODEL", "").strip()
    candidates_val = os.environ.get("GEMINI_MODEL_CANDIDATES", "").strip()
    print("\n【Gemini設定】")
    print(f"  GEMINI_MODEL         : {model_val if model_val else 'gemini-2.5-flash (デフォルト)'}")
    short_cand = candidates_val[:52] + "..." if len(candidates_val) > 55 else (candidates_val or "(未設定)")
    print(f"  GEMINI_MODEL_CANDIDATES: {short_cand}")

    print("\n【安全ガード環境変数】")
    print(f"  DRY_RUN              : {_bool_display('DRY_RUN', 'false')}")
    print(f"  MOCK_LLM             : {_bool_display('MOCK_LLM', 'false')}")
    print(f"  MOCK_SHEETS          : {_bool_display('MOCK_SHEETS', 'false')}")
    print(f"  PUBLISH_ENABLED      : {_bool_display('PUBLISH_ENABLED', 'false')}")
    allow = os.environ.get("ALLOW_SHEETS_WRITE", "").strip()
    print(f"  ALLOW_SHEETS_WRITE   : {allow if allow else '(廃止済み → dry_run=False で制御)'}")

    print("\n【任意設定】")
    discord = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    print(f"  DISCORD_WEBHOOK_URL  : {_s(discord)}")

    print("\n【診断サマリー】")
    missing_required = []
    if not sheet_id:
        missing_required.append("SNS_MASTER_SHEET_ID")
    if not gcp_auth_ok:
        missing_required.append("SA_JSON_BASE64 または GCP_SA_JSON")
    if not gemini_key:
        missing_required.append("GEMINI_API_KEY")

    if missing_required:
        print(f"  ❌ 未設定の必須項目: {', '.join(missing_required)}")
        print("     → v2/.env を確認してください (cp .env.template .env)")
    else:
        print("  ✓ すべての必須項目が設定されています")

    pub = os.environ.get("PUBLISH_ENABLED", "false").strip().lower()
    if pub in ("1", "true", "yes"):
        print("  ⚠ PUBLISH_ENABLED=true です（Phase 3 実装完了前に有効化しないでください）")
    else:
        print("  ✓ PUBLISH_ENABLED=false: SNS投稿処理は無効（安全）")

    print("=" * 55)

    # 次のステップ案内
    if missing_required:
        print("\n次のステップ:")
        for item in missing_required:
            print(f"  → .env に {item} を設定してください")
    else:
        print("\n次のステップ:")
        if gemini_key:
            print("  → python scripts/test_gemini_real.py")
        if gcp_auth_ok and sheet_id:
            print("  → python scripts/test_sheets_connection.py --dry-run")
        print("  → python scripts/preflight_check.py --quick")


if __name__ == "__main__":
    main()
