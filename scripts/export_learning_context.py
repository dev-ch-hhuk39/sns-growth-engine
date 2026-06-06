"""
export_learning_context.py - 学習コンテキストエクスポート（Phase 4.0）

Sheets から現在状態を読み取り、Hermes Agent 分析用の JSON を出力する。
出力先: exports/hermes/learning_context_YYYYMMDD.json

使い方:
  python scripts/export_learning_context.py --account-id night_scout
  python scripts/export_learning_context.py --account-id night_scout --output-dir exports/hermes
  python scripts/export_learning_context.py --mock --account-id night_scout

禁止事項:
  - APIキー・シークレットの出力
  - 本番投稿・Sheets書き込み（読み取り専用）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_V2_ROOT, ".env"))
except ImportError:
    pass

from config_loader import get_config
from sheets_client import MockSheetsClient, SheetsClient


def _safe_get_tab(sheets, tab_name: str, account_id: str | None) -> list[dict]:
    """タブの行を安全に取得する（エラーは無視して空リスト）。"""
    if hasattr(sheets, "_sh"):
        try:
            ws = sheets._sh.worksheet(tab_name)
            rows = ws.get_all_records()
            if account_id:
                rows = [r for r in rows if r.get("account_id") == account_id]
            return rows
        except Exception:
            return []
    # MockSheetsClient
    attr = "_" + tab_name.replace("-", "_")
    rows = getattr(sheets, attr, [])
    if account_id:
        rows = [r for r in rows if r.get("account_id") == account_id]
    return [dict(r) for r in rows]


def _redact_secrets(row: dict) -> dict:
    """APIキー・シークレット列の値をマスクする。"""
    sensitive_keys = {
        "sa_json", "api_key", "token", "secret", "password",
        "credential", "raw_payload_json",
    }
    result = {}
    for k, v in row.items():
        lower_k = k.lower()
        if any(sk in lower_k for sk in sensitive_keys):
            result[k] = "[REDACTED]"
        else:
            result[k] = v
    return result


def export_learning_context(
    sheets,
    account_id: str | None,
    *,
    output_dir: str = "exports/hermes",
) -> str:
    """学習コンテキストをエクスポートし、出力ファイルパスを返す。"""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    suffix = f"_{account_id}" if account_id else "_all"
    filename = f"learning_context{suffix}_{today}.json"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, filename)

    # 各タブからデータ収集
    posted_results = [
        _redact_secrets(r) for r in _safe_get_tab(sheets, "posted_results", account_id)
    ]
    queue_items = _safe_get_tab(sheets, "queue", account_id)
    queue_summary = {
        "total": len(queue_items),
        "READY": sum(1 for q in queue_items if str(q.get("status", "")).upper() == "READY"),
        "WAITING_REVIEW": sum(1 for q in queue_items if str(q.get("status", "")).upper() == "WAITING_REVIEW"),
        "DONE": sum(1 for q in queue_items if str(q.get("status", "")).upper() == "DONE"),
        "ERROR": sum(1 for q in queue_items if str(q.get("status", "")).upper() == "ERROR"),
    }

    gen_jobs = [
        _redact_secrets(r) for r in _safe_get_tab(sheets, "generation_jobs", account_id)
    ]
    recent_gen_jobs = gen_jobs[-10:]  # 直近10件のみ

    learning_rules = _safe_get_tab(sheets, "learning_rules", account_id)
    active_rules = [r for r in learning_rules if str(r.get("active", "")).lower() == "true"]

    prompt_templates = [
        _redact_secrets(r) for r in _safe_get_tab(sheets, "prompt_templates", account_id)
    ]
    active_templates = [
        t for t in prompt_templates
        if str(t.get("active", "")).lower() == "true"
    ]

    suggestions = _safe_get_tab(sheets, "prompt_improvement_suggestions", account_id)
    waiting_suggestions = [
        s for s in suggestions
        if str(s.get("status", "")).upper() == "WAITING_REVIEW"
    ]

    video_clips = _safe_get_tab(sheets, "video_clip_candidates", account_id)
    clip_summary = {
        "total": len(video_clips),
        "approved": sum(1 for c in video_clips if str(c.get("clip_status", "")) == "approved"),
        "candidate": sum(1 for c in video_clips if str(c.get("clip_status", "")) == "candidate"),
    }

    context = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "account_id": account_id or "all",
        "purpose": "Hermes Agent analysis - DO NOT commit to git",
        "posted_results_summary": {
            "count": len(posted_results),
            "recent": posted_results[-5:],
        },
        "queue_summary": queue_summary,
        "recent_generation_jobs": recent_gen_jobs,
        "active_learning_rules": active_rules,
        "active_prompt_templates": active_templates,
        "waiting_improvement_suggestions": waiting_suggestions,
        "video_clip_summary": clip_summary,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(context, f, ensure_ascii=False, indent=2)

    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="学習コンテキストエクスポート")
    parser.add_argument("--account-id", help="エクスポート対象アカウントID")
    parser.add_argument(
        "--output-dir", default="exports/hermes",
        help="出力ディレクトリ（デフォルト: exports/hermes）",
    )
    parser.add_argument("--mock", action="store_true", help="MockSheetsClient を使用")
    args = parser.parse_args()

    print("=" * 60)
    print("  export_learning_context.py - 学習コンテキストエクスポート")
    print("=" * 60)

    if args.mock:
        print("[INFO] MockSheetsClient を使用します")
        sheets = MockSheetsClient(dry_run=True)
    else:
        try:
            cfg = get_config()
        except ValueError as e:
            print(f"[ERROR] 認証情報が必要です: {e}")
            print("  → --mock でモック動作確認できます")
            sys.exit(1)
        sheets = SheetsClient(sheet_id=cfg["sheet_id"], sa_dict=cfg["sa_dict"], dry_run=True)

    print(f"[INFO] アカウント: {args.account_id or '全アカウント'}")
    print(f"[INFO] 出力先: {args.output_dir}/")

    output_path = export_learning_context(
        sheets,
        args.account_id,
        output_dir=args.output_dir,
    )
    print(f"[OK] エクスポート完了: {output_path}")
    print("[注意] このファイルには機密情報が含まれる場合があります。git commit しないでください。")


if __name__ == "__main__":
    main()
