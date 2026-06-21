"""
config_loader.py - 環境変数の読み込みと検証

対応認証方式:
  SA_JSON_BASE64: base64エンコードされたサービスアカウントJSON（ライバー・夜職threads方式）
  GCP_SA_JSON:    JSONをそのまま貼った文字列（夜職x方式）

安全ガード環境変数:
  DRY_RUN=true               シート書き込み & LLM 両方モック
  MOCK_LLM=true              LLM のみモック
  MOCK_SHEETS=true           Sheets を MockSheetsClient に強制切替
  PUBLISH_ENABLED=false      Phase 3-D まで false のまま（SNS投稿処理ガード）
  ALLOW_REAL_X_POST=false    Phase 3-D の X 手動投稿テスト時のみ true
  ALLOW_REAL_THREADS_POST=false Phase 3-E の Threads テスト時のみ true
  ALLOW_CLOUDINARY_UPLOAD=false Phase 2.12 以降: 実アップロード有効化フラグ
  ALLOW_SHEETS_WRITE         廃止 → dry_run=False で制御

SNS Publisher 環境変数:
  X API (OAuth 1.0a):  X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET
  X API (OAuth 2.0):   X_CLIENT_ID, X_CLIENT_SECRET, X_OAUTH2_ACCESS_TOKEN, X_OAUTH2_REFRESH_TOKEN
  X API (misc):        X_BEARER_TOKEN, X_REDIRECT_URI
  Threads API:         THREADS_ACCESS_TOKEN, THREADS_USER_ID, THREADS_APP_ID, THREADS_APP_SECRET
                       THREADS_API_VERSION

Cloudinary 環境変数:
  CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET
  ALLOW_CLOUDINARY_UPLOAD: false のまま変更しないこと（Phase 2.12 デフォルト）

Cloudflare Workers AI 環境変数（Phase 2.20追加）:
  CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN
  ALLOW_TRANSCRIPTION_API: false のまま変更しないこと（Phase 2.20 デフォルト）
  TRANSCRIPTION_PROVIDER: cloudflare_whisper（デフォルト）
  DAILY_TRANSCRIPTION_MINUTES_LIMIT: 120（分）

注意: APIキー・トークン等の値はログに出力しない。
"""
import os
import json
import base64

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _is_true(env_key: str) -> bool:
    return os.environ.get(env_key, "false").strip().lower() in ("1", "true", "yes")


def get_x_credentials() -> dict:
    """X API 認証情報を返す。値は呼び出し元でログに出力しないこと。"""
    return {
        "api_key_set": bool(os.environ.get("X_API_KEY", "").strip()),
        "api_secret_set": bool(os.environ.get("X_API_SECRET", "").strip()),
        "access_token_set": bool(os.environ.get("X_ACCESS_TOKEN", "").strip()),
        "access_token_secret_set": bool(os.environ.get("X_ACCESS_TOKEN_SECRET", "").strip()),
        "bearer_token_set": bool(os.environ.get("X_BEARER_TOKEN", "").strip()),
        "client_id_set": bool(os.environ.get("X_CLIENT_ID", "").strip()),
        "client_secret_set": bool(os.environ.get("X_CLIENT_SECRET", "").strip()),
        "redirect_uri_set": bool(os.environ.get("X_REDIRECT_URI", "").strip()),
        "oauth2_access_token_set": bool(os.environ.get("X_OAUTH2_ACCESS_TOKEN", "").strip()),
        "oauth2_refresh_token_set": bool(os.environ.get("X_OAUTH2_REFRESH_TOKEN", "").strip()),
        # 実値は返さない（ログ誤出力防止）
        "api_key": os.environ.get("X_API_KEY", "").strip() or None,
        "api_secret": os.environ.get("X_API_SECRET", "").strip() or None,
        "access_token": os.environ.get("X_ACCESS_TOKEN", "").strip() or None,
        "access_token_secret": os.environ.get("X_ACCESS_TOKEN_SECRET", "").strip() or None,
        "oauth2_access_token": os.environ.get("X_OAUTH2_ACCESS_TOKEN", "").strip() or None,
        "oauth2_refresh_token": os.environ.get("X_OAUTH2_REFRESH_TOKEN", "").strip() or None,
    }


def get_threads_credentials() -> dict:
    """Threads API 認証情報を返す。値は呼び出し元でログに出力しないこと。"""
    return {
        "access_token_set": bool(os.environ.get("THREADS_ACCESS_TOKEN", "").strip()),
        "user_id_set": bool(os.environ.get("THREADS_USER_ID", "").strip()),
        "app_id_set": bool(os.environ.get("THREADS_APP_ID", "").strip()),
        "app_secret_set": bool(os.environ.get("THREADS_APP_SECRET", "").strip()),
        "api_version": os.environ.get("THREADS_API_VERSION", "v1.0").strip(),
        # 実値は返さない（ログ誤出力防止）
        "access_token": os.environ.get("THREADS_ACCESS_TOKEN", "").strip() or None,
        "user_id": os.environ.get("THREADS_USER_ID", "").strip() or None,
        "app_id": os.environ.get("THREADS_APP_ID", "").strip() or None,
    }


def get_publish_guards() -> dict:
    """SNS投稿安全ガードの状態を返す。"""
    return {
        "publish_enabled": _is_true("PUBLISH_ENABLED"),
        "allow_real_x_post": _is_true("ALLOW_REAL_X_POST"),
        "allow_real_threads_post": _is_true("ALLOW_REAL_THREADS_POST"),
    }


def get_cloudinary_config() -> dict:
    """Cloudinary 設定を返す。API secret は bool フラグのみ公開。

    cloud_name と api_key は非機密（公開前提）だが、api_secret はログ禁止。
    allow_upload が False のときは実アップロードを行わない。
    """
    return {
        "cloud_name": os.environ.get("CLOUDINARY_CLOUD_NAME", "").strip(),
        "api_key": os.environ.get("CLOUDINARY_API_KEY", "").strip(),
        "api_secret": os.environ.get("CLOUDINARY_API_SECRET", "").strip() or None,
        "api_secret_set": bool(os.environ.get("CLOUDINARY_API_SECRET", "").strip()),
        "allow_upload": _is_true("ALLOW_CLOUDINARY_UPLOAD"),
    }


def get_transcription_config() -> dict:
    """Cloudflare Workers AI 文字起こし設定を返す。API トークンは bool フラグのみ公開。

    allow_transcription_api が False のときは実API呼び出しを行わない。
    """
    return {
        "account_id": os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip(),
        "account_id_set": bool(os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()),
        "api_token_set": bool(os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()),
        "api_token": os.environ.get("CLOUDFLARE_API_TOKEN", "").strip() or None,
        "allow_transcription_api": _is_true("ALLOW_TRANSCRIPTION_API"),
        "provider": os.environ.get("TRANSCRIPTION_PROVIDER", "cloudflare_whisper").strip(),
        "daily_limit_minutes": int(
            os.environ.get("DAILY_TRANSCRIPTION_MINUTES_LIMIT", "120").strip() or "120"
        ),
    }


def get_config_partial() -> dict:
    """エラーを投げない設定読み込み。不足項目は None または空文字で返す。テストCLI向け。"""
    sheet_id = (
        os.environ.get("SNS_MASTER_SHEET_ID", "").strip()
        or os.environ.get("NOTE_MASTER_SHEET_ID", "").strip()
    )
    sa_dict = None
    try:
        sa_dict = _load_sa_dict()
    except Exception:
        pass
    return {
        "sheet_id": sheet_id,
        "gemini_api_key": os.environ.get("GEMINI_API_KEY", "").strip(),
        "gemini_model_candidates": os.environ.get(
            "GEMINI_MODEL_CANDIDATES",
            "gemini-2.5-flash-lite@v1beta,gemini-2.5-flash@v1beta,gemini-2.5-pro@v1beta",
        ).strip(),
        "sa_dict": sa_dict,
        "dry_run": _is_true("DRY_RUN"),
        "mock_llm": _is_true("MOCK_LLM"),
        "mock_sheets": _is_true("MOCK_SHEETS"),
        "publish_enabled": _is_true("PUBLISH_ENABLED"),
        "allow_real_x_post": _is_true("ALLOW_REAL_X_POST"),
        "allow_real_threads_post": _is_true("ALLOW_REAL_THREADS_POST"),
        "discord_webhook_url": os.environ.get("DISCORD_WEBHOOK_URL", "").strip(),
    }


def get_config() -> dict:
    """環境変数を読み込んで設定dictを返す。必須項目が欠けている場合はValueErrorを投げる。"""
    # SNS_MASTER_SHEET_ID が優先。未設定時は NOTE_MASTER_SHEET_ID にフォールバック（後方互換）。
    sheet_id = (
        os.environ.get("SNS_MASTER_SHEET_ID", "").strip()
        or os.environ.get("NOTE_MASTER_SHEET_ID", "").strip()
    )
    cfg = {
        "sheet_id": sheet_id,
        "gemini_api_key": os.environ.get("GEMINI_API_KEY", "").strip(),
        "gemini_model_candidates": os.environ.get(
            "GEMINI_MODEL_CANDIDATES",
            "gemini-2.5-flash-lite@v1beta,gemini-2.5-flash@v1beta,gemini-2.5-pro@v1beta",
        ).strip(),
        "discord_webhook_url": os.environ.get("DISCORD_WEBHOOK_URL", "").strip(),
        "dry_run": _is_true("DRY_RUN"),
        "sa_dict": _load_sa_dict(),
    }

    if not cfg["sheet_id"]:
        raise ValueError(
            "SNS_MASTER_SHEET_ID が未設定です。.env を確認してください。"
            "（旧名称 NOTE_MASTER_SHEET_ID も未設定）"
        )
    if cfg["sa_dict"] is None:
        raise ValueError(
            "GCP認証情報が未設定です。SA_JSON_BASE64 または GCP_SA_JSON を設定してください。"
        )

    return cfg


def _load_sa_dict() -> dict | None:
    """SA_JSON_BASE64 または GCP_SA_JSON からサービスアカウントdictを返す。"""
    b64 = os.environ.get("SA_JSON_BASE64", "").strip()
    # 非ASCII文字（プレースホルダー等）は無効とみなして GCP_SA_JSON にフォールバック
    if b64 and all(ord(c) < 128 for c in b64):
        try:
            decoded = base64.b64decode(b64).decode("utf-8")
            return json.loads(decoded)
        except Exception as e:
            raise ValueError(f"SA_JSON_BASE64 のデコードに失敗しました: {e}") from e

    raw = os.environ.get("GCP_SA_JSON", "").strip()
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # 変数名が GCP_SA_JSON でも base64 エンコード値の場合がある
            try:
                decoded = base64.b64decode(raw).decode("utf-8")
                return json.loads(decoded)
            except Exception as e2:
                raise ValueError(f"GCP_SA_JSON のパース/デコードに失敗しました: {e2}") from e2

    return None
