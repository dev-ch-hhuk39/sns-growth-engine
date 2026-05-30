"""
check_pipeline_integrity.py - パイプラインデータ整合性チェック

実際の Google Sheets データを読み取り、drafts / social_derivatives /
queue / logs / posted_results の整合性を検証する。

使い方:
  # 実Sheetsに対してチェック（--use-sheetsが必要）
  python scripts/check_pipeline_integrity.py --account-id night_scout

  # WARN があっても終了コード 0（デフォルト）
  python scripts/check_pipeline_integrity.py --account-id night_scout

  # WARN でも非ゼロで終了
  python scripts/check_pipeline_integrity.py --account-id night_scout --fail-on-warn

  # モックで構造確認のみ（実データ検証不可）
  python scripts/check_pipeline_integrity.py --mock

出力:
  [PASS] 正常
  [WARN] 問題の可能性あり（オプションで非ゼロ終了）
  [FAIL] データ整合性エラー
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

from config_loader import get_config, get_config_partial
from sheets_client import SheetsClient, MockSheetsClient, make_client


VALID_DRAFT_STATUSES = {"DRAFT", "READY", "REVIEW", "POSTED", "REJECTED", "ARCHIVED"}
VALID_DERIVATIVE_STATUSES = {"DRAFT", "READY", "WAITING_REVIEW", "APPROVED", "REJECTED"}
VALID_QUEUE_STATUSES = {"READY", "WAITING_REVIEW", "PROCESSING", "DONE", "ERROR", "SKIPPED"}
VALID_LOG_LEVELS = {"INFO", "WARN", "ERROR"}


def check_drafts(sheets, account_id: str | None, results: list) -> int:
    """drafts タブの整合性チェック。問題件数を返す。"""
    issues = 0
    try:
        drafts = sheets.get_drafts(account_id=account_id)
        results.append(f"  [PASS] drafts 取得OK: {len(drafts)}件")

        score_missing = 0
        status_invalid = 0
        for d in drafts:
            score_val = d.get("score", "")
            if score_val == "" or score_val is None:
                score_missing += 1
            s = str(d.get("status", "")).upper()
            if s and s not in VALID_DRAFT_STATUSES:
                status_invalid += 1

        if score_missing > 0:
            results.append(f"  [WARN] drafts.score が空の行: {score_missing}件 (--setup 実行後に再チェックしてください)")
            issues += 1
        else:
            results.append(f"  [PASS] drafts.score は全行に値あり")

        if status_invalid > 0:
            results.append(f"  [FAIL] drafts.status が不正な行: {status_invalid}件")
            issues += 1
        else:
            results.append(f"  [PASS] drafts.status は全行正常")

    except Exception as e:
        results.append(f"  [FAIL] drafts 取得エラー: {e}")
        issues += 1

    return issues


def check_social_derivatives(sheets, account_id: str | None, results: list) -> int:
    """social_derivatives タブの整合性チェック。"""
    issues = 0
    try:
        ders = sheets.get_social_derivatives(account_id=account_id)
        results.append(f"  [PASS] social_derivatives 取得OK: {len(ders)}件")

        drafts = sheets.get_drafts(account_id=account_id)
        draft_ids = {d.get("draft_id") for d in drafts}

        dangling = 0
        status_invalid = 0
        text_empty = 0
        for d in ders:
            did = d.get("draft_id", "")
            if did and did not in draft_ids:
                dangling += 1
            s = str(d.get("status", "")).upper()
            if s and s not in VALID_DERIVATIVE_STATUSES:
                status_invalid += 1
            if not d.get("text", "").strip():
                text_empty += 1

        if dangling > 0:
            results.append(f"  [WARN] 対応する draft_id がない social_derivatives: {dangling}件")
            issues += 1
        else:
            results.append(f"  [PASS] social_derivatives の draft_id 参照整合性OK")

        if status_invalid > 0:
            results.append(f"  [FAIL] social_derivatives.status が不正な行: {status_invalid}件")
            issues += 1
        else:
            results.append(f"  [PASS] social_derivatives.status は全行正常")

        if text_empty > 0:
            results.append(f"  [WARN] social_derivatives.text が空の行: {text_empty}件")
            issues += 1
        else:
            results.append(f"  [PASS] social_derivatives.text は全行に値あり")

    except Exception as e:
        results.append(f"  [FAIL] social_derivatives 取得エラー: {e}")
        issues += 1

    return issues


def check_queue(sheets, account_id: str | None, results: list) -> int:
    """queue タブの整合性チェック。"""
    issues = 0
    try:
        ws = sheets._sh.worksheet("queue") if hasattr(sheets, "_sh") else None
        if ws is None:
            queue_items = sheets._queue if hasattr(sheets, "_queue") else []
        else:
            queue_items = ws.get_all_records()
            if account_id:
                queue_items = [r for r in queue_items if r.get("account_id") == account_id]

        results.append(f"  [PASS] queue 取得OK: {len(queue_items)}件")

        waiting_review = [q for q in queue_items if str(q.get("status", "")).upper() == "WAITING_REVIEW"]
        ready = [q for q in queue_items if str(q.get("status", "")).upper() == "READY"]
        status_invalid = sum(
            1 for q in queue_items
            if str(q.get("status", "")).upper() not in VALID_QUEUE_STATUSES
        )

        if waiting_review:
            results.append(f"  [WARN] queue.status=WAITING_REVIEW が {len(waiting_review)}件あります (review_queue.py で確認してください)")
            issues += 1
        else:
            results.append(f"  [PASS] queue に WAITING_REVIEW はありません")

        if ready:
            results.append(f"  [PASS] queue.status=READY: {len(ready)}件 (Phase 3 投稿待ち)")
        else:
            results.append(f"  [WARN] queue.status=READY が0件です (キューが空)")
            issues += 1

        if status_invalid > 0:
            results.append(f"  [FAIL] queue.status が不正な行: {status_invalid}件")
            issues += 1
        else:
            results.append(f"  [PASS] queue.status は全行正常")

    except Exception as e:
        results.append(f"  [FAIL] queue 取得エラー: {e}")
        issues += 1

    return issues


def check_logs(sheets, account_id: str | None, results: list) -> int:
    """logs タブの整合性チェック。"""
    issues = 0
    try:
        if hasattr(sheets, "_sh"):
            ws = sheets._sh.worksheet("logs")
            log_rows = ws.get_all_records()
            if account_id:
                log_rows = [r for r in log_rows if r.get("account_id") in (account_id, "")]
        else:
            log_rows = getattr(sheets, "_logs", [])

        results.append(f"  [PASS] logs 取得OK: {len(log_rows)}件")

        level_missing = sum(1 for r in log_rows if not r.get("level", "").strip())
        error_count = sum(1 for r in log_rows if str(r.get("level", "")).upper() == "ERROR")

        if level_missing > 0:
            results.append(f"  [WARN] logs.level が空の行: {level_missing}件 (--setup 実行後に解消します)")
            issues += 1
        else:
            results.append(f"  [PASS] logs.level は全行に値あり")

        if error_count > 0:
            results.append(f"  [WARN] logs に ERROR レベルのログ: {error_count}件 (内容を確認してください)")
            issues += 1
        else:
            results.append(f"  [PASS] logs に ERROR レベルのログなし")

    except Exception as e:
        results.append(f"  [FAIL] logs 取得エラー: {e}")
        issues += 1

    return issues


def check_posted_results(sheets, account_id: str | None, results: list) -> int:
    """posted_results タブが空であることを確認（Phase 2 段階では空が正常）。"""
    issues = 0
    try:
        if hasattr(sheets, "_sh"):
            ws = sheets._sh.worksheet("posted_results")
            rows = ws.get_all_records()
            if account_id:
                rows = [r for r in rows if r.get("account_id") == account_id]
        else:
            rows = []

        if rows:
            results.append(f"  [WARN] posted_results に {len(rows)}件あります (Phase 3 実施前は0件が正常)")
            issues += 1
        else:
            results.append(f"  [PASS] posted_results は空（Phase 2 正常状態）")

    except Exception as e:
        results.append(f"  [FAIL] posted_results 取得エラー: {e}")
        issues += 1

    return issues


VALID_MEDIA_TYPES = {"image", "video", "gif", "unknown"}
VALID_REUSE_STATUSES = {"", "empty", "approved", "review", "rejected", "reference_only", "available", "used", "restricted"}
VALID_STORAGE_PROVIDERS = {"", "cloudinary", "none", "dry_run"}
VALID_RISK_LEVELS = {"", "low", "medium", "high", "unknown"}
VALID_GENERATION_MODES = {"reference_based", "original_hypothesis"}
VALID_GENERATION_JOB_STATUSES = {"", "pending", "in_progress", "done", "failed"}
VALID_CONFIDENCE_LEVELS = {"", "HIGH", "MEDIUM", "LOW"}
VALID_AI_RECOMMENDATIONS = {"", "recommend", "review", "reject"}
VALID_TEXT_POLICY_STATUSES = {"", "OK", "WARN", "FAIL"}
VALID_MEDIA_STRATEGIES = {"", "none", "reference_image", "original_image"}


def _get_tab_rows(sheets, tab_name: str, account_id: str | None) -> list[dict]:
    """タブの全行を取得する。タブが存在しない場合は空リストを返す。"""
    if hasattr(sheets, "_sh"):
        try:
            ws = sheets._sh.worksheet(tab_name)
            rows = ws.get_all_records()
            if account_id:
                rows = [r for r in rows if r.get("account_id") == account_id]
            return rows
        except Exception:
            return []
    return []


def check_media_assets(sheets, account_id: str | None, results: list) -> int:
    """media_assets タブの整合性チェック（Phase 2.12 強化）。"""
    import re as _re

    def _is_url(val: str) -> bool:
        return bool(_re.match(r"^https?://", val.strip()))

    issues = 0
    try:
        rows = _get_tab_rows(sheets, "media_assets", account_id)

        if not rows:
            results.append(f"  [PASS] media_assets は空（初期状態として正常）")
            return 0

        results.append(f"  [PASS] media_assets 取得OK: {len(rows)}件")

        required_cols = ["media_id", "account_id", "reference_post_id", "original_media_url",
                         "storage_provider", "storage_url", "media_type",
                         "reuse_status", "media_reuse_risk", "used_count"]
        missing_cols = [c for c in required_cols if c not in (rows[0].keys() if rows else [])]
        if missing_cols:
            results.append(f"  [FAIL] media_assets に必須列がありません: {missing_cols}")
            return issues + 1

        no_media_id = 0
        no_ref_post_id = 0
        no_orig_url = 0
        invalid_storage_provider = 0
        storage_url_fmt_err = 0
        invalid_type = 0
        invalid_reuse = 0
        invalid_risk = 0
        used_count_err = 0

        for r in rows:
            if not str(r.get("media_id", "")).strip():
                no_media_id += 1
            if not str(r.get("reference_post_id", "")).strip():
                no_ref_post_id += 1
            if not str(r.get("original_media_url", "")).strip():
                no_orig_url += 1
            provider = str(r.get("storage_provider", "")).lower().strip()
            if provider not in VALID_STORAGE_PROVIDERS:
                invalid_storage_provider += 1
            storage_url = str(r.get("storage_url", "")).strip()
            if storage_url and not _is_url(storage_url):
                storage_url_fmt_err += 1
            mtype = str(r.get("media_type", "")).lower().strip()
            if mtype and mtype not in VALID_MEDIA_TYPES:
                invalid_type += 1
            reuse = str(r.get("reuse_status", "")).lower().strip()
            if reuse not in VALID_REUSE_STATUSES:
                invalid_reuse += 1
            risk = str(r.get("media_reuse_risk", "")).lower().strip()
            if risk not in VALID_RISK_LEVELS:
                invalid_risk += 1
            used = str(r.get("used_count", "")).strip()
            if used and not used.isdigit():
                used_count_err += 1

        def _check(count: int, level: str, msg: str) -> None:
            nonlocal issues
            if count > 0:
                results.append(f"  [{level}] media_assets: {msg}: {count}件")
                issues += 1
            else:
                results.append(f"  [PASS] media_assets: {msg.split('が')[0]}OK")

        _check(no_media_id, "WARN", "media_id が空の行")
        _check(no_ref_post_id, "WARN", "reference_post_id が空の行")
        _check(no_orig_url, "WARN", "original_media_url が空の行")
        _check(invalid_storage_provider, "WARN", "storage_provider が不正な行")
        _check(storage_url_fmt_err, "WARN", "storage_url がURL形式でない行")
        _check(invalid_type, "FAIL", "media_type が不正な行")
        _check(invalid_reuse, "WARN", "reuse_status が想定外の行")
        _check(invalid_risk, "WARN", "media_reuse_risk が想定外の行")
        _check(used_count_err, "WARN", "used_count が数値でない行")

    except Exception as e:
        results.append(f"  [FAIL] media_assets 取得エラー: {e}")
        issues += 1

    return issues


VALID_HOOK_STYLES = {"リスト型", "質問型", "暴露型", "体験談型", "断定型", "不明", ""}
VALID_CONTENT_ANGLES = {"体験談", "ノウハウ", "暴露", "共感", "質問", "その他", ""}
VALID_MEDIA_LABELS = {"動画あり", "画像あり", "メディアなし", ""}
VALID_TEXT_LENGTH_BUCKETS = {"短文(0-60字)", "中短文(61-120字)", "中文(121-180字)", "長文(181字以上)", ""}


def check_reference_post_scores(sheets, account_id: str | None, results: list) -> int:
    """reference_post_scores タブの整合性チェック（Phase 2.11 強化）。"""
    issues = 0
    try:
        rows = _get_tab_rows(sheets, "reference_post_scores", account_id)

        if not rows:
            results.append("  [PASS] reference_post_scores は空（初期状態として正常）")
            return 0

        results.append(f"  [PASS] reference_post_scores 取得OK: {len(rows)}件")

        no_ref_id = 0
        invalid_perf = 0
        invalid_buzz = 0
        invalid_percentile = 0
        invalid_hook_style = 0
        invalid_content_angle = 0
        invalid_media_label = 0
        invalid_text_bucket = 0
        negative_scores = 0

        for r in rows:
            if not str(r.get("reference_post_id", "")).strip():
                no_ref_id += 1

            perf = str(r.get("performance_score", "")).strip()
            if perf:
                try:
                    v = float(perf)
                    if v < 0:
                        negative_scores += 1
                except ValueError:
                    invalid_perf += 1

            buzz = str(r.get("buzz_score", "")).strip()
            if buzz:
                try:
                    v = float(buzz)
                    if not (0.0 <= v <= 100.0):
                        invalid_buzz += 1
                except ValueError:
                    invalid_buzz += 1

            for pct_col in ("account_percentile", "keyword_percentile"):
                pct = str(r.get(pct_col, "")).strip()
                if pct:
                    try:
                        v = float(pct)
                        if not (0.0 <= v <= 1.0):
                            invalid_percentile += 1
                    except ValueError:
                        invalid_percentile += 1

            hs = str(r.get("hook_style", "")).strip()
            if hs and hs not in VALID_HOOK_STYLES:
                invalid_hook_style += 1

            ca = str(r.get("content_angle", "")).strip()
            if ca and ca not in VALID_CONTENT_ANGLES:
                invalid_content_angle += 1

            ml = str(r.get("media_label", "")).strip()
            if ml and ml not in VALID_MEDIA_LABELS:
                invalid_media_label += 1

            tb = str(r.get("text_length_bucket", "")).strip()
            if tb and tb not in VALID_TEXT_LENGTH_BUCKETS:
                invalid_text_bucket += 1

        if no_ref_id > 0:
            results.append(f"  [WARN] reference_post_scores: reference_post_id が空の行: {no_ref_id}件")
            issues += 1
        else:
            results.append("  [PASS] reference_post_scores: reference_post_id OK")

        if invalid_perf > 0:
            results.append(f"  [FAIL] reference_post_scores: performance_score が数値でない行: {invalid_perf}件")
            issues += 1
        elif negative_scores > 0:
            results.append(f"  [WARN] reference_post_scores: performance_score が負の行: {negative_scores}件")
            issues += 1
        else:
            results.append("  [PASS] reference_post_scores: performance_score OK")

        if invalid_buzz > 0:
            results.append(f"  [FAIL] reference_post_scores: buzz_score が 0-100 範囲外の行: {invalid_buzz}件")
            issues += 1
        else:
            results.append("  [PASS] reference_post_scores: buzz_score OK")

        if invalid_percentile > 0:
            results.append(f"  [FAIL] reference_post_scores: percentile が 0.0-1.0 範囲外の行: {invalid_percentile}件")
            issues += 1
        else:
            results.append("  [PASS] reference_post_scores: percentile OK")

        if invalid_hook_style > 0:
            results.append(f"  [WARN] reference_post_scores: hook_style が未定義値の行: {invalid_hook_style}件")
            issues += 1
        else:
            results.append("  [PASS] reference_post_scores: hook_style OK")

        if invalid_content_angle > 0:
            results.append(f"  [WARN] reference_post_scores: content_angle が未定義値の行: {invalid_content_angle}件")
            issues += 1
        else:
            results.append("  [PASS] reference_post_scores: content_angle OK")

        if invalid_media_label > 0:
            results.append(f"  [WARN] reference_post_scores: media_label が未定義値の行: {invalid_media_label}件")
            issues += 1
        else:
            results.append("  [PASS] reference_post_scores: media_label OK")

        if invalid_text_bucket > 0:
            results.append(f"  [WARN] reference_post_scores: text_length_bucket が未定義値の行: {invalid_text_bucket}件")
            issues += 1
        else:
            results.append("  [PASS] reference_post_scores: text_length_bucket OK")

    except Exception as e:
        results.append(f"  [FAIL] reference_post_scores 取得エラー: {e}")
        issues += 1

    return issues


def check_generation_jobs(sheets, account_id: str | None, results: list) -> int:
    """generation_jobs タブの整合性チェック（Phase 2.13 強化）。"""
    issues = 0
    try:
        rows = _get_tab_rows(sheets, "generation_jobs", account_id)

        if not rows:
            results.append(f"  [PASS] generation_jobs は空（初期状態として正常）")
            return 0

        results.append(f"  [PASS] generation_jobs 取得OK: {len(rows)}件")

        invalid_mode = 0
        invalid_ref_ratio = 0
        invalid_orig_ratio = 0
        warn_x_chars = 0
        warn_th_chars = 0
        invalid_status = 0

        for r in rows:
            mode = str(r.get("generation_mode", "")).strip()
            if mode and mode not in VALID_GENERATION_MODES:
                invalid_mode += 1
            try:
                ref_ratio = float(r.get("reference_based_ratio", 0))
                if not (0.0 <= ref_ratio <= 1.0):
                    invalid_ref_ratio += 1
            except (TypeError, ValueError):
                if str(r.get("reference_based_ratio", "")).strip():
                    invalid_ref_ratio += 1
            try:
                orig_ratio = float(r.get("original_hypothesis_ratio", 0))
                if not (0.0 <= orig_ratio <= 1.0):
                    invalid_orig_ratio += 1
            except (TypeError, ValueError):
                if str(r.get("original_hypothesis_ratio", "")).strip():
                    invalid_orig_ratio += 1
            try:
                x_max = int(r.get("x_max_chars", 140))
                if x_max > 140:
                    warn_x_chars += 1
            except (TypeError, ValueError):
                pass
            try:
                th_max = int(r.get("threads_max_chars", 800))
                if th_max > 800:
                    warn_th_chars += 1
            except (TypeError, ValueError):
                pass
            job_status = str(r.get("status", "")).strip().lower()
            if job_status and job_status not in VALID_GENERATION_JOB_STATUSES:
                invalid_status += 1

        if invalid_mode > 0:
            results.append(f"  [FAIL] generation_jobs: generation_mode が不正な行: {invalid_mode}件")
            issues += 1
        else:
            results.append(f"  [PASS] generation_jobs: generation_mode OK")
        if invalid_ref_ratio > 0:
            results.append(f"  [FAIL] generation_jobs: reference_based_ratio が0〜1範囲外: {invalid_ref_ratio}件")
            issues += 1
        else:
            results.append(f"  [PASS] generation_jobs: reference_based_ratio OK")
        if invalid_orig_ratio > 0:
            results.append(f"  [FAIL] generation_jobs: original_hypothesis_ratio が0〜1範囲外: {invalid_orig_ratio}件")
            issues += 1
        else:
            results.append(f"  [PASS] generation_jobs: original_hypothesis_ratio OK")
        if invalid_status > 0:
            results.append(f"  [WARN] generation_jobs: status が想定外の行: {invalid_status}件 (pending/in_progress/done/failed)")
            issues += 1
        else:
            results.append(f"  [PASS] generation_jobs: status OK")
        if warn_x_chars > 0:
            results.append(f"  [WARN] generation_jobs: x_max_chars が140超の行: {warn_x_chars}件")
            issues += 1
        if warn_th_chars > 0:
            results.append(f"  [WARN] generation_jobs: threads_max_chars が800超の行: {warn_th_chars}件")
            issues += 1

        # Phase 2.15 追加フィールドサマリー
        done_count = sum(1 for r in rows if str(r.get("status", "")).lower() == "done")
        pending_count = sum(1 for r in rows if str(r.get("status", "")).lower() == "pending")
        if done_count or pending_count:
            results.append(f"  [PASS] generation_jobs: done={done_count}件 pending={pending_count}件")

    except Exception as e:
        results.append(f"  [FAIL] generation_jobs 取得エラー: {e}")
        issues += 1

    return issues


def main() -> None:
    parser = argparse.ArgumentParser(description="パイプラインデータ整合性チェック")
    parser.add_argument("--account-id", help="チェック対象アカウントID（省略時は全アカウント）")
    parser.add_argument("--fail-on-warn", action="store_true", help="WARN でも非ゼロ終了コードで終了")
    parser.add_argument("--mock", action="store_true", help="MockSheetsClient を使用（実データ検証不可）")
    args = parser.parse_args()

    print("=" * 60)
    print("  check_pipeline_integrity.py - パイプライン整合性チェック")
    print("=" * 60)

    if args.mock:
        print("[INFO] MockSheetsClient を使用します（実データ検証不可）")
        sheets = MockSheetsClient(dry_run=True)
    else:
        try:
            cfg = get_config()
        except ValueError as e:
            print(f"[ERROR] 認証情報が必要です: {e}")
            print("  → .env に SNS_MASTER_SHEET_ID と SA_JSON_BASE64 / GCP_SA_JSON を設定してください")
            print("  → モックで構造確認のみなら --mock を使ってください")
            sys.exit(1)
        sheets = SheetsClient(sheet_id=cfg["sheet_id"], sa_dict=cfg["sa_dict"], dry_run=True)

    account_label = args.account_id or "全アカウント"
    print(f"\n対象: {account_label}")
    print("-" * 60)

    all_results: list[str] = []
    total_issues = 0
    fail_count = 0

    # 各チェック実行
    checks = [
        ("drafts", check_drafts),
        ("social_derivatives", check_social_derivatives),
        ("queue", check_queue),
        ("logs", check_logs),
        ("posted_results", check_posted_results),
        # Phase 2.8 追加タブ
        ("media_assets", check_media_assets),
        ("reference_post_scores", check_reference_post_scores),
        ("generation_jobs", check_generation_jobs),
    ]

    for tab_name, check_fn in checks:
        print(f"\n[{tab_name}]")
        section_results: list[str] = []
        issues = check_fn(sheets, args.account_id, section_results)
        for line in section_results:
            print(line)
            all_results.append(line)
        total_issues += issues
        fail_count += sum(1 for r in section_results if r.strip().startswith("[FAIL]"))

    # サマリー
    print("\n" + "=" * 60)
    warn_count = sum(1 for r in all_results if r.strip().startswith("[WARN]"))
    pass_count = sum(1 for r in all_results if r.strip().startswith("[PASS]"))

    print(f"チェック結果サマリー:")
    print(f"  [PASS]: {pass_count}件")
    print(f"  [WARN]: {warn_count}件")
    print(f"  [FAIL]: {fail_count}件")
    print("=" * 60)

    if fail_count > 0:
        print("\n[RESULT] FAIL: データ整合性エラーがあります。上記ログを確認してください。")
        sys.exit(1)
    elif warn_count > 0 and args.fail_on_warn:
        print("\n[RESULT] WARN: 問題の可能性がある項目があります（--fail-on-warn 指定）。")
        sys.exit(1)
    elif warn_count > 0:
        print("\n[RESULT] WARN: 問題の可能性がある項目があります。内容を確認してください。")
        sys.exit(0)
    else:
        print("\n[RESULT] PASS: 全チェック正常です。")
        sys.exit(0)


if __name__ == "__main__":
    main()
