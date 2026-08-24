"""threads_credentials.py — Threads 認証情報リゾルバー

account_id から app_id / app_secret / access_token / user_id を解決する。
値はログに絶対に出力しない。

優先順位（フィールドごと）:
  access_token:  account file → THREADS_ACCESS_TOKEN_{UPPER}
  user_id:       THREADS_USER_ID_{UPPER} → account file
  app_id:        THREADS_APP_ID_{UPPER} → file → THREADS_APP_ID
  app_secret:    THREADS_APP_SECRET_{UPPER} → file → THREADS_APP_SECRET

Access token and user identity never use global fallback because doing so can
publish through a different managed account. App credentials may be shared.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

_DEFAULT_TOKEN_DIR = Path(os.environ.get("THREADS_TOKEN_STORE_DIR", "data/threads_tokens"))


def _token_path(account_id: str) -> Path:
    return _DEFAULT_TOKEN_DIR / f"{account_id}.json"


def _load_token_file(account_id: str) -> dict:
    p = _token_path(account_id)
    if p.exists():
        try:
            with open(p) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def resolve_credentials(account_id: str) -> dict:
    """account_id から認証情報を解決して返す。値はログに出さない。

    Returns:
        dict with keys: app_id, app_secret, access_token, user_id
        未設定の場合は "" (空文字)
    """
    from accounts.managed_accounts import credential_env_names

    upper = account_id.upper()
    env_names = credential_env_names(account_id)
    stored = _load_token_file(account_id)

    # Access and user identity are account-scoped. A global fallback could
    # silently publish through another managed account, so it is forbidden.
    access_token = (
        stored.get("access_token", "")
        or os.environ.get(env_names["access_token"], "").strip()
    )

    # user_id: account-specific env → account-specific token file
    user_id = (
        os.environ.get(env_names["user_id"], "").strip()
        or stored.get("user_id", "")
    )

    # app_id: account-specific env → file → fallback env
    app_id = (
        os.environ.get(f"THREADS_APP_ID_{upper}", "").strip()
        or stored.get("app_id", "")
        or os.environ.get("THREADS_APP_ID", "").strip()
    )

    # app_secret: account-specific env → file → fallback env
    app_secret = (
        os.environ.get(f"THREADS_APP_SECRET_{upper}", "").strip()
        or stored.get("app_secret", "")
        or os.environ.get("THREADS_APP_SECRET", "").strip()
    )

    return {
        "app_id": app_id,
        "app_secret": app_secret,
        "access_token": access_token,
        "user_id": user_id,
    }


def has_required_for_publish(creds: dict) -> tuple[bool, str]:
    """投稿に必要な認証情報が揃っているか確認する。"""
    if not creds.get("access_token"):
        return False, "THREADS_ACCESS_TOKEN が未設定"
    if not creds.get("user_id"):
        return False, "THREADS_USER_ID が未設定"
    return True, ""


def has_required_for_refresh(creds: dict) -> tuple[bool, str]:
    """トークンリフレッシュに必要な認証情報が揃っているか確認する。

    長期トークンの自己リフレッシュは access_token のみ必要。
    app_id / app_secret は不要。
    """
    if not creds.get("access_token"):
        return False, "THREADS_ACCESS_TOKEN が未設定"
    return True, ""
