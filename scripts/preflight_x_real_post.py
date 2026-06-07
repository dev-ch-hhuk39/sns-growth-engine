"""
preflight_x_real_post.py - X本番投稿前最終preflight（Phase 3-E）

X API 実投稿を実行する前に必要な全条件を確認する。
このスクリプト自体は実投稿を行わない。

チェック内容:
  1. X API 認証情報 4項目の set/missing 確認（値は表示しない）
  2. PUBLISH_ENABLED=false 確認
  3. ALLOW_REAL_X_POST=false 確認
  4. READY queue 候補の確認
  5. rights_review_required=true の投稿は投稿不可
  6. media_reuse_risk=high の投稿は投稿不可
  7. X 120文字以内確認
  8. media_asset がある場合の準備確認
  9. tweepy 利用可能確認

使い方:
  python scripts/preflight_x_real_post.py --mock
  python scripts/preflight_x_real_post.py --account-id night_scout

禁止事項:
  - 実投稿
  - シークレット値の表示
  - PUBLISH_ENABLED=true の設定
  - ALLOW_REAL_X_POST=true の設定
"""
from __future__ import annotations

import argparse
import os
import sys

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_V2_ROOT, ".env"))
except ImportError:
    pass

from config_loader import get_config, get_x_credentials
from sheets_client import MockSheetsClient, SheetsClient
from text_policy import check_text_policy

X_CHAR_LIMIT = 120  # 推奨上限（ハード上限は140）

RESULTS: list[tuple[str, str, str]] = []


def _add(level: str, label: str, msg: str) -> None:
    RESULTS.append((level, label, msg))
    icon = {"PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]", "INFO": "[INFO]"}[level]
    print(f"  {icon} {label}: {msg}")


# ------------------------------------------------------------------ #
# チェック関数
# ------------------------------------------------------------------ #

def check_x_credentials() -> bool:
    """X API 認証情報の set/missing 確認（値は表示しない）。"""
    print("\n[1] X API 認証情報（値は表示しません）")
    creds = get_x_credentials()
    required = [
        ("X_API_KEY", creds.get("api_key_set", False)),
        ("X_API_SECRET", bool(os.environ.get("X_API_SECRET", "").strip())),
        ("X_ACCESS_TOKEN", creds.get("access_token_set", False)),
        ("X_ACCESS_TOKEN_SECRET", creds.get("access_token_secret_set", False)),
    ]
    all_set = True
    for name, is_set in required:
        if is_set:
            _add("PASS", name, "set（値は非表示）")
        else:
            _add("FAIL", name, "未設定（.env に追加してください）")
            all_set = False
    return all_set


def check_safety_flags() -> bool:
    """PUBLISH_ENABLED / ALLOW_REAL_X_POST の確認。"""
    print("\n[2] 安全ガードフラグ確認")
    publish_enabled = os.environ.get("PUBLISH_ENABLED", "false").lower()
    allow_x_post = os.environ.get("ALLOW_REAL_X_POST", "false").lower()

    if publish_enabled == "true":
        _add("WARN", "PUBLISH_ENABLED", "true（本番投稿が有効です）")
    else:
        _add("PASS", "PUBLISH_ENABLED", f"false（本番投稿無効）")

    if allow_x_post == "true":
        _add("WARN", "ALLOW_REAL_X_POST", "true（X実投稿が有効です）")
    else:
        _add("PASS", "ALLOW_REAL_X_POST", f"false（X実投稿無効）")

    return True


def check_tweepy() -> bool:
    """tweepy の利用可能確認。"""
    print("\n[3] tweepy 確認")
    try:
        import tweepy  # type: ignore[import]
        _add("PASS", "tweepy", f"インストール済み (version: {tweepy.__version__})")
        return True
    except ImportError:
        _add("FAIL", "tweepy", "未インストール（pip install tweepy でインストール）")
        return False


def check_ready_queue(sheets, account_id: str | None) -> list[dict]:
    """READY queue 候補を確認してリストを返す。"""
    print("\n[4] READY queue 候補確認")

    if hasattr(sheets, "_sh"):
        try:
            ws = sheets._sh.worksheet("queue")
            rows = ws.get_all_records()
            if account_id:
                rows = [r for r in rows if r.get("account_id") == account_id]
        except Exception:
            rows = []
    else:
        rows = getattr(sheets, "_queue", [])
        if account_id:
            rows = [r for r in rows if r.get("account_id") == account_id]
        rows = [dict(r) for r in rows]

    ready = [r for r in rows if str(r.get("status", "")).upper() == "READY"]
    _add("INFO", "READY queue", f"{len(ready)}件")

    if not ready:
        _add("WARN", "READY queue", "投稿候補がありません")

    return ready


def check_post_safety(queue_items: list[dict]) -> tuple[int, int, int]:
    """各投稿候補の安全確認。(blocked_rights, blocked_risk, char_over) を返す。"""
    print("\n[5] 投稿候補の安全確認")

    blocked_rights = 0
    blocked_risk = 0
    char_over = 0

    for item in queue_items:
        item_id = item.get("queue_id", item.get("draft_id", "?"))
        text = str(item.get("text", item.get("body", "")))
        platform = str(item.get("platform", "x")).lower()

        # rights_review_required チェック
        rights = str(item.get("rights_review_required", "false")).lower()
        if rights == "true":
            _add("FAIL", f"rights_review [{item_id}]", "rights_review_required=true → 投稿不可")
            blocked_rights += 1

        # media_reuse_risk チェック
        risk = str(item.get("media_reuse_risk", "")).lower()
        if risk == "high":
            _add("FAIL", f"media_reuse_risk [{item_id}]", "high → 投稿不可")
            blocked_risk += 1

        # 文字数チェック
        if platform in ("x", "twitter") and text:
            policy = check_text_policy(text, "x")
            if policy.status == "FAIL":
                _add("FAIL", f"文字数 [{item_id}]", f"{policy.char_count}文字 > 上限140文字")
                char_over += 1
            elif policy.status == "WARN":
                _add("WARN", f"文字数 [{item_id}]", f"{policy.char_count}文字 > 推奨{X_CHAR_LIMIT}文字")

        # media_asset 確認
        media_id = item.get("media_asset_id", "")
        if media_id:
            _add("INFO", f"media_asset [{item_id}]", f"media_asset_id={media_id} (アップロード確認が必要)")

    if blocked_rights == 0 and blocked_risk == 0:
        _add("PASS", "rights/risk チェック", "全件クリア")
    if char_over == 0:
        _add("PASS", "文字数チェック", "全件クリア（推奨120文字以内）")

    return blocked_rights, blocked_risk, char_over


def check_media_assets(sheets, account_id: str | None) -> None:
    """media_assets の Cloudinary アップロード状態確認。"""
    print("\n[6] media_assets 確認")

    if hasattr(sheets, "_sh"):
        try:
            ws = sheets._sh.worksheet("media_assets")
            rows = ws.get_all_records()
            if account_id:
                rows = [r for r in rows if r.get("account_id") == account_id]
        except Exception:
            rows = []
    else:
        rows = getattr(sheets, "_media_assets", [])
        if account_id:
            rows = [r for r in rows if r.get("account_id") == account_id]
        rows = [dict(r) for r in rows]

    uploaded = [r for r in rows if r.get("cloudinary_url", "").startswith("http")]
    _add("INFO", "media_assets", f"全{len(rows)}件 / Cloudinaryアップロード済み: {len(uploaded)}件")

    pending = [r for r in rows if not r.get("cloudinary_url", "").startswith("http")]
    if pending:
        _add("WARN", "media_assets 未アップロード", f"{len(pending)}件 → 投稿前にアップロードが必要")
    else:
        _add("PASS", "media_assets", "全件アップロード済み（または対象なし）")


# ------------------------------------------------------------------ #
# main
# ------------------------------------------------------------------ #

def main() -> None:
    parser = argparse.ArgumentParser(description="X本番投稿前最終preflight")
    parser.add_argument("--account-id", help="対象アカウントID")
    parser.add_argument("--mock", action="store_true", help="MockSheetsClient を使用")
    parser.add_argument("--strict", action="store_true", help="WARN でも終了コード 1")
    args = parser.parse_args()

    print("=" * 60)
    print("  preflight_x_real_post.py - X本番投稿前最終preflight（Phase 3-E）")
    print("=" * 60)
    print("[INFO] このスクリプトは実投稿を行いません。")
    print("[INFO] 実投稿コマンドは docs/x-real-post-final-checklist.md を参照してください。")

    # Sheets 接続
    if args.mock:
        print("[INFO] MockSheetsClient を使用します")
        sheets = MockSheetsClient(dry_run=True)
    else:
        try:
            cfg = get_config()
            sheets = SheetsClient(sheet_id=cfg["sheet_id"], sa_dict=cfg["sa_dict"], dry_run=True)
        except ValueError:
            print("[WARN] Sheets認証情報未設定 → MockSheetsClient にフォールバック")
            sheets = MockSheetsClient(dry_run=True)

    # 各チェック実行
    cred_ok = check_x_credentials()
    check_safety_flags()
    tweepy_ok = check_tweepy()
    ready_items = check_ready_queue(sheets, args.account_id)

    if ready_items:
        blocked_rights, blocked_risk, char_over = check_post_safety(ready_items)
    else:
        blocked_rights, blocked_risk, char_over = 0, 0, 0

    check_media_assets(sheets, args.account_id)

    # サマリー
    print("\n" + "=" * 60)
    fail_count = sum(1 for r in RESULTS if r[0] == "FAIL")
    warn_count = sum(1 for r in RESULTS if r[0] == "WARN")
    pass_count = sum(1 for r in RESULTS if r[0] == "PASS")

    print(f"チェック結果: PASS={pass_count} / WARN={warn_count} / FAIL={fail_count}")

    if fail_count > 0 or blocked_rights > 0 or blocked_risk > 0:
        print("\n[RESULT] FAIL: 投稿ブロック条件があります。解消してから再チェックしてください。")
        if blocked_rights > 0:
            print(f"  → rights_review_required=true の投稿: {blocked_rights}件（投稿不可）")
        if blocked_risk > 0:
            print(f"  → media_reuse_risk=high の投稿: {blocked_risk}件（投稿不可）")
        sys.exit(1)
    elif warn_count > 0 and args.strict:
        print("\n[RESULT] WARN（--strict 指定）: 警告を解消してください。")
        sys.exit(1)
    elif warn_count > 0:
        print("\n[RESULT] WARN: 確認推奨の項目があります。")
    else:
        print("\n[RESULT] PASS: 全チェック正常です。")

    print("\n[次のステップ] 実投稿手順:")
    print("  docs/x-real-post-final-checklist.md を参照してください")
    print("  実投稿コマンドは同ドキュメントに記載されています（今回は実行しない）")


if __name__ == "__main__":
    main()
