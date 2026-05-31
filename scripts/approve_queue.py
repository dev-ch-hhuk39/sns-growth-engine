"""
approve_queue.py - キュー承認/却下 CLI（Phase 3-B）

queue の WAITING_REVIEW 投稿を人間の判断で READY / REJECTED に変更する。

動作保証:
  - SNS 本番投稿は絶対にしない
  - posted_results には書き込まない
  - PUBLISH_ENABLED=false を維持
  - queue.status の変更は --approve / --reject / --status フラグが明示された場合のみ
  - --reason は必須（変更時）
  - --dry-run 時は Sheets を変更しない
  - 承認/却下ログを logs タブに残す

使い方:
  # 一覧確認（読み取り専用）
  python scripts/approve_queue.py --account-id night_scout --status WAITING_REVIEW --list

  # 1件承認（WAITING_REVIEW → READY）
  python scripts/approve_queue.py --queue-id q-xxxx --approve --reason "内容確認済み"

  # 1件却下（WAITING_REVIEW → REJECTED）
  python scripts/approve_queue.py --queue-id q-xxxx --reject --reason "表現が強すぎる"

  # ステータス直接指定
  python scripts/approve_queue.py --queue-id q-xxxx --status READY --reason "手動承認"

  # dry-run（変更確認のみ、Sheets は変更しない）
  python scripts/approve_queue.py --queue-id q-xxxx --approve --reason "テスト" --dry-run
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
from generation.approval_scorer import detect_forbidden_keywords
from seeds import ACCOUNT_FORBIDDEN_KEYWORDS
from sheets_client import SheetsClient, MockSheetsClient, make_client
from publishers.dry_run import DryRunPublisher, X_CHAR_WARN, X_CHAR_LIMIT

ALLOWED_NEW_STATUSES = {"READY", "REJECTED"}


def _truncate(text: str, n: int = 80) -> str:
    return text[:n] + "..." if len(text) > n else text


def _risk_tag(brand_risk: str) -> str:
    try:
        v = int(brand_risk or 0)
        if v >= 30:
            return "[HIGH_RISK]"
        elif v >= 15:
            return "[MED_RISK]"
        return "[LOW_RISK]"
    except (ValueError, TypeError):
        return "[RISK_?]"


def _readiness_verdict(platform: str, text: str, brand_risk: str) -> tuple[str, list[str]]:
    """READY 推奨/非推奨の判定。(verdict, reasons) を返す。"""
    reasons: list[str] = []
    try:
        risk_val = int(brand_risk or 0)
    except (ValueError, TypeError):
        risk_val = 0

    if risk_val >= 30:
        reasons.append(f"brand_risk_score={risk_val} (高リスク, ≥30)")

    plat = platform.lower()
    if plat == "x":
        length = len(text)
        if length > X_CHAR_LIMIT:
            reasons.append(f"X投稿が{length}字でX制限({X_CHAR_LIMIT}字)を超えています")
        elif length > X_CHAR_WARN:
            reasons.append(f"X投稿が{length}字で推奨上限({X_CHAR_WARN}字)を超えています")
    elif plat == "threads":
        lines = text.split("\n")
        has_blank = len(lines) >= 2 and any(l.strip() == "" for l in lines[1:3])
        if not has_blank:
            reasons.append("Threadsフォーマット: フックと本文の間に空行がない可能性あり")

    if not text.strip():
        reasons.append("テキストが空です")
        return "REJECT推奨", reasons

    if reasons:
        return "要確認", reasons
    return "READY推奨", reasons


def display_queue_detail(sheets, q: dict) -> None:
    """承認前に対象投稿の詳細を表示する。"""
    queue_id = q.get("queue_id", "?")
    draft_id = q.get("draft_id", "?")
    platform = str(q.get("platform", "?")).upper()
    current_status = q.get("status", "?")
    scheduled_at = q.get("scheduled_at", "未設定")

    print(f"\n{'─' * 55}")
    print(f"  queue_id    : {queue_id}")
    print(f"  draft_id    : {draft_id}")
    print(f"  platform    : {platform}")
    print(f"  status      : {current_status}")
    print(f"  scheduled_at: {scheduled_at}")

    # draft 取得
    draft: dict = {}
    if hasattr(sheets, "_sh"):
        ws = sheets._sh.worksheet("drafts")
        for row in ws.get_all_records():
            if row.get("draft_id") == draft_id:
                draft = dict(row)
                break
    else:
        for d in getattr(sheets, "_drafts", []):
            if d.get("draft_id") == draft_id:
                draft = dict(d)
                break

    if draft:
        title = draft.get("title", "")
        score = draft.get("score", "")
        pv = draft.get("pv_score", "")
        cv = draft.get("cv_score", "")
        brand_risk = draft.get("brand_risk_score", "")
        ai_review = draft.get("ai_review", "")
        cta = draft.get("cta_text", "")
        print(f"\n  [draft]")
        print(f"    title      : {_truncate(title, 60)}")
        print(f"    score      : {score}  (pv={pv} cv={cv} brand_risk={brand_risk} {_risk_tag(brand_risk)})")
        if ai_review:
            print(f"    ai_review  : {_truncate(ai_review, 80)}")
        if cta:
            print(f"    cta_text   : {_truncate(cta, 60)}")
    else:
        print(f"\n  [draft] 取得できませんでした")

    # derivative 取得
    derivative = sheets.find_social_derivative(draft_id, platform.lower())
    if derivative:
        text = str(derivative.get("text", ""))
        char_count = len(text)
        brand_risk = draft.get("brand_risk_score", "") if draft else ""
        verdict, reasons = _readiness_verdict(platform.lower(), text, brand_risk)

        print(f"\n  [投稿テキスト]")
        print(f"    文字数   : {char_count}字")
        print(f"    内容     : {_truncate(text, 120)}")

        # publish readiness
        pub = DryRunPublisher()
        result = pub.publish(
            text,
            account={"account_id": q.get("account_id", "")},
            derivative=derivative,
            queue_item=q,
            dry_run=True,
        )
        tag = "[DRY/OK] " if (result.success and "WARN" not in result.message) else \
              "[DRY/WARN]" if result.success else "[DRY/FAIL]"
        print(f"\n  [publish readiness]")
        print(f"    {tag} {_truncate(result.message, 90)}")
        print(f"    判定     : {verdict}")
        for r in reasons:
            print(f"      ⚠ {r}")
    else:
        print(f"\n  [投稿テキスト] 取得できませんでした")


def _log_approval(sheets, queue_id: str, account_id: str, platform: str,
                  old_status: str, new_status: str, reason: str,
                  dry_run: bool) -> None:
    """承認/却下ログを logs タブに記録する。"""
    action = "queue_approved" if new_status == "READY" else \
             "queue_rejected" if new_status == "REJECTED" else "queue_status_changed"
    dry_tag = " [DRY_RUN]" if dry_run else ""
    details = (
        f"queue_id={queue_id} platform={platform} "
        f"{old_status}→{new_status} reason={reason!r}{dry_tag}"
    )
    sheets.log(
        operation=action,
        status="OK",
        message=f"{action}: queue_id={queue_id} {old_status}→{new_status}{dry_tag}",
        account_id=account_id,
        details=details,
        level="INFO",
    )


def cmd_list(sheets, account_id: str | None, status: str, platform: str | None) -> None:
    """--list: queue 一覧を読み取り専用で表示する。"""
    items = sheets.get_queue_items(account_id=account_id, platform=platform, status=status)
    label = account_id or "全アカウント"
    plat_label = platform or "全プラットフォーム"
    print(f"\n対象: {label} / {plat_label} / status={status}")
    if not items:
        print(f"\n[INFO] 対象キューアイテムなし")
        return
    print(f"\n{len(items)}件:")
    for q in items:
        platform_q = str(q.get("platform", "")).upper()
        draft_id = q.get("draft_id", "")
        derivative = sheets.find_social_derivative(draft_id, platform_q.lower()) or {}
        text = str(derivative.get("text", ""))
        char_info = f"{len(text)}字" if text else "text不明"
        print(
            f"  {q.get('queue_id')} | {platform_q} | {q.get('status')} | {char_info} | "
            f"scheduled={q.get('scheduled_at', '?')}"
        )
    print(f"\n承認コマンド例:")
    print(f"  python scripts/approve_queue.py --queue-id <queue_id> --approve --reason \"理由\"")
    print(f"  python scripts/approve_queue.py --queue-id <queue_id> --reject  --reason \"理由\"")


def cmd_approve(sheets, queue_id: str, new_status: str, reason: str, dry_run: bool) -> int:
    """--approve / --reject / --status: 1件の status を変更する。"""
    q = sheets.get_queue_item(queue_id)
    if q is None:
        print(f"[ERROR] queue_id={queue_id!r} が見つかりません")
        return 1

    old_status = str(q.get("status", ""))
    account_id = q.get("account_id", "")
    platform = str(q.get("platform", ""))

    display_queue_detail(sheets, q)

    print(f"\n{'─' * 55}")
    print(f"  変更内容: {old_status} → {new_status}")
    print(f"  reason  : {reason}")
    if dry_run:
        print(f"  [DRY-RUN] Sheets への書き込みはスキップします")

    # Phase 2.17: READY への変更前にテーマガード実行
    if new_status == "READY":
        draft_id = q.get("draft_id", "")
        derivative = sheets.find_social_derivative(draft_id, platform.lower()) if draft_id else None
        if derivative:
            deriv_text = str(derivative.get("text", ""))
        else:
            deriv_text = ""
        forbidden = ACCOUNT_FORBIDDEN_KEYWORDS.get(account_id, [])
        if forbidden and deriv_text:
            hits = detect_forbidden_keywords(deriv_text, forbidden)
            if hits:
                print(f"\n[REJECTED] content_theme_guard: forbidden_keywords detected: {hits}")
                print(f"  → READY への変更を拒否します。--reject で明示的に却下してください。")
                return 1

    if dry_run:
        _log_approval(sheets, queue_id, account_id, platform,
                      old_status, new_status, reason, dry_run=True)
        print(f"\n[DRY-RUN] queue_id={queue_id} の status を {new_status} に変更します（実行はしません）")
        return 0

    # 実際に更新
    sheets.update_queue_item(queue_id, status=new_status)
    _log_approval(sheets, queue_id, account_id, platform,
                  old_status, new_status, reason, dry_run=False)

    print(f"\n[OK] queue_id={queue_id} の status を {new_status} に変更しました")
    print(f"     ※ SNS 本番投稿は行っていません")
    print(f"     ※ posted_results への書き込みは行っていません")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="キュー承認/却下 CLI（Phase 3-B）")
    parser.add_argument("--queue-id", help="対象 queue_id（変更時必須）")
    parser.add_argument("--account-id", help="対象アカウントID（--list 時に使用）")
    parser.add_argument("--platform", help="プラットフォーム絞り込み（--list 時）")
    parser.add_argument("--approve", action="store_true",
                        help="status を READY に変更")
    parser.add_argument("--reject", action="store_true",
                        help="status を REJECTED に変更")
    parser.add_argument("--status",
                        help="status を直接指定（READY / REJECTED / WAITING_REVIEW）")
    parser.add_argument("--reason", default="",
                        help="承認/却下の理由（変更時必須）")
    parser.add_argument("--list", action="store_true",
                        help="一覧表示のみ（読み取り専用）")
    parser.add_argument("--dry-run", action="store_true",
                        help="変更内容を表示するが Sheets は変更しない")
    parser.add_argument("--use-sheets", action="store_true",
                        help="実 SheetsClient を使用（認証情報必須）")
    parser.add_argument("--mock", action="store_true",
                        help="MockSheetsClient を使用")
    args = parser.parse_args()

    print("=" * 60)
    print("  approve_queue.py - キュー承認/却下（Phase 3-B）")
    print("=" * 60)
    print("[INFO] SNS 本番投稿は行いません")
    print("[INFO] posted_results への書き込みは行いません")

    # ---- フラグ検証 ----
    action_flags = [args.approve, args.reject, bool(args.status and not args.list)]
    if sum(action_flags) > 1:
        print("[ERROR] --approve / --reject / --status は同時に指定できません")
        sys.exit(1)

    is_change_action = args.approve or args.reject or (args.status and not args.list)

    if is_change_action and not args.queue_id:
        print("[ERROR] 変更操作には --queue-id が必要です")
        sys.exit(1)

    if is_change_action and not args.reason.strip():
        print("[ERROR] --reason は必須です（承認/却下の理由を記載してください）")
        sys.exit(1)

    # 変更先ステータス決定
    if args.approve:
        new_status = "READY"
    elif args.reject:
        new_status = "REJECTED"
    elif args.status and not args.list:
        new_status = args.status.upper()
        if new_status not in ALLOWED_NEW_STATUSES:
            print(f"[ERROR] --status に指定できる値: {ALLOWED_NEW_STATUSES}")
            sys.exit(1)
    else:
        new_status = ""

    # ---- Sheets クライアント初期化 ----
    if args.mock:
        sheets = MockSheetsClient(dry_run=args.dry_run)
        print("[INFO] MockSheetsClient を使用します")
    elif args.use_sheets or (not args.mock and is_change_action and not args.dry_run):
        try:
            cfg = get_config()
        except ValueError as e:
            if args.dry_run:
                cfg = get_config_partial()
                sheets = make_client(cfg, dry_run=True, force_mock=False)
            else:
                print(f"[ERROR] 認証情報が必要です: {e}")
                sys.exit(1)
        else:
            dry_run_sheets = args.dry_run
            sheets = SheetsClient(
                sheet_id=cfg["sheet_id"],
                sa_dict=cfg["sa_dict"],
                dry_run=dry_run_sheets,
            )
    else:
        cfg = get_config_partial()
        sheets = make_client(cfg, dry_run=True, force_mock=False)

    if args.dry_run:
        print("[INFO] DRY-RUN: Sheets への書き込みはスキップします")

    # ---- コマンド実行 ----
    if args.list:
        list_status = args.status or "WAITING_REVIEW"
        cmd_list(sheets, args.account_id, list_status, args.platform)
        sys.exit(0)

    if is_change_action:
        rc = cmd_approve(sheets, args.queue_id, new_status, args.reason, args.dry_run)
        sys.exit(rc)

    # どのフラグも指定されていない場合はヘルプ表示
    print("\n[INFO] フラグが未指定です。--list で一覧確認、--approve / --reject で変更できます。")
    parser.print_help()
    sys.exit(0)


if __name__ == "__main__":
    main()
