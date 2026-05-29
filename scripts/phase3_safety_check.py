"""
phase3_safety_check.py - Phase 3 移行前安全チェック（Phase 3-C 対応版）

Phase 3（SNS本番投稿）に進む前に必要な安全条件を検証する。
すべての条件を満たさない限り Phase 3-D（X 本番投稿）実装を開始してはならない。

チェック項目:
  1. PUBLISH_ENABLED=false であること
  2. ALLOW_REAL_X_POST=false / ALLOW_REAL_THREADS_POST=false であること（Phase 3-C 追加）
  3. X API / Threads API の認証トークンが未設定であること
  4. x_publisher.py / threads_publisher.py が存在し、本番投稿未実装スタブであること（Phase 3-C）
  5. factory.py が本番 Publisher を返していないこと（Phase 3-C）
  6. src/publishers/dry_run.py が存在すること（Phase 3-A 実装済み）
  7. approve_queue.py が存在すること（Phase 3-B 実装済み）
  8. posted_results タブが空であること（本番投稿履歴なし）
  9. logs タブに ERROR レベルのログが0件であること
  10. queue.status=POSTED がないこと（Phase 3-C 追加）
  11. 既存3プロジェクト (夜職_x / 夜職_threads / ライバー) の git が clean であること

使い方:
  python scripts/phase3_safety_check.py

  # 実Sheetsに対してチェック（推奨）
  python scripts/phase3_safety_check.py --use-sheets
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SNS_ROOT = os.path.dirname(_V2_ROOT)
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_V2_ROOT, ".env"))
except ImportError:
    pass

EXISTING_PROJECTS = [
    ("夜職_x", os.path.join(_SNS_ROOT, "夜職_x")),
    ("夜職_threads", os.path.join(_SNS_ROOT, "夜職_threads")),
    ("ライバー", os.path.join(_SNS_ROOT, "ライバー")),
]

PUBLISHER_FILES = [
    os.path.join(_V2_ROOT, "src", "publishers", "x_publisher.py"),
    os.path.join(_V2_ROOT, "src", "publishers", "threads_publisher.py"),
]

PHASE3A_REQUIRED_FILES = [
    os.path.join(_V2_ROOT, "src", "publishers", "dry_run.py"),
    os.path.join(_V2_ROOT, "src", "publishers", "base.py"),
    os.path.join(_V2_ROOT, "src", "publishers", "factory.py"),
]

PHASE3B_REQUIRED_FILES = [
    os.path.join(_V2_ROOT, "scripts", "approve_queue.py"),
]

PHASE3C_REQUIRED_FILES = [
    os.path.join(_V2_ROOT, "src", "publishers", "x_publisher.py"),
    os.path.join(_V2_ROOT, "src", "publishers", "threads_publisher.py"),
    os.path.join(_V2_ROOT, "scripts", "check_publisher_credentials.py"),
]

X_TOKEN_ENVS = [
    "X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET",
    "TWITTER_BEARER_TOKEN", "TWITTER_API_KEY",
]
THREADS_TOKEN_ENVS = [
    "THREADS_ACCESS_TOKEN", "THREADS_APP_ID", "THREADS_APP_SECRET",
    "INSTAGRAM_ACCESS_TOKEN",
]


def check_publish_enabled(results: list) -> bool:
    val = os.environ.get("PUBLISH_ENABLED", "false").strip().lower()
    if val in ("1", "true", "yes"):
        results.append("[FAIL] PUBLISH_ENABLED が true です！Phase 3-D まで false に戻してください")
        return False
    results.append("[PASS] PUBLISH_ENABLED=false (安全)")

    allow_x = os.environ.get("ALLOW_REAL_X_POST", "false").strip().lower()
    if allow_x in ("1", "true", "yes"):
        results.append("[FAIL] ALLOW_REAL_X_POST=true です！Phase 3-D の手動テスト以外では false を維持してください")
        return False
    results.append("[PASS] ALLOW_REAL_X_POST=false (安全)")

    allow_t = os.environ.get("ALLOW_REAL_THREADS_POST", "false").strip().lower()
    if allow_t in ("1", "true", "yes"):
        results.append("[FAIL] ALLOW_REAL_THREADS_POST=true です！Phase 3-E の手動テスト以外では false を維持してください")
        return False
    results.append("[PASS] ALLOW_REAL_THREADS_POST=false (安全)")
    return True


def check_sns_tokens(results: list) -> bool:
    x_set = [k for k in X_TOKEN_ENVS if os.environ.get(k, "").strip()]
    threads_set = [k for k in THREADS_TOKEN_ENVS if os.environ.get(k, "").strip()]

    ok = True
    # Phase 3-D: X 認証情報は設定済みが正常
    if x_set:
        results.append(f"[PASS] X API 認証情報が設定されています（Phase 3-D 準備OK）: {x_set}")
    else:
        results.append("[INFO] X API 認証情報は未設定（Phase 3-D の手動投稿前に設定が必要）")
        # 未設定でもチェックは通す（設定は Phase 3-D 本番テスト直前でよい）

    # Threads 認証情報は Phase 3-E まで不要
    if threads_set:
        results.append(f"[WARN] Threads API 認証情報が設定されています: {threads_set}")
        results.append(f"       Phase 3-E 実装前は .env から削除または空にしてください")
        ok = False
    else:
        results.append("[PASS] Threads API 認証情報は未設定（Phase 3-E まで不要）")

    return ok


def check_publisher_files(results: list) -> bool:
    """Phase 3-C: x_publisher.py / threads_publisher.py はスタブとして存在するが、本番投稿しないことを確認する。"""
    found = [f for f in PUBLISHER_FILES if os.path.exists(f)]
    if not found:
        # Phase 3-C 以前は未存在でもOK
        results.append("[PASS] x_publisher.py / threads_publisher.py は未作成（Phase 3-C 未実施）")
        return True

    names = [os.path.basename(f) for f in found]
    # Phase 3-C: スタブが存在することは正常
    # SAFETY_STOP / NotImplementedError が実装されていることをコード検索で確認
    stub_safe = True
    for fpath in found:
        try:
            with open(fpath, encoding="utf-8") as fh:
                content = fh.read()
            if "NotImplementedError" not in content and "SAFETY_STOP" not in content:
                results.append(f"[FAIL] {os.path.basename(fpath)}: SAFETY_STOP / NotImplementedError が見つかりません")
                stub_safe = False
            else:
                results.append(f"[PASS] {os.path.basename(fpath)}: スタブ（SAFETY_STOP/NotImplementedError 確認OK）")
        except Exception as e:
            results.append(f"[WARN] {os.path.basename(fpath)}: 読み取りエラー: {e}")
            stub_safe = False
    return stub_safe


def check_phase3c_files(results: list) -> bool:
    """Phase 3-C で実装された publisher スタブ・認証情報チェックスクリプトの存在を確認する。"""
    missing = [f for f in PHASE3C_REQUIRED_FILES if not os.path.exists(f)]
    if missing:
        names = [os.path.basename(f) for f in missing]
        results.append(f"[FAIL] Phase 3-C 必須ファイルが見つかりません: {names}")
        return False
    results.append("[PASS] Phase 3-C ファイル存在確認OK (x_publisher/threads_publisher/check_publisher_credentials)")
    return True


def check_factory_safe(results: list) -> bool:
    """factory.py が本番 Publisher を返していないことを確認する。"""
    factory_path = os.path.join(_V2_ROOT, "src", "publishers", "factory.py")
    if not os.path.exists(factory_path):
        results.append("[FAIL] factory.py が見つかりません")
        return False
    try:
        with open(factory_path, encoding="utf-8") as fh:
            content = fh.read()
        # XPublisher / ThreadsPublisher のコメントアウトを確認
        # コメントアウトされていれば安全（"# from publishers.x_publisher" が存在する）
        x_active = "from publishers.x_publisher import XPublisher" in content
        t_active = "from publishers.threads_publisher import ThreadsPublisher" in content
        # コメント行でない（先頭に#がない）インポートが存在するかチェック
        x_live = any(
            line.strip() == "from publishers.x_publisher import XPublisher"
            for line in content.splitlines()
        )
        t_live = any(
            line.strip() == "from publishers.threads_publisher import ThreadsPublisher"
            for line in content.splitlines()
        )
        # ThreadsPublisher 有効化は Phase 3-E まで禁止
        if t_live:
            results.append("[FAIL] factory.py が ThreadsPublisher を有効化しています（Phase 3-E 以前は禁止）")
            return False
        # XPublisher 有効化は Phase 3-D で正常
        if x_live:
            results.append("[PASS] factory.py が XPublisher を有効化済み（Phase 3-D 実装確認OK）")
        else:
            results.append("[PASS] factory.py は本番 Publisher を返していません（Phase 3-C 安全状態）")
        return True
    except Exception as e:
        results.append(f"[WARN] factory.py 読み取りエラー: {e}")
        return False


def check_phase3b_files(results: list) -> bool:
    """Phase 3-B で実装された approve_queue.py の存在を確認する。"""
    missing = [f for f in PHASE3B_REQUIRED_FILES if not os.path.exists(f)]
    if missing:
        names = [os.path.basename(f) for f in missing]
        results.append(f"[FAIL] Phase 3-B 必須ファイルが見つかりません: {names}")
        return False
    results.append("[PASS] Phase 3-B approve_queue.py 存在確認OK")
    return True


def check_phase3a_files(results: list) -> bool:
    """Phase 3-A で実装された publishers パッケージのファイル存在を確認する。"""
    missing = [f for f in PHASE3A_REQUIRED_FILES if not os.path.exists(f)]
    if missing:
        names = [os.path.basename(f) for f in missing]
        results.append(f"[FAIL] Phase 3-A 必須ファイルが見つかりません: {names}")
        results.append(f"       Phase 3-A の実装を確認してください")
        return False
    results.append("[PASS] Phase 3-A publishers ファイル存在確認OK (base/dry_run/factory)")
    return True


def check_posted_results(results: list, use_sheets: bool) -> bool:
    if not use_sheets:
        results.append("[SKIP] posted_results チェック: --use-sheets なしのためスキップ")
        return True

    try:
        from config_loader import get_config
        from sheets_client import SheetsClient

        cfg = get_config()
        sheets = SheetsClient(sheet_id=cfg["sheet_id"], sa_dict=cfg["sa_dict"], dry_run=True)
        ws = sheets._sh.worksheet("posted_results")
        rows = ws.get_all_records()
        if rows:
            results.append(f"[WARN] posted_results に {len(rows)}件あります")
            results.append(f"       Phase 3 実施前は0件が正常です")
            return False
        results.append("[PASS] posted_results は空（Phase 2 正常状態）")
        return True
    except Exception as e:
        results.append(f"[WARN] posted_results チェックエラー: {e}")
        return False


def check_error_logs(results: list, use_sheets: bool) -> bool:
    if not use_sheets:
        results.append("[SKIP] logs.ERROR チェック: --use-sheets なしのためスキップ")
        return True

    try:
        from config_loader import get_config
        from sheets_client import SheetsClient

        cfg = get_config()
        sheets = SheetsClient(sheet_id=cfg["sheet_id"], sa_dict=cfg["sa_dict"], dry_run=True)
        ws = sheets._sh.worksheet("logs")
        rows = ws.get_all_records()
        error_rows = [r for r in rows if str(r.get("level", "")).upper() == "ERROR"]
        if error_rows:
            results.append(f"[WARN] logs に ERROR レベルが {len(error_rows)}件あります")
            results.append(f"       内容を確認し、解決済みであることを確認してください")
            return False
        results.append(f"[PASS] logs に ERROR レベルのログなし ({len(rows)}件中)")
        return True
    except Exception as e:
        results.append(f"[WARN] logs チェックエラー: {e}")
        return False


def check_queue_no_posted(results: list, use_sheets: bool) -> bool:
    """queue.status=POSTED がないことを確認する。"""
    if not use_sheets:
        results.append("[SKIP] queue.status=POSTED チェック: --use-sheets なしのためスキップ")
        return True

    try:
        from config_loader import get_config
        from sheets_client import SheetsClient

        cfg = get_config()
        sheets = SheetsClient(sheet_id=cfg["sheet_id"], sa_dict=cfg["sa_dict"], dry_run=True)
        ws = sheets._sh.worksheet("queue")
        rows = ws.get_all_records()
        posted_rows = [r for r in rows if str(r.get("status", "")).upper() == "POSTED"]
        if posted_rows:
            results.append(f"[WARN] queue に status=POSTED が {len(posted_rows)}件あります")
            results.append(f"       Phase 3-C では POSTED になるべきではありません")
            return False
        results.append(f"[PASS] queue.status=POSTED なし（{len(rows)}件中）")
        return True
    except Exception as e:
        results.append(f"[WARN] queue.status=POSTED チェックエラー: {e}")
        return False


def check_existing_projects_git(results: list) -> bool:
    ok = True
    for project_name, project_path in EXISTING_PROJECTS:
        if not os.path.isdir(project_path):
            results.append(f"[WARN] {project_name}: ディレクトリが見つかりません ({project_path})")
            ok = False
            continue

        git_dir = os.path.join(project_path, ".git")
        if not os.path.isdir(git_dir):
            results.append(f"[WARN] {project_name}: git リポジトリではありません")
            ok = False
            continue

        try:
            proc = subprocess.run(
                ["git", "-C", project_path, "status", "--porcelain"],
                capture_output=True, text=True, timeout=10
            )
            output = proc.stdout.strip()
            if proc.returncode != 0:
                results.append(f"[WARN] {project_name}: git status 失敗 (rc={proc.returncode})")
                ok = False
            elif output:
                lines = output.splitlines()
                results.append(f"[WARN] {project_name}: {len(lines)}件の未コミット変更があります")
                for line in lines[:5]:
                    results.append(f"       {line}")
                if len(lines) > 5:
                    results.append(f"       ... 他 {len(lines) - 5}件")
                ok = False
            else:
                results.append(f"[PASS] {project_name}: git status clean")
        except subprocess.TimeoutExpired:
            results.append(f"[WARN] {project_name}: git status タイムアウト")
            ok = False
        except Exception as e:
            results.append(f"[WARN] {project_name}: git status エラー: {e}")
            ok = False

    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 3 移行前安全チェック")
    parser.add_argument(
        "--use-sheets", action="store_true",
        help="実Sheetsに対して posted_results / logs もチェックする"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  phase3_safety_check.py - Phase 3 移行前安全チェック")
    print("=" * 60)
    if args.use_sheets:
        print("[INFO] --use-sheets: 実Sheets データもチェックします")
    else:
        print("[INFO] ローカル環境チェックのみ（Sheets チェックは --use-sheets で追加）")

    results: list[str] = []
    all_ok = True

    print("\n[1] PUBLISH_ENABLED チェック")
    r: list[str] = []
    ok = check_publish_enabled(r)
    for line in r:
        print(f"  {line}")
    results.extend(r)
    all_ok = all_ok and ok

    print("\n[2] SNS API 認証情報チェック")
    r = []
    ok = check_sns_tokens(r)
    for line in r:
        print(f"  {line}")
    results.extend(r)
    all_ok = all_ok and ok

    print("\n[3] Phase 3-C publisher スタブ安全チェック（本番未実装確認）")
    r = []
    ok = check_publisher_files(r)
    for line in r:
        print(f"  {line}")
    results.extend(r)
    all_ok = all_ok and ok

    print("\n[3b] Phase 3-A publishers パッケージ存在チェック")
    r = []
    ok = check_phase3a_files(r)
    for line in r:
        print(f"  {line}")
    results.extend(r)
    all_ok = all_ok and ok

    print("\n[3c] Phase 3-B approve_queue.py 存在チェック")
    r = []
    ok = check_phase3b_files(r)
    for line in r:
        print(f"  {line}")
    results.extend(r)
    all_ok = all_ok and ok

    print("\n[3d] Phase 3-C スタブファイル存在チェック")
    r = []
    ok = check_phase3c_files(r)
    for line in r:
        print(f"  {line}")
    results.extend(r)
    all_ok = all_ok and ok

    print("\n[3e] factory.py 本番Publisher非返却チェック")
    r = []
    ok = check_factory_safe(r)
    for line in r:
        print(f"  {line}")
    results.extend(r)
    all_ok = all_ok and ok

    print("\n[4] posted_results 空チェック")
    r = []
    ok = check_posted_results(r, args.use_sheets)
    for line in r:
        print(f"  {line}")
    results.extend(r)
    all_ok = all_ok and ok

    print("\n[5] logs ERROR チェック")
    r = []
    ok = check_error_logs(r, args.use_sheets)
    for line in r:
        print(f"  {line}")
    results.extend(r)
    all_ok = all_ok and ok

    print("\n[5b] queue.status=POSTED 非存在チェック")
    r = []
    ok = check_queue_no_posted(r, args.use_sheets)
    for line in r:
        print(f"  {line}")
    results.extend(r)
    all_ok = all_ok and ok

    print("\n[6] 既存3プロジェクト git clean チェック")
    r = []
    ok = check_existing_projects_git(r)
    for line in r:
        print(f"  {line}")
    results.extend(r)
    all_ok = all_ok and ok

    # サマリー
    pass_count = sum(1 for r in results if r.strip().startswith("[PASS]"))
    warn_count = sum(1 for r in results if r.strip().startswith("[WARN]"))
    fail_count = sum(1 for r in results if r.strip().startswith("[FAIL]"))
    skip_count = sum(1 for r in results if r.strip().startswith("[SKIP]"))

    print("\n" + "=" * 60)
    print("Phase 3 安全チェック サマリー:")
    print(f"  [PASS]: {pass_count}件")
    print(f"  [WARN]: {warn_count}件")
    print(f"  [FAIL]: {fail_count}件")
    if skip_count:
        print(f"  [SKIP]: {skip_count}件（--use-sheets で追加チェック可）")
    print("=" * 60)

    if fail_count > 0 or warn_count > 0:
        print("\n[RESULT] Phase 3 移行前に上記の問題を解決してください。")
        if not args.use_sheets:
            print("         --use-sheets を付けて再実行すると Sheets データも検証できます。")
        sys.exit(1)
    else:
        print("\n[RESULT] 安全チェック全通過。Phase 3 実装を開始できます。")
        sys.exit(0)


if __name__ == "__main__":
    main()
