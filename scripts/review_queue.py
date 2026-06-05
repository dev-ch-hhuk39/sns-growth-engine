"""
review_queue.py - 投稿キュー確認ビューア（読み取り専用）

queue タブから WAITING_REVIEW 等のアイテムを取得し、
drafts / social_derivatives と JOIN して表示する。

X投稿の140字制限（安全マージンとして120字）、
Threads形式（フック + 2空行 + 本文）も確認する。

Phase 3-A 強化: DryRunPublisher による publish readiness チェックを追加。

使い方:
  # WAITING_REVIEW のキューを確認（実Sheets）
  python scripts/review_queue.py --account-id night_scout --status WAITING_REVIEW

  # プラットフォーム絞り込み
  python scripts/review_queue.py --account-id night_scout --platform x

  # 全ステータス表示
  python scripts/review_queue.py --account-id night_scout --status all

  # モック（データなし確認）
  python scripts/review_queue.py --mock

注意:
  - このスクリプトは読み取り専用です。データを変更しません。
  - X投稿は120字以下を推奨（140字制限に安全マージン）
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

from config_loader import get_config
from sheets_client import SheetsClient, MockSheetsClient
from publishers.factory import get_publisher

X_CHAR_WARN = 120
X_CHAR_LIMIT = 140


def _check_x_length(text: str) -> tuple[str, int]:
    """X投稿のテキスト長チェック。(status, length) を返す。"""
    length = len(text)
    if length > X_CHAR_LIMIT:
        return "FAIL", length
    elif length > X_CHAR_WARN:
        return "WARN", length
    return "OK", length


def _check_threads_format(text: str) -> tuple[str, str]:
    """Threads投稿のフォーマットチェック。(status, note) を返す。"""
    lines = text.split("\n")
    if len(lines) < 3:
        return "WARN", "フック+本文の区切りが不明確（2行以下）"
    has_blank = any(line.strip() == "" for line in lines[1:3])
    if not has_blank:
        return "WARN", "フックと本文の間に空行がない可能性があります"
    return "OK", "フォーマット正常"


def _truncate(text: str, length: int = 80) -> str:
    if len(text) <= length:
        return text
    return text[:length] + "..."


def fetch_queue(sheets, account_id: str | None, platform: str | None, status: str | None) -> list[dict]:
    """queue タブからアイテムを取得する。"""
    if hasattr(sheets, "_sh"):
        ws = sheets._sh.worksheet("queue")
        rows = ws.get_all_records()
    else:
        rows = getattr(sheets, "_queue", [])

    if account_id:
        rows = [r for r in rows if r.get("account_id") == account_id]
    if platform:
        rows = [r for r in rows if str(r.get("platform", "")).lower() == platform.lower()]
    if status:
        rows = [r for r in rows if str(r.get("status", "")).upper() == status.upper()]
    return [dict(r) for r in rows]


def fetch_draft(sheets, draft_id: str) -> dict:
    """draft_id に対応する draft を取得する。"""
    if hasattr(sheets, "_sh"):
        ws = sheets._sh.worksheet("drafts")
        for row in ws.get_all_records():
            if row.get("draft_id") == draft_id:
                return dict(row)
    else:
        for d in getattr(sheets, "_drafts", []):
            if d.get("draft_id") == draft_id:
                return dict(d)
    return {}


def fetch_derivative(sheets, draft_id: str, platform: str) -> dict:
    """draft_id + platform に対応する social_derivative を取得する。"""
    result = sheets.find_social_derivative(draft_id, platform)
    return result or {}


def _run_dry_publish_check(text: str, platform: str, account: dict,
                           derivative: dict, queue_item: dict) -> tuple[str, str]:
    """DryRunPublisher でテキストを検証し (tag, message) を返す。"""
    publisher = get_publisher(platform=platform, dry_run=True)
    result = publisher.publish(
        text,
        account=account,
        derivative=derivative,
        queue_item=queue_item,
        dry_run=True,
    )
    if result.success and "WARN" in result.message:
        return "[DRY/WARN]", result.message
    elif result.success:
        return "[DRY/OK] ", result.message
    else:
        return "[DRY/FAIL]", result.message


def display_queue_item(sheets, q: dict, draft: dict, derivative: dict) -> tuple[int, int]:
    """キューアイテムの詳細を表示する。(fail_count, warn_count) を返す。"""
    queue_id = q.get("queue_id", "?")
    draft_id = q.get("draft_id", "?")
    platform = str(q.get("platform", "?")).upper()
    status = q.get("status", "?")
    scheduled_at = q.get("scheduled_at", "未設定")
    priority = q.get("priority", "")

    print(f"\n{'─' * 55}")
    print(f"  queue_id    : {queue_id}")
    print(f"  draft_id    : {draft_id}")
    print(f"  platform    : {platform}")
    print(f"  status      : {status}")
    print(f"  scheduled_at: {scheduled_at}")
    if priority:
        print(f"  priority    : {priority}")

    fail_count = 0
    warn_count = 0

    # Phase 2.28: rights_review_required 警告
    rights_review_required = str(q.get("rights_review_required", "false")).lower()
    rights_status_q = str(q.get("rights_status", "")).lower()
    if rights_review_required == "true" or rights_status_q == "unknown":
        print(f"\n  [RIGHTS WARNING] rights_review_required=true")
        print(f"    rights_status : {rights_status_q or '(未設定)'}")
        media_reuse_risk_q = q.get("media_reuse_risk", "")
        source_video_url_q = q.get("source_video_url", "")
        source_time_range_q = q.get("source_time_range", "")
        if media_reuse_risk_q:
            print(f"    media_reuse_risk : {media_reuse_risk_q}")
        if source_video_url_q:
            print(f"    source_video_url : {_truncate(source_video_url_q, 80)}")
        if source_time_range_q:
            print(f"    source_time_range: {source_time_range_q}")
        print(f"    → video_clip_candidates タブで rights_status を allowed に更新後、")
        print(f"      approve_queue.py で --approve を実行できます")
        warn_count += 1

    # draft 情報
    if draft:
        title = draft.get("title", "")
        score = draft.get("score", "")
        pv_score = draft.get("pv_score", "")
        cv_score = draft.get("cv_score", "")
        brand_risk = draft.get("brand_risk_score", "")
        ai_review = draft.get("ai_review", "")
        cta_text = draft.get("cta_text", "")

        # risk summary
        try:
            risk_val = int(brand_risk or 0)
            risk_tag = "[HIGH_RISK]" if risk_val >= 30 else ("[MED_RISK]" if risk_val >= 15 else "[LOW_RISK]")
        except (ValueError, TypeError):
            risk_tag = "[RISK_?]"

        print(f"\n  [draft]")
        print(f"    title        : {_truncate(title, 60)}")
        print(f"    score        : {score}  (pv={pv_score} cv={cv_score} brand_risk={brand_risk} {risk_tag})")
        if ai_review:
            print(f"    ai_review    : {_truncate(ai_review, 80)}")
        if cta_text:
            print(f"    cta_text     : {_truncate(cta_text, 60)}")
    else:
        print(f"\n  [draft] 取得できませんでした (draft_id={draft_id})")

    # derivative 情報 + フォーマットチェック + DryRunPublisher チェック
    if derivative:
        text = str(derivative.get("text", ""))
        char_count = len(text)
        platform_lower = platform.lower()

        print(f"\n  [social_derivative]")
        print(f"    文字数       : {char_count}字")
        print(f"    text preview : {_truncate(text, 100)}")

        # フォーマットチェック
        if platform_lower == "x":
            chk_status, chk_len = _check_x_length(text)
            if chk_status == "FAIL":
                print(f"    [FAIL] X投稿が {chk_len}字でX制限({X_CHAR_LIMIT}字)を超えています")
                fail_count += 1
            elif chk_status == "WARN":
                print(f"    [WARN] X投稿が {chk_len}字で推奨上限({X_CHAR_WARN}字)を超えています")
                warn_count += 1
            else:
                print(f"    [OK]   X投稿文字数: {chk_len}字 (≤{X_CHAR_WARN}字)")
        elif platform_lower == "threads":
            fmt_status, fmt_note = _check_threads_format(text)
            if fmt_status == "WARN":
                print(f"    [WARN] Threads: {fmt_note}")
                warn_count += 1
            else:
                print(f"    [OK]   Threads: {fmt_note}")

        # DryRunPublisher による publish readiness チェック
        account = sheets.get_account(q.get("account_id", "")) or {}
        tag, msg = _run_dry_publish_check(
            text, platform_lower, account, derivative, q
        )

        # READY 推奨 / 非推奨 判定
        try:
            risk_val = int(draft.get("brand_risk_score", 0) if draft else 0)
        except (ValueError, TypeError):
            risk_val = 0
        reject_reasons: list[str] = []
        if "FAIL" in tag:
            reject_reasons.append("投稿テキストに問題あり（DRY/FAIL）")
        if risk_val >= 30:
            reject_reasons.append(f"brand_risk_score={risk_val} (高リスク ≥30)")
        if platform_lower == "x" and len(text) > X_CHAR_LIMIT:
            reject_reasons.append(f"X投稿 {len(text)}字 超過")
        readiness = "REJECT推奨" if reject_reasons else ("要確認" if "WARN" in tag else "READY推奨")

        print(f"\n  [publish readiness]")
        print(f"    {tag} {_truncate(msg, 100)}")
        print(f"    判定: {readiness}")
        for r in reject_reasons:
            print(f"      ⚠ {r}")
        acct_id = q.get("account_id", "")
        q_id = q.get("queue_id", "?")
        print(f"\n  [承認コマンド]")
        if readiness == "READY推奨":
            print(f"    python scripts/approve_queue.py --queue-id {q_id} --approve --reason \"内容確認済み\"")
        elif readiness == "REJECT推奨":
            print(f"    python scripts/approve_queue.py --queue-id {q_id} --reject --reason \"<理由を記載>\"")
        else:
            print(f"    python scripts/approve_queue.py --queue-id {q_id} --approve --reason \"<理由>\"  # 要確認")
            print(f"    python scripts/approve_queue.py --queue-id {q_id} --reject  --reason \"<理由>\"  # 要確認")
        print(f"    python scripts/publish_queue.py "
              f"--account-id {acct_id} "
              f"--platform {platform_lower} --status {status} --dry-run")
        # Phase 3-D: READY な X アイテムの実投稿コマンドを表示
        if status == "READY" and platform_lower == "x":
            print(f"\n  [X 実投稿コマンド（Phase 3-D）]")
            print(f"    ※ 投稿前に: PUBLISH_ENABLED=true かつ ALLOW_REAL_X_POST=true を .env に設定")
            print(f"    python scripts/publish_queue.py \\")
            print(f"      --account-id {acct_id} \\")
            print(f"      --platform x --status READY --limit 1 \\")
            print(f"      --confirm-real-post --queue-id {q_id} --max-real-posts 1")

        if "FAIL" in tag:
            fail_count += 1
        elif "WARN" in tag:
            warn_count += 1
    else:
        print(f"\n  [social_derivative] 取得できませんでした (draft_id={draft_id}, platform={platform})")
        warn_count += 1

    return fail_count, warn_count


def main() -> None:
    parser = argparse.ArgumentParser(description="投稿キュー確認ビューア（読み取り専用）")
    parser.add_argument("--account-id", help="対象アカウントID")
    parser.add_argument("--platform", help="対象プラットフォーム (x / threads)")
    parser.add_argument("--status", default="WAITING_REVIEW",
                        help="対象ステータス（デフォルト: WAITING_REVIEW）。'all' で全件表示")
    parser.add_argument("--mock", action="store_true", help="MockSheetsClient を使用")
    args = parser.parse_args()

    print("=" * 60)
    print("  review_queue.py - 投稿キュー確認（読み取り専用）")
    print("=" * 60)
    print("[INFO] このスクリプトはデータを変更しません")

    if args.mock:
        print("[INFO] MockSheetsClient を使用します（実データなし）")
        sheets = MockSheetsClient(dry_run=True)
    else:
        try:
            cfg = get_config()
        except ValueError as e:
            print(f"[ERROR] 認証情報が必要です: {e}")
            print("  → .env に SNS_MASTER_SHEET_ID と SA_JSON_BASE64 / GCP_SA_JSON を設定してください")
            sys.exit(1)
        sheets = SheetsClient(sheet_id=cfg["sheet_id"], sa_dict=cfg["sa_dict"], dry_run=True)

    status_filter = None if args.status.lower() == "all" else args.status.upper()
    account_label = args.account_id or "全アカウント"
    platform_label = args.platform or "全プラットフォーム"
    status_label = status_filter or "全ステータス"

    print(f"\n対象: {account_label} / {platform_label} / status={status_label}")

    queue_items = fetch_queue(sheets, args.account_id, args.platform, status_filter)

    if not queue_items:
        print(f"\n[INFO] 対象のキューアイテムが見つかりませんでした。")
        print(f"  → status=WAITING_REVIEW のアイテムがない場合は問題ありません。")
        sys.exit(0)

    print(f"\n{len(queue_items)}件のキューアイテムが見つかりました。")

    total_fail = 0
    total_warn = 0

    for q in queue_items:
        draft_id = q.get("draft_id", "")
        platform = str(q.get("platform", ""))
        draft = fetch_draft(sheets, draft_id) if draft_id else {}
        derivative = fetch_derivative(sheets, draft_id, platform) if draft_id and platform else {}
        fc, wc = display_queue_item(sheets, q, draft, derivative)
        total_fail += fc
        total_warn += wc

    print(f"\n{'─' * 55}")
    print(f"合計: {len(queue_items)}件")
    if total_fail > 0:
        print(f"  [FAIL] 問題あり: {total_fail}件 — 修正が必要です")
    if total_warn > 0:
        print(f"  [WARN] 確認推奨: {total_warn}件")
    if total_fail == 0 and total_warn == 0:
        print(f"  [OK]   全アイテムのフォーマット・publishチェック通過")
    print()
    print("  → publish_queue.py で dry-run 実行確認:")
    acct_flag = f"--account-id {args.account_id}" if args.account_id else ""
    plat_flag = f"--platform {args.platform}" if args.platform else "--platforms x,threads"
    print(f"     python scripts/publish_queue.py {acct_flag} {plat_flag} --status {args.status.upper() if args.status.lower() != 'all' else 'WAITING_REVIEW'} --dry-run")
    print("=" * 60)

    sys.exit(1 if total_fail > 0 else 0)


if __name__ == "__main__":
    main()
