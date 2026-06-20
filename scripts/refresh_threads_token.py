"""Threads アクセストークンをリフレッシュするCLIツール。

Threads 長期アクセストークンは 60日で期限切れになる。
このスクリプトはリフレッシュAPIを呼び出して期限を延長し、
結果をローカルJSONファイルに保存する。

Usage:
    python3 scripts/refresh_threads_token.py \\
        --account-id night_scout \\
        --confirm-refresh \\
        [--dry-run]

--dry-run: API は呼ばずにトークン状態のみ表示する。
--confirm-refresh: 実際にリフレッシュAPIを呼び出す。

安全ルール:
  - トークン値はログに出力しない
  - 結果は data/threads_tokens/{account_id}.json に保存する（.gitignore 対象）
  - GITHUB_OUTPUT には書き込まない
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv()

THREADS_REFRESH_URL = "https://graph.threads.net/refresh_access_token"
_DEFAULT_TOKEN_DIR = Path(os.environ.get("THREADS_TOKEN_STORE_DIR", "data/threads_tokens"))

JST = timezone(timedelta(hours=9))


def _token_path(account_id: str) -> Path:
    return _DEFAULT_TOKEN_DIR / f"{account_id}.json"


def _load_token(account_id: str) -> dict | None:
    """トークンJSONを読み込む。存在しなければ None を返す。"""
    p = _token_path(account_id)
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return None


def _save_token(account_id: str, data: dict) -> None:
    p = _token_path(account_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  保存先: {p}")


def _get_current_token(account_id: str) -> str | None:
    """現在のトークンを取得する（ファイル→env の順）。値は返すが表示しない。"""
    stored = _load_token(account_id)
    if stored and stored.get("access_token"):
        return stored["access_token"]
    # env から取得
    key = f"THREADS_ACCESS_TOKEN_{account_id.upper()}"
    token = os.environ.get(key, "").strip()
    if token:
        return token
    token = os.environ.get("THREADS_ACCESS_TOKEN", "").strip()
    return token or None


def _mask(token: str) -> str:
    if len(token) <= 8:
        return "***"
    return token[:4] + "..." + token[-4:]


def refresh(account_id: str, dry_run: bool) -> None:
    import requests

    current_token = _get_current_token(account_id)
    if not current_token:
        print(
            f"ERROR: アカウント '{account_id}' の THREADS_ACCESS_TOKEN が見つかりません。\n"
            f"  設定方法:\n"
            f"  1. .env に THREADS_ACCESS_TOKEN_{account_id.upper()}=<token> を追加\n"
            f"  2. または data/threads_tokens/{account_id}.json を作成"
        )
        sys.exit(1)

    stored = _load_token(account_id)
    if stored:
        expires_at = stored.get("expires_at")
        refreshed_at = stored.get("refreshed_at")
        print(f"  現在のトークン: {_mask(current_token)}")
        print(f"  最終リフレッシュ: {refreshed_at}")
        print(f"  期限: {expires_at}")
    else:
        print(f"  現在のトークン: {_mask(current_token)}")
        print(f"  ストアファイル: 未作成（初回リフレッシュ）")

    if dry_run:
        print(f"\n[DRY_RUN] アカウント '{account_id}' のトークンリフレッシュをスキップします。")
        print(f"  実際にリフレッシュするには --confirm-refresh を使用してください。")
        return

    print(f"\nリフレッシュ中...")
    params = {
        "grant_type": "th_refresh_token",
        "access_token": current_token,
    }
    resp = requests.get(THREADS_REFRESH_URL, params=params, timeout=30)
    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        print(f"ERROR: リフレッシュAPIエラー: {resp.status_code} {resp.text}")
        raise SystemExit(1) from e

    data = resp.json()
    new_token = data.get("access_token")
    expires_in = data.get("token_type")  # Threads API はtoken_typeのみ返す場合あり

    if not new_token:
        print(f"ERROR: レスポンスに access_token がありません: {data}")
        sys.exit(1)

    now = datetime.now(JST)
    expires_at = (now + timedelta(days=60)).isoformat()

    store_data = {
        "access_token": new_token,
        "refreshed_at": now.isoformat(),
        "expires_at": expires_at,
        "account_id": account_id,
    }
    _save_token(account_id, store_data)
    print(f"  新しいトークン: {_mask(new_token)}")
    print(f"  期限: {expires_at}")
    print(f"\n[OK] アカウント '{account_id}' のトークンリフレッシュが完了しました。")
    print(f"     次回リフレッシュ推奨: {(now + timedelta(days=45)).strftime('%Y-%m-%d')}")


def show_status(account_id: str) -> None:
    """トークンの現在状態を表示する。"""
    token = _get_current_token(account_id)
    if not token:
        print(f"  status: NOT_SET")
        return

    stored = _load_token(account_id)
    print(f"  token: {_mask(token)}")
    if stored:
        expires_at_str = stored.get("expires_at", "")
        if expires_at_str:
            try:
                expires_at = datetime.fromisoformat(expires_at_str)
                now = datetime.now(JST)
                days_left = (expires_at - now).days
                print(f"  expires_at: {expires_at_str}  (残り {days_left} 日)")
                if days_left < 15:
                    print(f"  WARN: トークンの有効期限が {days_left} 日です。早急にリフレッシュしてください。")
                elif days_left < 45:
                    print(f"  WARN: トークンの有効期限が {days_left} 日です。リフレッシュを検討してください。")
            except ValueError:
                print(f"  expires_at: {expires_at_str}")
    else:
        print(f"  ストアファイル: 未作成（期限不明）")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Threads アクセストークンをリフレッシュする"
    )
    parser.add_argument(
        "--account-id",
        required=True,
        help="対象アカウントID (例: night_scout, liver_manager)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="API を呼ばずにトークン状態のみ表示する",
    )
    parser.add_argument(
        "--confirm-refresh",
        action="store_true",
        help="実際にリフレッシュAPIを呼び出す",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="トークンの現在状態を表示する（リフレッシュしない）",
    )
    args = parser.parse_args()

    if args.status:
        print(f"=== トークン状態: {args.account_id} ===")
        show_status(args.account_id)
        return

    if not args.dry_run and not args.confirm_refresh:
        print("ERROR: --dry-run または --confirm-refresh のいずれかを指定してください")
        sys.exit(1)

    print(f"=== Threads トークンリフレッシュ: {args.account_id} ===")
    dry_run = args.dry_run and not args.confirm_refresh
    refresh(args.account_id, dry_run=dry_run)


if __name__ == "__main__":
    main()
