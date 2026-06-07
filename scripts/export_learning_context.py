"""
export_learning_context.py - 学習コンテキストエクスポート（Phase 4.3）

Sheets から現在状態を読み取り、Hermes Agent 分析用の4ファイルを出力する。

出力先（4ファイル）:
  exports/hermes/weekly_growth_report_{account_id}_{date}.md
  exports/hermes/performance_summary_{account_id}_{date}.json
  exports/hermes/account_memory_snapshot_{account_id}_{date}.json
  exports/hermes/improvement_context_{account_id}_{date}.json

使い方:
  python scripts/export_learning_context.py --account-id night_scout
  python scripts/export_learning_context.py --account-id night_scout --output-dir exports/hermes
  python scripts/export_learning_context.py --mock --account-id night_scout

禁止事項:
  - APIキー・シークレットの出力
  - 本番投稿・Sheets書き込み（読み取り専用）
  - git commit
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

try:
    from seeds import ACCOUNT_FORBIDDEN_KEYWORDS, ACCOUNT_FORBIDDEN_THEMES
except ImportError:
    ACCOUNT_FORBIDDEN_KEYWORDS = {}
    ACCOUNT_FORBIDDEN_THEMES = {}


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


def _safe_redact_list(rows: list[dict]) -> list[dict]:
    return [_redact_secrets(r) for r in rows]


# ------------------------------------------------------------------ #
# ファイル1: weekly_growth_report (Markdown)
# ------------------------------------------------------------------ #

def _build_weekly_growth_report_md(
    account_id: str,
    posted_results: list[dict],
    suggestions: list[dict],
    learning_rules: list[dict],
    date_str: str,
) -> str:
    waiting = [s for s in suggestions if str(s.get("status", "")).upper() == "WAITING_REVIEW"]
    approved = [s for s in suggestions if str(s.get("status", "")).upper() == "APPROVED"]
    active_rules = [r for r in learning_rules if str(r.get("active", "")).lower() == "true"]
    recent_posted = posted_results[-10:]

    lines = [
        f"# Weekly Growth Report: {account_id}",
        f"",
        f"**生成日**: {date_str}",
        f"**対象アカウント**: `{account_id}`",
        f"",
        f"---",
        f"",
        f"## 投稿実績サマリー",
        f"",
        f"- 総投稿数: {len(posted_results)}件",
        f"- 直近10件:",
        f"",
    ]
    if recent_posted:
        for p in recent_posted:
            post_id = p.get("post_id", p.get("draft_id", "?"))
            platform = p.get("platform", "?")
            posted_at = p.get("posted_at", "?")
            lines.append(f"  - `{post_id}` ({platform}) - {posted_at}")
    else:
        lines.append("  - (なし)")
    lines.append("")

    lines += [
        f"## 改善提案サマリー",
        f"",
        f"- WAITING_REVIEW: {len(waiting)}件",
        f"- APPROVED: {len(approved)}件",
        f"",
    ]
    if waiting:
        lines.append("### WAITING_REVIEW 提案（Hermes分析用）")
        lines.append("")
        for s in waiting[:5]:
            sid = s.get("suggestion_id", "?")
            stype = s.get("suggestion_type", "?")
            priority = s.get("priority", "?")
            reason = str(s.get("reason", ""))[:100]
            lines.append(f"- `{sid}` [{stype}] priority={priority}")
            lines.append(f"  - {reason}")
        lines.append("")

    lines += [
        f"## 有効な学習ルール",
        f"",
        f"- active=true: {len(active_rules)}件",
        f"",
    ]
    for r in active_rules[:5]:
        rid = r.get("rule_id", "?")
        desc = str(r.get("description", ""))[:80]
        lines.append(f"- `{rid}`: {desc}")
    lines.append("")

    forbidden_kw = ACCOUNT_FORBIDDEN_KEYWORDS.get(account_id, [])
    forbidden_th = ACCOUNT_FORBIDDEN_THEMES.get(account_id, [])
    lines += [
        f"## Account Targeting Policy",
        f"",
        f"**Forbidden keywords**: {', '.join(forbidden_kw) if forbidden_kw else '(なし)'}",
        f"**Forbidden themes**: {', '.join(forbidden_th) if forbidden_th else '(なし)'}",
        f"",
        f"---",
        f"",
        f"*このファイルは Hermes Agent への入力用です。git commit しないでください。*",
    ]
    return "\n".join(lines)


# ------------------------------------------------------------------ #
# ファイル2: performance_summary (JSON)
# ------------------------------------------------------------------ #

def _build_performance_summary(
    account_id: str,
    posted_results: list[dict],
    queue_items: list[dict],
    date_str: str,
) -> dict:
    queue_summary = {
        "total": len(queue_items),
        "READY": sum(1 for q in queue_items if str(q.get("status", "")).upper() == "READY"),
        "WAITING_REVIEW": sum(1 for q in queue_items if str(q.get("status", "")).upper() == "WAITING_REVIEW"),
        "DONE": sum(1 for q in queue_items if str(q.get("status", "")).upper() == "DONE"),
        "ERROR": sum(1 for q in queue_items if str(q.get("status", "")).upper() == "ERROR"),
    }

    type_breakdown: dict[str, int] = {}
    platform_breakdown: dict[str, int] = {}
    for p in posted_results:
        ptype = str(p.get("generation_type", "unknown"))
        type_breakdown[ptype] = type_breakdown.get(ptype, 0) + 1
        platform = str(p.get("platform", "unknown"))
        platform_breakdown[platform] = platform_breakdown.get(platform, 0) + 1

    return {
        "exported_at": date_str,
        "account_id": account_id,
        "purpose": "performance_summary for Hermes analysis",
        "posted_results_count": len(posted_results),
        "post_type_breakdown": type_breakdown,
        "platform_breakdown": platform_breakdown,
        "queue_summary": queue_summary,
        "recent_posts": _safe_redact_list(posted_results[-10:]),
    }


# ------------------------------------------------------------------ #
# ファイル3: account_memory_snapshot (JSON)
# ------------------------------------------------------------------ #

def _build_account_memory_snapshot(
    account_id: str,
    learning_rules: list[dict],
    category_scores: list[dict],
    reference_scores: list[dict],
    date_str: str,
) -> dict:
    active_rules = [r for r in learning_rules if str(r.get("active", "")).lower() == "true"]
    forbidden_kw = ACCOUNT_FORBIDDEN_KEYWORDS.get(account_id, [])
    forbidden_th = ACCOUNT_FORBIDDEN_THEMES.get(account_id, [])

    return {
        "exported_at": date_str,
        "account_id": account_id,
        "purpose": "account_memory_snapshot for Hermes long-term memory",
        "active_learning_rules": active_rules,
        "all_learning_rules_count": len(learning_rules),
        "category_scores_count": len(category_scores),
        "reference_scores_count": len(reference_scores),
        "forbidden_keywords": forbidden_kw,
        "forbidden_themes": forbidden_th,
        "account_targeting_policy": {
            "night_scout": {
                "platform": "x + threads",
                "target": "キャバクラ・ナイトワーク希望女性",
                "forbidden": "代理店勧誘・情報商材的訴求",
            },
            "liver_manager": {
                "platform": "x + threads",
                "target": "ライバー希望者",
                "forbidden": "代理店勧誘・怪しい副業訴求",
            },
        }.get(account_id, {}),
    }


# ------------------------------------------------------------------ #
# ファイル4: improvement_context (JSON)
# ------------------------------------------------------------------ #

def _build_improvement_context(
    account_id: str,
    suggestions: list[dict],
    video_clips: list[dict],
    recent_failures: list[dict],
    date_str: str,
) -> dict:
    waiting = [s for s in suggestions if str(s.get("status", "")).upper() == "WAITING_REVIEW"]
    high_risk = [s for s in waiting if str(s.get("risk_level", "")).lower() == "high"]

    clip_summary = {
        "total": len(video_clips),
        "approved": sum(1 for c in video_clips if str(c.get("clip_status", "")) == "approved"),
        "candidate": sum(1 for c in video_clips if str(c.get("clip_status", "")) == "candidate"),
    }

    return {
        "exported_at": date_str,
        "account_id": account_id,
        "purpose": "improvement_context for Hermes suggestion generation",
        "waiting_suggestions_count": len(waiting),
        "high_risk_waiting_count": len(high_risk),
        "waiting_suggestions": waiting[:20],
        "video_clip_summary": clip_summary,
        "recent_failures_count": len(recent_failures),
        "recent_failures": recent_failures[-5:],
        "next_recommended_experiments": [
            "低エンゲージメント投稿パターンの分析",
            "rights_review_required=true 投稿の削減策",
            "フック行の改善（120文字制限内での表現強化）",
        ],
        "import_instructions": (
            "提案は imports/hermes/improvement_suggestions.json に "
            "WAITING_REVIEW 状態で保存し、import_improvement_suggestions.py でインポートする"
        ),
    }


# ------------------------------------------------------------------ #
# メイン export 関数
# ------------------------------------------------------------------ #

def export_all_files(
    sheets,
    account_id: str | None,
    *,
    output_dir: str = "exports/hermes",
) -> list[str]:
    """4ファイルをエクスポートし、出力ファイルパスのリストを返す。"""
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y%m%d")
    suffix = account_id or "all"
    os.makedirs(output_dir, exist_ok=True)

    # データ収集
    posted_results = _safe_redact_list(_safe_get_tab(sheets, "posted_results", account_id))
    queue_items = _safe_get_tab(sheets, "queue", account_id)
    learning_rules = _safe_get_tab(sheets, "learning_rules", account_id)
    category_scores = _safe_get_tab(sheets, "category_scores", account_id)
    reference_scores = _safe_get_tab(sheets, "reference_post_scores", account_id)
    suggestions = _safe_get_tab(sheets, "prompt_improvement_suggestions", account_id)
    video_clips = _safe_get_tab(sheets, "video_clip_candidates", account_id)

    # 失敗ログ収集（generation_jobs の ERROR 状態）
    gen_jobs = _safe_get_tab(sheets, "generation_jobs", account_id)
    recent_failures = [
        _redact_secrets(j) for j in gen_jobs
        if str(j.get("status", "")).upper() in ("ERROR", "FAILED")
    ][-10:]

    output_files: list[str] = []

    # ---- ファイル1: weekly_growth_report (Markdown) ----
    md_path = os.path.join(output_dir, f"weekly_growth_report_{suffix}_{date_str}.md")
    md_content = _build_weekly_growth_report_md(
        account_id or "all",
        posted_results,
        suggestions,
        learning_rules,
        now.isoformat(),
    )
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    output_files.append(md_path)

    # ---- ファイル2: performance_summary (JSON) ----
    perf_path = os.path.join(output_dir, f"performance_summary_{suffix}_{date_str}.json")
    perf_data = _build_performance_summary(
        account_id or "all",
        posted_results,
        queue_items,
        now.isoformat(),
    )
    with open(perf_path, "w", encoding="utf-8") as f:
        json.dump(perf_data, f, ensure_ascii=False, indent=2)
    output_files.append(perf_path)

    # ---- ファイル3: account_memory_snapshot (JSON) ----
    mem_path = os.path.join(output_dir, f"account_memory_snapshot_{suffix}_{date_str}.json")
    mem_data = _build_account_memory_snapshot(
        account_id or "all",
        learning_rules,
        category_scores,
        reference_scores,
        now.isoformat(),
    )
    with open(mem_path, "w", encoding="utf-8") as f:
        json.dump(mem_data, f, ensure_ascii=False, indent=2)
    output_files.append(mem_path)

    # ---- ファイル4: improvement_context (JSON) ----
    imp_path = os.path.join(output_dir, f"improvement_context_{suffix}_{date_str}.json")
    imp_data = _build_improvement_context(
        account_id or "all",
        suggestions,
        video_clips,
        recent_failures,
        now.isoformat(),
    )
    with open(imp_path, "w", encoding="utf-8") as f:
        json.dump(imp_data, f, ensure_ascii=False, indent=2)
    output_files.append(imp_path)

    return output_files


# 後方互換性のためのラッパー（旧 export_learning_context インターフェース）
def export_learning_context(
    sheets,
    account_id: str | None,
    *,
    output_dir: str = "exports/hermes",
) -> str:
    """旧インターフェース互換：improvement_context ファイルのパスを返す。"""
    files = export_all_files(sheets, account_id, output_dir=output_dir)
    return files[-1] if files else ""


def main() -> None:
    parser = argparse.ArgumentParser(description="学習コンテキストエクスポート（4ファイル）")
    parser.add_argument("--account-id", help="エクスポート対象アカウントID")
    parser.add_argument(
        "--output-dir", default="exports/hermes",
        help="出力ディレクトリ（デフォルト: exports/hermes）",
    )
    parser.add_argument("--mock", action="store_true", help="MockSheetsClient を使用")
    args = parser.parse_args()

    print("=" * 60)
    print("  export_learning_context.py - 学習コンテキストエクスポート（Phase 4.3）")
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
    print("[INFO] 4ファイルを出力します")

    output_files = export_all_files(
        sheets,
        args.account_id,
        output_dir=args.output_dir,
    )
    for path in output_files:
        print(f"  [OK] {path}")
    print(f"\n[完了] {len(output_files)}ファイルをエクスポートしました")
    print("[注意] このファイルには機密情報が含まれる場合があります。git commit しないでください。")


if __name__ == "__main__":
    main()
