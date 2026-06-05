"""
run_video_pipeline.py - 動画パイプライン統合実行 CLI（Phase 2.25）

全ステップをシーケンシャルに実行する:
  1. ソース確認（reference_sources タブ）
  2. 動画収集状態確認（reference_posts content_type=video）
  3. 文字起こし（transcribe_videos.py 相当の処理）
  4. クリップ候補抽出（analyze_video_clips.py 相当）
  5. クリップ切り抜き dry-run（cut_video_clips.py 相当）
  6. 投稿文生成（generate_from_video_clips.py 相当）
  7. パイプライン整合性チェック

安全ガード:
  - デフォルト: dry_run=True（書き込み一切なし）
  - --test-write で書き込み有効
  - --use-sheets で実Sheets 接続
  - --mock / --mock-llm でモック動作
  - 文字起こし実API: ALLOW_TRANSCRIPTION_API=true + --confirm-api が両方必要
  - 切り抜き実行: --cut + --confirm-cut が両方必要
  - SNS 本番投稿は絶対にしない

使い方:
  # モック全体実行（デフォルト・推奨）
  python scripts/run_video_pipeline.py --account-id night_scout

  # 実Sheets + mockLLM + 書き込みあり（推奨テスト手順）
  python scripts/run_video_pipeline.py --account-id night_scout --use-sheets --test-write --mock-llm

  # 実Sheets + 実LLM + 書き込みあり
  python scripts/run_video_pipeline.py --account-id night_scout --use-sheets --test-write

  # 特定ステップのみ実行
  python scripts/run_video_pipeline.py --account-id night_scout --steps transcribe,analyze
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))
sys.path.insert(0, os.path.join(_V2_ROOT, "scripts"))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_V2_ROOT, ".env"))
except ImportError:
    pass

from config_loader import get_config_partial, get_transcription_config
from sheets_client import make_client
from video.clip_candidate_analyzer import analyze_transcripts_batch, save_clip_candidates
from video.clip_cutter import cut_clips_batch, update_cut_status
from generation.video_clip_generator import generate_from_clips_batch

ALL_STEPS = ["sources", "collect", "transcribe", "analyze", "cut", "generate", "integrity"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _section(title: str) -> None:
    print(f"\n{'=' * 55}")
    print(f"  {title}")
    print(f"{'=' * 55}")


def step_sources(client, account_id: str) -> dict:
    """ステップ1: reference_sources 確認（読み取り専用）"""
    _section("Step 1: ソース確認 (reference_sources)")
    try:
        sources = client.get_reference_sources(account_id=account_id)
    except AttributeError:
        sources = getattr(client, "_reference_sources", [])
        sources = [s for s in sources if s.get("account_id") == account_id]

    active = [s for s in sources if str(s.get("active", "true")).lower() != "false"]
    print(f"  登録ソース: {len(sources)} 件 (active: {len(active)} 件)")
    for s in active[:5]:
        print(f"    platform={s.get('platform', '?')} url={str(s.get('source_url', ''))[:60]}")
    return {"source_count": len(active)}


def step_collect(client, account_id: str) -> dict:
    """ステップ2: 動画収集状態確認"""
    _section("Step 2: 動画収集状態確認 (reference_posts)")
    try:
        posts = client.get_reference_posts(account_id=account_id, status="ACTIVE")
    except Exception:
        posts = []

    videos = [p for p in posts if str(p.get("content_type", "")).lower() == "video"]
    pending = [v for v in videos if str(v.get("transcription_status", "pending")).lower() == "pending"]
    done = [v for v in videos if str(v.get("transcription_status", "")).lower() == "done"]

    print(f"  動画参考投稿: {len(videos)} 件")
    print(f"    文字起こし待ち (pending): {len(pending)} 件")
    print(f"    文字起こし済み (done):    {len(done)} 件")
    return {"video_count": len(videos), "pending_count": len(pending), "done_count": len(done)}


def step_transcribe(client, account_id: str, *, dry_run: bool, allow_real: bool, limit: int = 10) -> dict:
    """ステップ3: 文字起こし"""
    _section("Step 3: 文字起こし (transcribe)")

    if allow_real:
        print("  [WARN] allow_real=True: 実Cloudflare API を呼び出します")
        print("  [WARN] ALLOW_TRANSCRIPTION_API=true が必要です")
    else:
        print("  [INFO] dry_run モード（実API呼び出しなし）")

    try:
        from transcription.cloudflare_whisper_client import CloudflareWhisperClient
        from transcription.transcription_limiter import TranscriptionLimiter

        transcription_cfg = get_transcription_config()
        whisper = CloudflareWhisperClient.from_config(transcription_cfg, dry_run=not allow_real)
        limiter = TranscriptionLimiter(
            client,
            limit_minutes=float(transcription_cfg.get("daily_limit_minutes", 120)),
            dry_run=dry_run,
        )
        print(f"  残り文字起こし上限: {limiter.remaining_minutes:.1f} 分")

        pending_videos = client.get_reference_posts(account_id=account_id, status="ACTIVE")
        pending_videos = [
            v for v in pending_videos
            if str(v.get("content_type", "")).lower() == "video"
            and str(v.get("transcription_status", "pending")).lower() == "pending"
        ][:limit]

        if not pending_videos:
            print("  文字起こし対象なし")
            return {"transcribed": 0}

        print(f"  対象: {len(pending_videos)} 件")
        processed = 0
        for video in pending_videos:
            ref_id = str(video.get("id", ""))
            duration = float(video.get("duration_seconds", 0) or 0)
            if not limiter.can_process(duration):
                limiter.record_skip()
                continue
            import uuid
            tr_id = f"tr-{str(uuid.uuid4())[:8]}"
            result = whisper.transcribe(
                audio_path=str(video.get("video_url", "")),
                reference_post_id=ref_id,
                transcript_id=tr_id,
                duration_seconds=duration,
            )
            limiter.record(duration_seconds=duration, status=result.status)
            row = result.to_sheets_row()
            row["account_id"] = account_id
            row["source_platform"] = str(video.get("platform", ""))
            row["video_url"] = str(video.get("video_url", ""))
            if not dry_run:
                client.save_video_transcript(row)
            else:
                print(f"    [dry-run] transcript_id={tr_id!r} status={result.status!r}")
            processed += 1

        limiter.flush()
        print(f"  文字起こし完了: {processed} 件")
        return {"transcribed": processed}

    except ImportError as e:
        print(f"  [SKIP] transcription モジュール未利用可能: {e}")
        return {"transcribed": 0, "skipped": True}


def step_analyze(client, account_id: str, *, dry_run: bool, mock_llm: bool, n_candidates: int = 6) -> dict:
    """ステップ4: クリップ候補抽出"""
    _section("Step 4: クリップ候補抽出 (analyze)")
    print(f"  mock_llm={mock_llm}")

    transcripts = client.get_video_transcripts(account_id=account_id, transcription_status="done")
    if not transcripts:
        print("  文字起こし済みデータなし → スキップ")
        return {"candidates": 0}

    print(f"  文字起こし済み: {len(transcripts)} 件")
    candidates = analyze_transcripts_batch(transcripts, account_id, n_candidates=n_candidates, mock_llm=mock_llm)
    stats = save_clip_candidates(client, candidates, dry_run=dry_run)
    print(f"  クリップ候補: {len(candidates)} 件 (保存: {stats['added']} 追加, {stats['skipped']} スキップ)")
    return {"candidates": len(candidates), "added": stats["added"]}


def step_cut(client, account_id: str, *, dry_run: bool) -> dict:
    """ステップ5: クリップ切り抜き（dry-run のみ）"""
    _section("Step 5: クリップ切り抜き (cut dry-run)")
    print("  [INFO] このステップは常に dry-run で実行します（実切り抜き禁止）")
    print("  [INFO] 実切り抜きは cut_video_clips.py --cut --confirm-cut で個別実行してください")

    candidates = client.get_video_clip_candidates(account_id=account_id, clip_status="candidate")
    pending_cut = [c for c in candidates if str(c.get("cut_status", "pending")).lower() == "pending"]

    if not pending_cut:
        print("  切り抜き待ち候補なし")
        return {"cut": 0}

    print(f"  切り抜き待ち: {len(pending_cut)} 件")
    results = cut_clips_batch(pending_cut, {}, dry_run=True)
    stats = update_cut_status(client, results, dry_run=True)
    print(f"  dry-run 完了: {len(results)} 件")
    return {"cut": len(results)}


def step_generate(client, account_id: str, *, dry_run: bool, mock_llm: bool) -> dict:
    """ステップ6: 投稿文生成"""
    _section("Step 6: 投稿文生成 (generate)")
    print(f"  mock_llm={mock_llm}")

    try:
        account = client.get_account(account_id) or {"account_id": account_id}
    except Exception:
        account = {"account_id": account_id}

    # rights_status=allowed のみ生成対象（not_allowed はスキップ、unknownも処理する）
    candidates = client.get_video_clip_candidates(account_id=account_id, clip_status="candidate")
    generable = [
        c for c in candidates
        if str(c.get("text_generation_status", "pending")).lower() == "pending"
        and str(c.get("rights_status", "unknown")).lower() != "not_allowed"
    ]

    if not generable:
        print("  生成対象クリップ候補なし")
        return {"generated": 0}

    print(f"  生成対象: {len(generable)} 件")
    stats = generate_from_clips_batch(generable, client, account, mock_llm=mock_llm, dry_run=dry_run)
    print(
        f"  生成完了: total={stats['total']} "
        f"generated={stats['generated']} "
        f"rights_blocked={stats['rights_blocked']} "
        f"errors={stats['errors']}"
    )
    return stats


def step_integrity(account_id: str) -> dict:
    """ステップ7: パイプライン整合性チェック"""
    _section("Step 7: パイプライン整合性チェック")
    try:
        from check_pipeline_integrity import (
            check_video_clip_candidates,
            check_video_transcripts,
        )
        from sheets_client import MockSheetsClient
        client_check = MockSheetsClient(dry_run=True)
        results_check: list[str] = []
        issues = check_video_clip_candidates(client_check, account_id, results_check)
        issues += check_video_transcripts(client_check, account_id, results_check)
        for r in results_check:
            print(f"  {r}")
        print(f"  整合性チェック: issues={issues}")
        return {"issues": issues}
    except Exception as e:
        print(f"  [WARN] 整合性チェックをスキップ: {e}")
        return {"issues": -1}


def main() -> int:
    parser = argparse.ArgumentParser(description="動画パイプライン統合実行 CLI（Phase 2.25）")
    parser.add_argument("--account-id", required=True, help="アカウントID（night_scout / liver_manager）")
    parser.add_argument("--use-sheets", action="store_true", help="実Google Sheets 接続")
    parser.add_argument("--test-write", action="store_true", help="Sheets 書き込み有効化")
    parser.add_argument("--mock", action="store_true", help="MockSheetsClient を強制使用")
    parser.add_argument("--mock-llm", action="store_true", default=True,
                        help="LLM をモック使用（デフォルト: True）")
    parser.add_argument("--no-mock-llm", dest="mock_llm", action="store_false",
                        help="実LLM を使用")
    parser.add_argument("--confirm-api", action="store_true",
                        help="文字起こし実API呼び出し許可（ALLOW_TRANSCRIPTION_API=true も必要）")
    parser.add_argument("--steps", default="all",
                        help=f"実行ステップ（カンマ区切り、all または {ALL_STEPS}）")
    parser.add_argument("--limit", type=int, default=10,
                        help="文字起こし対象動画の最大件数（デフォルト: 10）")
    parser.add_argument("--n-candidates", type=int, default=6,
                        help="動画1本あたりのクリップ候補数（デフォルト: 6）")
    args = parser.parse_args()

    print("=" * 60)
    print("  run_video_pipeline.py - 動画パイプライン統合実行")
    print("=" * 60)
    print("[INFO] SNS 本番投稿は行いません")
    print("[INFO] posted_results への書き込みは行いません")

    dry_run = not args.test_write
    force_mock = not args.use_sheets or args.mock

    if dry_run:
        print("[INFO] DRY-RUN モード（--test-write なし）")
    if force_mock:
        print("[INFO] MockSheetsClient を使用（--use-sheets なし）")

    transcription_cfg = get_transcription_config()
    allow_real = args.confirm_api and transcription_cfg.get("allow_transcription_api", False)
    if args.confirm_api and not transcription_cfg.get("allow_transcription_api", False):
        print("[WARN] --confirm-api が指定されましたが ALLOW_TRANSCRIPTION_API=false のためモック動作")

    cfg = get_config_partial()
    client = make_client(cfg, dry_run=dry_run, force_mock=force_mock)

    # 実行ステップの決定
    if args.steps.lower() == "all":
        steps = ALL_STEPS
    else:
        steps = [s.strip() for s in args.steps.split(",")]
        invalid = [s for s in steps if s not in ALL_STEPS]
        if invalid:
            print(f"[ERROR] 不明なステップ: {invalid}. 有効: {ALL_STEPS}")
            return 1

    print(f"\n実行ステップ: {steps}")
    print(f"アカウント: {args.account_id}")
    print(f"mock_llm: {args.mock_llm}")

    results: dict[str, dict] = {}
    start_time = time.time()

    if "sources" in steps:
        results["sources"] = step_sources(client, args.account_id)

    if "collect" in steps:
        results["collect"] = step_collect(client, args.account_id)

    if "transcribe" in steps:
        results["transcribe"] = step_transcribe(
            client, args.account_id,
            dry_run=dry_run,
            allow_real=allow_real,
            limit=args.limit,
        )

    if "analyze" in steps:
        results["analyze"] = step_analyze(
            client, args.account_id,
            dry_run=dry_run,
            mock_llm=args.mock_llm,
            n_candidates=args.n_candidates,
        )

    if "cut" in steps:
        results["cut"] = step_cut(client, args.account_id, dry_run=dry_run)

    if "generate" in steps:
        results["generate"] = step_generate(
            client, args.account_id,
            dry_run=dry_run,
            mock_llm=args.mock_llm,
        )

    if "integrity" in steps:
        results["integrity"] = step_integrity(args.account_id)

    elapsed = time.time() - start_time

    _section("実行結果サマリー")
    for step, result in results.items():
        print(f"  {step}: {result}")
    print(f"\n  経過時間: {elapsed:.1f}s")
    print(f"  完了時刻: {_now()}")

    issues = results.get("integrity", {}).get("issues", 0)
    if isinstance(issues, int) and issues > 0:
        print(f"\n[WARN] パイプライン整合性問題: {issues} 件")
        return 1

    print("\n[OK] パイプライン実行完了")
    return 0


if __name__ == "__main__":
    sys.exit(main())
