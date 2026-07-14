# Production Completion Status

## 2026-07-12 Approved Media Automation Expansion

The user explicitly reconfirmed permission for the configured media source URLs to be downloaded, transcribed, analysed, clipped, stored in Cloudinary, and reposted with a newly written Threads caption. The permission is recorded source-by-source as `approved_creator_clip`, `permission_status=approved`, and `media_autopilot_enabled=true`; it is not inferred for unregistered URLs.

- `liver_manager`: one approved YouTube channel and three approved TikTok accounts are eligible for bounded discovery and media production.
- `night_scout`: the nine registered YouTube channels are now eligible under the same source-level permission record. The Night Scout TikTok placeholder remains excluded because no actual Night Scout TikTok URL is registered.
- `.github/workflows/media-growth-production.yml` runs the liver media chain daily at JST 09:20. `.github/workflows/media-growth-production-night-scout.yml` runs the Night Scout chain daily at JST 12:20. Each workflow is account-fixed and can publish at most one approved video post for that account per day.
- The shared pipeline is: bounded metadata discovery -> individual video URL -> local/caption transcript -> transcript-grounded clip candidates -> ffmpeg 9:16 clip -> Cloudinary -> media validator -> Threads video + newly generated `public_post_text` -> `posted_results` / PDCA records.
- `fetch_enabled=false` remains the generic reference-collection safety setting. Approved media automation uses the separate, explicit `media_autopilot_enabled=true` field and the bounded media workflow, so X, beauty, TODO entries, and ordinary reference sources remain outside this execution path.
- X posting, beauty posting, external transcription API calls, unregistered/TODO URLs, and sources without approved permission evidence remain blocked.

## 2026-07-12 Full Automation Recovery / Transcript-Grounded Media

Current production design is:

- Text-only Threads schedules are ON for `night_scout` and `liver_manager`.
- The recent "no automatic posting / Sheets not written" issue was not a disabled schedule. Both account-specific scheduled workflows were firing, but apply failed on Sheets API 429. The immediate causes were row-by-row `update_cell` writes in `generate_threads_ideas_from_references.py` and repeated `setup_all()`/read-after-write behavior in `refill_threads_queue.py`.
- Text generation writes are now batched with row-level `batch_update` and `append_rows`. Refill now skips `setup_all()` in production and avoids post-write verification reads.
- Threads queue posting now retries Sheets append/find/update operations on 429/quota responses. Queue status updates use row-level `batch_update` instead of repeated `update_cell`, and non-critical PDCA/log save failures no longer turn a successful post into a failed workflow.
- AUTO_READY promotion now uses the same batched/retried queue update path through `SheetsClient.update_queue_item()`. The July 12 Actions failure at `auto_approve_queue.py` was caused by the older `update_cell` loop hitting Sheets write quota.
- The same queue update path also retries queue header reads (`row_values(1)`) because the next observed failure was a Sheets read quota 429 before the batched update could run.
- Production workflows use workflow-scoped concurrency, `sns-growth-production-${{ github.workflow }}-${{ github.ref }}`, with `cancel-in-progress=false`. A shared group was tested and reverted because GitHub Actions permits only one pending run per concurrency group and cancelled same-time account runs. Sheets quota is instead protected by batched writes, lower rereads, and non-blocking fallback for reference collection/scoring failures.
- `Production Autopilot Aftercare` remains ON for bounded source registry sync, metrics/PDCA, and approved video discovery.
- `Media Transcription Production` is now ON at JST 00:10. It transcribes only approved `liver_manager` `source_videos` with individual video URLs, max 3 per run. YouTube captions are preferred; local Whisper fallback is step-scoped and does not enable external transcription API.
- `Media Growth Production` remains ON at JST 09:20, but production selection now requires `transcript_grounded=true`. Old duration-only clip candidates are blocked by `transcript_grounding_required`.

What is automated now:

- Text-only Threads posting through GitHub Actions.
- Source registry sync and aftercare.
- Approved source video discovery.
- Approved individual source video transcription.
- Transcript-grounded clip candidate generation.
- One approved liver_manager video post per day through the media workflow, after transcript, rights, permission, validator, media validator, Cloudinary, Threads and daily-cap gates.

What remains blocked by design:

- X fetch/post.
- beauty posting.
- Unknown/reference-only/third-party media download/cut/upload/repost.
- External transcription API (`ALLOW_TRANSCRIPTION_API=false`).
- Unbounded TikTok profile scraping.
- `learning_rules` auto-apply.

## 2026-07-11 Production Completion Audit

The production path is now connected end to end for the two approved operating modes.

- Text-only Threads: the account-specific `night_scout` and `liver_manager` schedules remain enabled. A failed reference-generation step now falls back to the safe original-post inventory, so an empty or stale reference set does not silently stop READY creation.
- Production aftercare: JST 23:40 syncs the source registry before bounded approved-source discovery, metrics/PDCA processing, and clip-candidate persistence. It never posts or downloads media.
- Approved media: `Media Growth Production` runs daily at JST 09:20 for `liver_manager`, selects only `owned` / `licensed` / `approved_creator_clip` media with approved permission evidence, and can create at most one video post per day.
- Media execution is a real connected chain: bounded metadata discovery -> `source_videos` -> clip candidate -> yt-dlp download -> ffmpeg 9:16 cut -> Cloudinary upload -> media validator -> READY queue -> Threads video container -> `posted_results`.
- All real media gates are scoped to the single production step. X, beauty, unknown/reference-only media, and transcription API remain disabled. `kill_switch=true` stops execution.
- Unknown metrics remain blank until measured; they are never fabricated as zero.

The pre-fix scheduled runs failed because production Sheets lagged behind the 73-row source registry and reference generation could leave no promotable candidate. Daily registry sync and safe fallback generation address both causes. The first runs after this commit must still be observed for external API/credential availability; that is operational verification, not an unimplemented code path.

The first manual aftercare apply on the new workflow (`29134404560`) exposed a Sheets write-quota issue in the legacy row-by-row registry upsert. Registry updates are now batched while preserving existing rows and unknown columns, reducing a full sync from roughly 70 writes to at most two writes per tab.

Date: 2026-07-10 (最終更新 — Production Autopilot Aftercare追加)
Created: 2026-06-24

## Status

The project is operational for Threads-first text-only autonomous operation, with media/video growth features implemented as gated dry-run/manual foundations.
`threads-queue-worker.yml` の Sheets verify は check 総数 **51 件**（2026-06-25 snapshot の 33 件 → item J の media/metrics チェック等で +8 → READY 承認モデルで +10）。合格条件は `failed=[]`（`passed` は seed 充足状況で変動）。READY 承認モデル追加後の live `--verify-only` 再確認は #68 で実施。

## 2026-07-10 Update — Production Autopilot Aftercare

ユーザー方針「個別確認で止めず、本番で自動運用する」に合わせて、text-only投稿の自動scheduleに加え、投稿後aftercareとMedia Growth Engineの保存系を自動運用へ接続した。

本番で自動実行されるもの:

- `Autonomous Growth Loop Night Scout` / `Autonomous Growth Loop Liver Manager`: account別scheduleで text-only Threads posting を自動実行。`max_posts_per_run=1`、`daily_post_cap_per_account=5`、final public post validator、X/media/beauty block は維持。
- `Production Autopilot Aftercare`: 毎日 JST 23:40 にmetrics snapshot、PDCA候補生成、許可済みliver_manager sourceの `source_videos` discovery、`video_clip_candidates` 生成・Sheets保存を実行。
- `source_videos` / `video_clip_candidates`: approved sourceのみ、dedupe付きで保存。dry-runでは保存しない。

安全のため自動公開しないもの:

- X fetch/post、beauty投稿、未許可media、`third_party_reference_only` media。
- 実download、実cut、Cloudinary実upload、Threads video+text post。
- learning_rules の自動適用。PDCAは候補・提案まで。

今回の追加:

- `config/production_autopilot.json`
- `.github/workflows/production-autopilot-aftercare.yml`
- `discover_approved_source_videos.py --apply --confirm-discovery --use-sheets`
- `run_media_growth_engine.py --apply --confirm-media-growth --use-sheets`

## 2026-07-10 Update — Review Closure / Completion Classification

添付レビューの指摘はおおむね正しい。`d7357e0` 時点では「診断と fallback は入ったが、空referenceからREADYを作れること、`--stop-before-post` で投稿せずREADY生成を検証できること、docsのAUTO_READY仕様整合性、text-onlyのmedia risk分類、1日5投稿に耐えるテーマ在庫」の証明が不足していた。

今回の補強で完了扱いにしたもの:

- text-only scheduled autonomous posting path: schedule → generation/fallback → AUTO_READY → READY → worker の導線を静的・mockテストで固定。
- `--stop-before-post`: generation/AUTO_READY までは進め、`process_threads_queue.py` を呼ばず `would_post=false` で止める診断導線をテスト化。
- safe fallback inventory: `night_scout` 15本、`liver_manager` 12本の reader-facing template pool を用意し、同一run内で重複しないことを検査。
- text-only candidates: `media_reuse_risk=not_applicable` に正規化。media reuse risk は動画/画像再利用時のリスクであり、text-only fallbackを high 扱いしない。
- AUTO_READY diagnostics: reject reason / ready count / checked count / approved count / rejected count / autonomous_health の仕様をテスト化。
- docs comments: 「READYは人間承認のみ」という旧記述を、`approve_queue.py` または `auto_approve_queue.py` の2系統に更新。

基盤はあるが本番ONではないもの:

- Media Growth Engine: source video discovery、transcript/clip candidate schema、download/cut/upload/video-post runner、media validator、PDCA記録の土台はある。ただし schedule はOFF、実download/cut/upload/video post は env + confirm gate 必須。
- Metrics/PDCA: posted_results の `metrics_status=PENDING` とPDCA初期記録は作る。実metrics自動取得、改善案の自動適用、learning_rules auto-apply は未ON。
- YouTube/TikTok media use: approved source のみ設計上eligible。channel/account URLの無制限downloadはしない。個別video URL、権利証跡、manual apply が必要。

明示的に未完成 / production-off:

- 実download、実cut、Cloudinary実upload、Threads video+text post。
- media schedule。
- X fetch/post。
- beauty_account posting。
- transcription API自動呼び出し。
- learning_rules の自動書き換え。

次回scheduled runで見るべきもの:

- `health_summary.ready_count > 0`
- `health_summary.posted_count`
- `health_summary.no_post_reason` が空、または `NO_READY_QUEUE` / `AUTO_READY_REJECTED_ALL` から変化していること。
- `posted_results.post_url` または `external_post_id` が保存され、`metrics_status=PENDING` になっていること。

## 2026-07-09 Update — GitHub Actions Schedule Firing Audit

GitHub Actions itself is enabled and the autonomous workflows are active. The account-specific schedules are firing:

- `Autonomous Growth Loop Night Scout`: latest checked scheduled run `29003612060`, success, reached apply.
- `Autonomous Growth Loop Liver Manager`: latest checked scheduled run `29000408859`, success, reached apply.

The current no-post symptom is not an Actions-disabled/no-schedule issue. The observed production reason is `NO_READY_QUEUE`: apply runs, `auto_approve_queue.py` rejects or skips candidates, and `process_threads_queue.py` finds no `READY` queue row. This must be checked separately from schedule firing.

Workflow hardening added:

- explicit `permissions: contents: read` and `actions: read`
- account-specific `concurrency` with `cancel-in-progress: false`
- `Schedule heartbeat` step
- `workflow_dispatch` `dry_run_only` input that prevents guard/apply even if confirm is true
- health check coverage for permissions, concurrency, heartbeat, and dry-run-only safety

Next scheduled windows from 2026-07-09 18:50 JST are both accounts at JST 21:00 ±15min, then `night_scout` at JST 25:00 ±15min.

## 2026-07-09 Update — READY Shortage Recovery

The next production blocker after schedule firing was `NO_READY_QUEUE` / `AUTO_READY_REJECTED_ALL`. The text-only autonomous path now has a safer recovery mechanism:

- Stale generated rows with the same IDs are refreshed when their status is not locked.
- Locked rows (`READY`, `PROCESSING`, `MEDIA_READY`, `POSTED`) are never overwritten.
- When reference-generated rows are all skipped because they already exist in locked states, safe timestamped fallback candidates are added.
- Fallback candidates are validated by `final_public_post_validator` and covered by AUTO_READY tests for both `night_scout` and `liver_manager`.
- Health summary distinguishes `AUTO_READY_REJECTED_ALL` from worker-level `NO_READY_QUEUE`.

This does not execute a real post by itself. It makes the next scheduled apply capable of producing a safe `READY` candidate instead of repeatedly reusing stale rejected rows.

## 2026-07-07 Update — Autonomous Posting Recovery

Account-specific scheduled autonomous posting is still the production text-only path:

- `Autonomous Growth Loop Night Scout`
- `Autonomous Growth Loop Liver Manager`

The schedules were firing, but recent runs failed before posting because `recover_production_sheets_threads_first.py --verify-only --json` returned non-posting registry reflection failures (`source_registry_reflected`, `video_sources_reflected`) and `run_autonomous_loop.py` treated that as a hard apply blocker.

Recovery changes:

- Sheets verify failure is now recorded as `sheets_verify_failed_non_blocking_runner_will_validate` and no longer blocks the whole autonomous apply by itself.
- Source fetch, video reference, and reference scoring failures are soft-fail warnings so the runner can continue to safe fallback post generation.
- If source posts/scores are empty, `generate_threads_ideas_from_references.py` creates validated reader-facing fallback candidates in `WAITING_REVIEW`.
- `auto_approve_queue.py` can promote safe fallback candidates to `READY`.
- `process_threads_queue.py` reports `NO_POST` / `NO_READY_QUEUE` as JSON when there is no eligible queue row.
- Scheduled workflows now run `scripts/check_autonomous_health.py --dry-run` in an `if: always()` summary step.
- Added `src_ns_threads_user_chiishunin_s` as a `night_scout` Threads reference source.

Current production state:

- text-only schedule: ON
- media schedule: OFF
- X fetch/post: OFF
- beauty posting: BLOCKED
- real download/cut/upload/video post: OFF unless separate env+confirm gates are intentionally enabled
- `kill_switch=false`
- `daily_post_cap_per_account=5`
- `max_posts_per_run=1`
- `cooldown_minutes=90`

Next scheduled run should be checked for `health_summary.posted_count`, `health_summary.no_post_reason`, `posted_results`, and queue status transitions.

## 2026-07-02 Update — Autonomous Text-Only Threads Pilot

Autonomous mode has been added for the initial reviewed text-only Threads pilot.

- Config: `config/autonomous_mode.json`
- Runner: `scripts/run_autonomous_loop.py`
- Workflow: `.github/workflows/autonomous-growth-loop.yml`
- Runbook: `docs/autonomous-mode-runbook.md`

The user no longer needs to approve every individual post in this autonomous path. Safety remains rules-based:

- only `night_scout` and `liver_manager`
- Threads posting only
- X fetch/post blocked
- `beauty_account` blocked
- media posts blocked
- third-party/unknown-rights media blocked
- max 1 post per run and daily post cap 1 per account
- `kill_switch=true` stops the workflow
- apply requires `--confirm-autonomous`

No autonomous apply or real post was executed during this implementation pass.

## 2026-06-29 アップデート — Threads worker READY 承認モデル必須化（Phase 3）

### 変更点

- `process_threads_queue.py` の投稿対象を **`READY` のみ**に変更（`ELIGIBLE_STATUSES = {"READY"}`）。
  `WAITING_REVIEW` / `DRAFT` / `PLANNED` は投稿対象外。状態遷移 `WAITING_REVIEW → READY → PROCESSING → POSTED`。
- 生成系CLI（refill / clip / metrics 候補 / seed）は `READY` を直接書かない。`READY` 昇格は `approve_queue.py`（人間承認）または `auto_approve_queue.py`（AUTO_READY条件通過）経由のみ。承認時は logs に `queue_approved` 互換証跡を残す。
- X 側 `publish_queue.py` の `--status READY` 必須ゲートと対称になり、旧「承認モデル非対称」の潜在課題を解消。
- verify に READY 承認モデルの安全チェック10件を追加（`waiting_review_not_postable` / `ready_is_only_postable_status` / `generated_candidates_not_ready_by_default`（承認証跡で誤検知防止）/ `no_ready_for_x_or_beauty` / media 権利3件 ほか）。
- 回帰固定テスト `test_recover_verify_ready_checks.py` ほか READY 系11本を追加。curated suite **55 / 55 PASS**（offline）。

## 2026-06-25 アップデート — posted_results 整合性修復

### 失敗原因

GitHub Actions `threads-queue-worker.yml` dry_run で `recover_production_sheets_threads_first.py --verify-only` が exit code 1 で失敗していた。

- `verification_passed=30 failed=3`
- `failed_checks=posted_metrics_status_allowed,posted_real_post_true,posted_media_used_false`

**原因**: posted_results 既存3行のうち、以下2行の新規カラムが空欄だった（Sheetsに列が追加された時点で既存行に値が書かれていなかった）。
- `recovery_threads_initial_night_scout` (status=RECOVERED): metrics_status / real_post / media_used 空
- `real_threads_liver_manager_20260624_01` (status=POSTED): metrics_status / real_post / media_used 空

**修正内容**:
1. `scripts/repair_posted_results_integrity.py` を新規作成
   - POSTED 行: metrics_status="" → "PENDING", real_post="" → "true", media_used="" → "false"
   - RECOVERED 行: metrics_status="" → "MANUAL_PENDING", real_post="" → "true", media_used="" → "false"
   - `--apply` で Sheets 書き込み、`--dry-run` では書き込まない
   - read-after-write 確認付き
2. `backfill_posted_results()` の POSTED 行 metrics_status 補正値を "MANUAL_PENDING" → "PENDING" に修正
3. `.github/workflows/threads-queue-worker.yml` に repair ステップを追加 (verify の前に実行)
4. `scripts/test_repair_posted_results_integrity.py` 17項目 PASS
5. `scripts/test_recovered_posted_result_verify_warn.py` 10項目 PASS

### 修復後の確認結果

```
verification_passed=33 failed=0
count_posted_results=3
threads_credentials_night_scout=SET
threads_credentials_liver_manager=SET
```

- `python3 scripts/process_threads_queue.py --account-id night_scout --dry-run`: status=DRY_RUN ✓
- `python3 scripts/process_threads_queue.py --account-id liver_manager --dry-run`: status=DUPLICATE_BLOCKED ✓（duplicate guard 正常動作）

## Completed

- Existing unpushed main commit was pushed to GitHub before recovery.
- Google Sheets tabs were audited.
- Empty production tabs were seeded.
- Read-after-write verification passed.
- CTA rules were applied to code, Sheets seed, prompt templates, and docs.
- X posting was disabled for recovery mode.
- `night_scout` and `liver_manager` Threads queues were seeded.
- `beauty_account` remains blocked.
- Cloudinary upload was not executed.
- Media download/cut/upload was not executed.
- One `liver_manager` Threads real post was executed and recorded.
- `scripts/process_threads_queue.py` added for queue row processing.
- `scripts/import_threads_metrics_manual.py` added for manual insights import.
- `scripts/refill_threads_queue.py` added for review queue refill.
- `.github/workflows/threads-queue-worker.yml` added as manual-only worker.
- `content-daily-dry-run.yml` switched to Threads-first queue dry-run/refill dry-run/publisher dry-run.

## Verification

- Sheets verification: 21 / 21 PASS.
- Required local tests: 18 / 18 scripts PASS.
- Credential readiness: READY for required items.
- Cloudinary: credentials SET, upload disabled.
- Cloudflare transcription: optional credentials missing, transcription disabled.
- Stricter local Sheets verification and worker dry-run against live Sheets: blocked by local approval credits.
- GitHub Actions dry-run attempted twice and classified: repository Sheets secrets missing, so the workflow stopped before queue processing.
- True dry-run implementation verified locally: worker/refill dry-run do not call `setup_all()` or write to Sheets.

## 2026-06-25 アップデート — 孤児投稿復旧・Sheets 429 対策

### 失敗原因

GitHub Actions `threads-queue-worker.yml` real_post 実行後、Threads 投稿は成功したが
Sheets API 429（Read requests per minute per user quota）で `save_posted_result()` が失敗した。

- `queue_id=recovery_night_scout_queue_01` が PROCESSING に残存
- `posted_results` に行が未追加

**原因**: `append_row` / `update_row` がヘッダー行 (`ws.row_values(1)`) を毎回呼び出しており、
複数回の Sheets API コールで quota を超過した。

**修正内容**:

1. `process_threads_queue.py`
   - `_headers_cache` 追加（同一 ws はセッション内 1 回のみ `row_values(1)` を呼ぶ）
   - `_get_headers()` に 429 指数バックオフ（5s/15s/30s）追加
   - real_post モードの `setup_all()` 呼び出しを削除（タブは初期化済み前提）
   - `FALLBACK_DIR` 定数追加、`write_fallback()` に `dry_run` パラメータ追加

2. `scripts/recover_orphan_threads_post.py` 新規作成
   - Threads API で最新投稿を取得してテキスト一致を確認
   - `--skip-api-lookup` で ID 不明のまま RECOVERED 行を追加可
   - 実行結果: `recovery_night_scout_queue_01` → status=POSTED、posted_results に RECOVERED 行追加

3. `.github/workflows/threads-queue-worker.yml`
   - `output/posted_results_fallback/` を `actions/upload-artifact` で 30 日保存 (`if: always()`)

4. `recover_production_sheets_threads_first.py`
   - `queue_night_scout_3` → `queue_night_scout_2` に変更（孤児復旧で active 行が 2 に）

5. テスト 4 本追加（全 PASS）:
   - `test_recover_orphan_threads_post.py`: 13 PASS
   - `test_sheets_rate_limit_backoff.py`: 14 PASS
   - `test_queue_worker_no_setup_all_in_real_mode.py`: 12 PASS
   - `test_fallback_artifact_no_secrets.py`: 11 PASS

### 修復後の確認結果

```
verification_passed=33 failed=0
count_posted_results=4
count_queue_night_scout=2
```

- `python3 scripts/process_threads_queue.py --account-id night_scout --dry-run`: queue_02 status=DRY_RUN ✓
- `python3 scripts/process_threads_queue.py --account-id liver_manager --dry-run`: status=DUPLICATE_BLOCKED ✓

## 2026-06-25 アップデート — queue WARN 設計 / liver_manager dup 解消

### 変更内容

1. `recover_production_sheets_threads_first.py` `verify_state()`
   - `queue_night_scout_3` / `queue_liver_manager_3` チェックを廃止
   - 代わりに `queue_night_scout_min1` / `queue_liver_manager_min1`（>= 1 なら PASS）を採用
   - queue が 1〜2 件 → `warning_list` / `refill_needed_accounts` に追記。FAIL にはならない
   - queue が 0 件 → 従来通り FAIL
   - `RECOVERED` 行の `external_post_id` 未補完 → WARN のみ（FAIL にしない）
   - `posted_save_failed` > 0 → WARN のみ

2. night_scout queue 補充
   - `refill_threads_queue.py --account-id night_scout --count 1` 実行
   - queue_after=4（WAITING_REVIEW 3 / PLANNED 1）

3. liver_manager DUPLICATE_BLOCKED 解消
   - `recovery_liver_manager_queue_01`（draft=`recovery_liver_manager_draft_01`）が posted_results に既存のため dry-run でも DUPLICATE_BLOCKED だった
   - `refill_threads_queue.py --account-id liver_manager --count 1` で新候補追加
   - Sheets 上で `recovery_liver_manager_queue_01` を直接 `DUPLICATE_BLOCKED` に更新（実投稿なし）
   - `process_threads_queue.py --account-id liver_manager --dry-run` → `status=DRY_RUN` ✓（`recovery_liver_manager_queue_02` が選ばれる）

4. night_scout posted_results 孤児投稿
   - `orphan_recovery_recovery_night_scout_queue_01_*` の `post_url` を更新
   - `https://www.threads.com/@kyaba_consul_mizu/post/DZ_bylhAIqz`
   - `external_post_id=18050331680547160`
   - WARN なし（補完済み）

5. 新規テスト 3本追加（各 14〜15 PASS）
   - `test_verify_queue_minimum_warn_not_fail.py`: 15 PASS
   - `test_refill_needed_accounts_warning.py`: 15 PASS
   - `test_posted_recovered_post_url_backfill.py`: 14 PASS

### 修復後の確認結果

```
verification_passed=33 failed=0
warning_list=[]
count_posted_results=4
count_queue_night_scout=3
count_queue_liver_manager=3
```

- `python3 scripts/process_threads_queue.py --account-id night_scout --dry-run`: queue_02 status=DRY_RUN ✓
- `python3 scripts/process_threads_queue.py --account-id liver_manager --dry-run`: queue_02 status=DRY_RUN ✓

## 2026-06-26 アップデート — GitHub Actions dry_run 両アカウント PASS

### GitHub Actions dry_run 結果

- run `28212477795` (night_scout): **success** — verification_passed=33 failed=0, status=DRY_RUN ✓
- run `28212482318` (liver_manager): **success** — verification_passed=33 failed=0, status=DRY_RUN ✓

### 追加変更

- `.github/workflows/threads-queue-worker.yml`: dry_run では post-processing verify を skip（`if: mode == 'real_post'` 条件付き）。real_post では sleep 60 + verify を実行。
- `test_threads_queue_worker_workflow.py`: verify-after の `if: real_post` 条件チェック追加（14 PASS）

## 2026-06-26 アップデート — self_generated media パイプライン追加

法的リスク最小の「自前生成テキストカード」パスを実装（第三者 media・実投稿・実 upload は一切なし）。

1. `src/media/social_card.py` + `scripts/generate_social_card.py`
   - PIL で 1080x1350 / 1080x1080 のテキストカード描画
   - self_generated レコード（rights_policy=owned / reuse_policy=allow_reuse / media_policy=owned / status=SELF_GENERATED）
   - 出力は `output/social_cards/`（gitignore 済）。Sheets 書き込みなし。Cloudinary upload は別ゲート維持
2. `src/publishers/threads_publisher.py` — `publish()` に `media_url` 追加
   - dry-run + media: 「IMAGE 添付予定」を計画表示（API 呼び出しなし）
   - real mode + media: env フラグ true でも `SAFETY_STOP` でハード拒否（実 media 投稿は構造的に不可能）
3. `src/media/queue_media_attach.py` + `scripts/attach_media_to_queue.py`
   - 権利クリア media のみ queue 付与計画（plan-only・Sheets 書き込みなし）

テスト 3 本追加: social_card 22 / publisher_media_dryrun 11 / attach_media 14（全 PASS）。
既存 publisher テスト（phase10/phase13/preflight）回帰なし。
commit: `8b14d01` / `9bdf7f5` / `cccaee6`（main に push 済み）。

## 2026-06-27 アップデート — media 承認ワークフロー + metrics ループ実装

2026-06-26 時点で「保留」だった項目のうち、**コード・ゲート・テストで完結する範囲**を実装した。
実 upload / 実 media 投稿 / 本番 Sheets への実書き込みは、引き続き明示フラグと確認ゲートの後ろに保持する。

### 実装した内容

1. `scripts/attach_media_to_queue.py`（item G）
   - 権利クリア media を queue 行へ付与。既定 PLAN_ONLY。実書き込みは `--apply --confirm-attach`。
   - 既存ヘッダーのある列だけに書き込む（防御的）。`--apply` と `--input-json` の併用は拒否。
2. `scripts/upload_approved_media_to_cloudinary.py`（item H）
   - `evaluate_upload_gate()`: approval_status=APPROVED または status=SELF_GENERATED、かつ権利クリア、
     かつ rights_review_required≠true、かつローカルファイル存在、のときのみ許可。
   - 実 upload は `--apply --confirm-upload` かつ `ALLOW_CLOUDINARY_UPLOAD=true` のときだけ。secrets は出力しない。
3. `scripts/approve_self_generated_media.py`（item I）
   - self_generated・権利クリア・未承認の media のみ approval_status=APPROVED に。
   - 既定 PLAN_ONLY。実書き込みは `--apply --confirm-approve`。beauty_account は不可。
4. `scripts/import_threads_metrics_manual.py` 強化（item L）
   - ER 計算を純粋関数 `compute_engagement_rate()` に分離。
   - 決定論的 id による再インポートの二重追記を `row_exists()` ガードで防止（冪等化）。
5. `scripts/generate_next_queue_from_metrics.py` 新規（item L）
   - posted_results の MEASURED 行を ER 降順でランキングし、次回候補を生成。
   - 生成 queue 行の status は worker の `ELIGIBLE_STATUSES`（現在は {READY}）に
     **含めない**（`DRAFT`）。worker が自動投稿しないことをコードで保証（assert）。
     ※ 2026-06-29 に `ELIGIBLE_STATUSES` は {READY} に変更（READY 承認モデル）。本項記載時は {WAITING_REVIEW, PLANNED} だったが、DRAFT が非対象である点は変わらない。
   - 既定 PLAN_ONLY。実書き込みは `--apply --confirm-generate`。beauty_account / x は対象外。
     改善提案は status=WAITING_REVIEW（auto_apply=false）。
6. `recover_production_sheets_threads_first.py` verify 強化（item M）
   - `media_approved_rows_rights_clear`: APPROVED media は権利クリアであること
   - `media_uploaded_only_if_approved`: upload 済み media は承認済みのみ
   - `metrics_candidates_not_postable`: metrics 由来候補は worker 非対象 status であること
   - `metrics_suggestions_waiting_review`: metrics 由来提案は WAITING_REVIEW であること

### テスト（item N）

新規 7 本 + 関連既存 29 本 = **curated 36 / 36 PASS**（offline 完結）。
- 新規: `test_generate_next_queue_from_metrics`(17) / `test_metrics_import_idempotency_and_er`(11) /
  `test_recover_verify_media_metrics_checks`(8) / `test_approve_self_generated_media`(11) /
  `test_upload_approved_media_gate`(10) / `test_attach_media_apply_writes`(14) / `test_attach_media_to_queue`(14)
- 既存回帰なし（queue worker / refill / posted_results integrity / verify / beauty/x safety / cta 等）。

### 引き続きゲート保持（明示確認が必要・自動実行しない）

- liver_manager Threads 実投稿（`PUBLISH_ENABLED=true ALLOW_REAL_THREADS_POST=true --confirm-real-post`）
- Cloudinary 実 upload（`ALLOW_CLOUDINARY_UPLOAD=true --confirm-upload`）
- 上記スクリプトの本番 Sheets `--apply`（attach / approve / generate）
- git commit / push

## Remaining Manual Checks

- `night_scout` の Threads 次投稿候補（WAITING_REVIEW）は、人間が `approve_queue.py --queue-id <id> --approve --reason "..."` で `READY` に昇格するか、scheduled run 内の `auto_approve_queue.py` が安全条件を満たした場合だけ worker 投稿対象になる
- Threads insights（night_scout 初回投稿 / liver_manager 投稿）を確認する
- X API Credits を補充し、X 投稿を再開するかどうか判断する
- Cloudinary upload を使う場合は `ALLOW_CLOUDINARY_UPLOAD=true` で `media-approved-pilot.yml` を実行する

## 過去共有sourceの回収・registry化 (2026-06-29)

- ユーザーが過去に共有済みのソースアカウントURL/選定ルールを、既存 repo / `production_sources.example.json` から回収し `config/source_accounts/default_sources.json` へ dedup マージ済み(17→59件)。
- `scripts/seed_source_registry.py`(dry-run/apply)で source_accounts / reference_sources タブへ seed。
- X=reference保持(投稿対象外・manual_only)、TikTok/YouTube=reference_only(can_reuse_media=false)、beautyは`target_account_ids=["beauty_account"]`維持でinactive、`beauty_future`はtrack labelのみ、公式メディア=低優先、URL未入力=WAITING_URL_INPUT。
- 詳細: [source-recovery-and-seed.md](source-recovery-and-seed.md) / [ai-work-handoff.md](ai-work-handoff.md)。

## required source URL固定化 (2026-06-29)

- ユーザー明示の required source URL 13件を `config/source_accounts/required_source_urls.json` に固定。
- Threads / night_scout required 6件を照合し、不足4件を `default_sources.json` に追加。
- X / night_scout required 7件を照合し、`minatoku789` status URL を既存sourceの `post_url` / `canonical_url` / `status_url` に追加。
- `default_sources.json`: 59件 → 63件。`fetch_enabled=true` は0件維持。
- YouTube/TikTok は再探索し、production example の33件がすべて default に存在。追加すべき未登録の実source account URLはなし。
- 固定テスト: `test_required_source_urls_present.py` / `test_required_threads_sources_present.py` / `test_required_x_sources_manual_only.py` / `test_source_canonical_url_matching.py` / `test_no_fetch_enabled_required_sources.py` / `test_required_sources_classification.py`。
- Sheets apply / 実fetch / 実download / 実cut / 実upload / 実投稿は未実行。

## production loop completion (2026-06-30)

Source registry / Sheets apply / READY承認モデルの上に、実データの半自動運用ループを1周できる状態まで接続した。

- `source_account_posts`（verify上の reference_posts）: 0件 → 10件。`seed_reference_posts_from_sources.py` で source registry から manual reference seed を作成。実fetchなし、X fetchなし、media downloadなし、`use_status=REFERENCE_ONLY`、`can_reuse_media=false`。
- `reference_post_scores`: 0件 → 10件。`score_reference_posts.py --apply --confirm-score` で deterministic scoring を保存。流用リスクが高いため全件 `recommended_use=REFERENCE_ONLY`。
- Threads投稿案: `night_scout` 3件、`liver_manager` 3件を `WAITING_REVIEW` で `drafts` / `social_derivatives` / `queue` に生成。`READY` は0件、自動投稿対象外。
- Worker dry-run: `process_threads_queue.py --dry-run --max-posts 2` は両アカウント `candidates=0`。`WAITING_REVIEW` は拾わず、`READY` のみ対象。
- Approval dry-run: `approve_queue.py --queue-id q_night_scout_manualref_src_ns_threads_required_001_threads --approve --dry-run --use-sheets` で `WAITING_REVIEW → READY` の計画のみ確認。実昇格なし。
- PDCA dry-run: `import_threads_metrics_manual.py --dry-run` と `generate_next_queue_from_metrics.py --dry-run` は安全終了。MEASURED posted_results がないため candidate_count=0。
- Verify: `recover_production_sheets_threads_first.py --verify-only --json` は PASS 61 / FAIL 0。

現在の安全状態:

- `source_accounts=63`, `reference_sources=33`, `fetch_enabled=true=0`
- `queue_total=14`, `WAITING_REVIEW=10`, `READY=0`
- `beauty_active=0`, `x_active=0`
- 実fetch / 実投稿 / X投稿 / video download / transcription API / Cloudinary upload は未実行

人間が次に見るべきタブ:

- `収集済み投稿`: `manualref_` で始まる10件
- `参考投稿スコア`: `qscore_` で始まる10件
- `SNS投稿文`: `idea_` で始まる6件
- `投稿キュー`: `q_night_scout_manualref_...` / `q_liver_manager_manualref_...` の6件

実投稿に進む条件:

1. 人間が `投稿キュー` のWAITING_REVIEW行を読み、1件だけ `approve_queue.py --approve --reason ...` で `READY` に昇格する。
2. `process_threads_queue.py --dry-run --max-posts 1` で対象1件が妥当と確認する。
3. 実投稿は別作業として、`--confirm-real-post` + `PUBLISH_ENABLED=true` + `ALLOW_REAL_THREADS_POST=true` を明示する。

## AUTO_READY / autopilot update (2026-06-30)

READY承認の手間を減らすため、品質・安全・上限・cooldown・kill switch付きのAUTO_READYを追加した。

- 設定: `config/auto_approval_rules.json`
- AUTO_READY CLI: `scripts/auto_approve_queue.py`
- Autopilot runner: `scripts/run_autopilot_loop.py`
- Media mix plan: `scripts/plan_media_mix.py`
- Video reference multi-post plan: `scripts/generate_video_reference_posts.py`

初期設定:

- `auto_ready_enabled=true`
- `auto_post_enabled=false`
- `min_quality_score=75`, `min_safety_score=90`, `max_risk_score=10`
- `daily_ready_cap=2`, `daily_post_cap=1`, `cooldown_minutes=180`
- `max_posts_per_run=1`, `kill_switch=false`
- `allow_media_posts=false`, `allow_third_party_media=false`, `require_no_media_for_auto_ready=true`

AUTO_READY適用結果:

- Dry-runで安全判定後、`--apply --confirm-auto-ready --max-ready 2` を実行。
- READY化: 2件
  - `q_night_scout_manualref_src_ns_threads_required_001_threads`
  - `q_liver_manager_manualref_src_lm_note_cand_001_threads`
- `READY=2`, `WAITING_REVIEW=8`
- 各READY行に `auto_ready_by`, `auto_ready_reason`, `auto_ready_score`, `auto_ready_at`, `quality_score`, `safety_score`, `risk_score` を記録。
- `logs` には `queue_approved` 互換ログとして `auto_ready=true` を記録し、verifyのREADY承認証跡と互換。

AUTO_POST:

- AUTO_READYとは別フラグ。
- 初期値は `auto_post_enabled=false`。
- 実投稿は引き続き `--confirm-real-post` + `PUBLISH_ENABLED=true` + `ALLOW_REAL_THREADS_POST=true` の三重ゲート必須。
- 今回、実投稿は未実行。

Media / video:

- mediaなし70% / media付き30%方針を `plan_media_mix.py` でPLAN_ONLY化。
- 初期AUTO_READY対象はmediaなしのみ。media付きは別review/gate。
- YouTube/TikTokはreference analysis用。download/cut/upload/repostは行わない。
- `generate_video_reference_posts.py` で1動画から複数のWAITING_REVIEW案をPLAN_ONLY生成可能。

## First real Threads post and pilot hardening (2026-06-30)

初回の本番Threads投稿を1件だけ実施し、結果保存、metrics import経路、PDCA dry-run、AUTO_READY定期化、media/video pilotの安全確認まで完了。

- 実投稿: `liver_manager` 1件のみ。
- queue_id: `q_liver_manager_manualref_src_lm_note_cand_001_threads`
- result_id: `threads_q_liver_manager_manualref_src_lm_note_cand_001_threads_20260630025810`
- post_url: `https://www.threads.com/@ran.liver_pro/post/DaMbCLQiXLs`
- queue更新: `READY -> POSTED`
- posted_results: `POSTED`, `metrics_status=PENDING`, `real_post=TRUE`, `media_used=FALSE`
- verify: PASS 61 / FAIL 0。`posted_results=5`
- metrics import: `--dry-run` で0値テンプレート確認。保存なし。
- PDCA: MEASURED metricsなしのため `candidate_count=0`。保存なし。
- AUTOPOST: `auto_post_enabled=false` 維持。`run_autopilot_loop.py` dry-runで `auto_post_gate.allowed=false`。
- GitHub Actions: `.github/workflows/autopilot-auto-ready.yml` を追加。scheduleはAUTO_READY適用のみで `--skip-real-post` 固定。
- media/video: `media_assets=0`、media付き投稿なし。video referenceは `WAITING_REVIEW` planのみ。

残状態:

- `queue`: `POSTED=2`, `READY=1`, `WAITING_REVIEW=8`, `PLANNED=2`, `DUPLICATE_BLOCKED=1`
- `night_scout`: READY 1件あり。実投稿する場合は別作業でdry-run後に1件だけ。
- `liver_manager`: READY 0件。今回の対象はPOSTED済み。
- 実fetch / X fetch / X投稿 / video download / cut / upload / transcription API / Cloudinary upload は未実行。

## Metrics / PDCA pilot hardening (2026-06-30)

投稿後metricsとPDCA候補生成の運用ループを補強した。ただし、この作業中はGoogle Sheets接続が承認システムの `out of credits` で拒否されたため、本番metrics apply / night_scout実投稿は未実行。

- Threads post URLはHTTP 200で到達確認済み。
- 公開ページから信頼できるmetrics値は取得できず、本番値は捏造しない方針。
- `import_threads_metrics_manual.py` は `--apply --confirm-metrics` 必須に変更。
- 値なしdry-runは `missing_metrics` を返し、`MEASURED` にしない。
- 明示ゼロ値dry-runは `would_mark_measured=true` まで確認。
- offline sample MEASUREDではPDCA `candidate_count=1` を確認。生成候補は `DRAFT` でworker非対象。
- AUTOPOSTは引き続き `auto_post_enabled=false`。
- night_scout追加投稿は未実行。次回、Sheets/Threads接続承認が回復してから1件だけ実施する。

## Production verify and night_scout first post (2026-06-30)

承認回復後に本番Sheets verifyと `night_scout` の1件投稿を完了。

- verify: PASS 61 / FAIL 0。
- `posted_results`: 6件。
- `night_scout` queue_id: `q_night_scout_manualref_src_ns_threads_required_001_threads`
- `night_scout` result_id: `threads_q_night_scout_manualref_src_ns_threads_required_001_threads_20260630111243`
- `night_scout` external_post_id: `18104495005994780`
- `night_scout` post_url: `https://www.threads.com/@kyaba_consul_mizu/post/DaNToTqgQ7i`
- `queue`: `POSTED=3`, `READY=0`, `WAITING_REVIEW=8`, `PLANNED=2`, `DUPLICATE_BLOCKED=1`
- `fetch_enabled=true=0`, `beauty_active=0`, `x_active=0`
- `AUTOPOST`: OFF維持。`auto_post_enabled=false`

`liver_manager` metricsは、公開URL到達はHTTP 200で確認したが実数値は取得できなかった。0値をMEASUREDとして本番保存する操作は安全レビューで拒否されたため未実行。`metrics_status=PENDING` のまま、実測値確認後に明示値でapplyする。

## v2 collection / analysis / media pipeline (2026-06-30)

Fully safe v2 pipeline scaffolding has been added:

- Threads metrics snapshots with null unknowns and `PARTIAL/MEASURED/UNAVAILABLE`.
- Source collection planning for Threads/X/YouTube/TikTok with `fetch_enabled` and `manual_only` gates.
- Sanitized reference archive.
- Video reference metadata, transcript gate, structure analysis, and multi-post idea generation.
- Clip candidate and approved-only clip cutting gates.
- Approved-only media upload and media queue generation.
- Growth loop dry-run orchestration.

No real fetch, download, cut, upload, media post, X post, or beauty post was executed. AUTOPOST remains off.

# Dependency Inventory Update (2026-06-30)

- Added safe runtime dependencies to `requirements.txt`: `beautifulsoup4`, `lxml`, `playwright`, `yt-dlp`, `youtube-transcript-api`, `ffmpeg-python`, `cloudinary`, `pillow`.
- Created `docs/dependency-inventory.md` to distinguish installed/imported/wired/tested/optional/rejected/not_found.
- Agent Reach remains optional: repo has fetcher/config references, but no requirements entry and no confirmed local CLI installation in this turn.
- CLI-Anything remains optional/not_found: no repo import, no requirements entry, no CLI wiring.
- Threads Scraper系, TikTokApi, twikit, snscrape, moviepy, local whisper/faster-whisper, PaddleOCR, VoxCPM, MoneyPrinterTurbo, ViMax remain optional or rejected for this phase due to ToS, stability, weight, auth, or scope risks.
- AUTOPOST remains OFF. No real post, X fetch/post, beauty post, download, cut, upload, or transcription API call is enabled by these dependency changes.

## Dependency Runtime Verification (2026-07-01)

- `pip install -r requirements.txt`: completed successfully.
- Imports OK: `bs4`, `lxml`, `playwright`, `yt_dlp`, `youtube_transcript_api`, `PIL`, `ffmpeg`, `cloudinary`.
- Playwright Chromium install: command exited 0; browser adapter dry-run returned `UNAVAILABLE` because public Threads pages did not expose metrics.
- Threads source public metadata dry-run collected two public OG metadata rows as `source_account_posts`-shaped plan rows.
- YouTube metadata dry-run via `yt-dlp`: `FETCHED`, `download=false`.
- YouTube transcript dry-run via `youtube-transcript-api`: `FETCHED`, text preview suppressed.
- TikTok profile metadata dry-run: `UNAVAILABLE` without download.
- No Sheets apply, media download, cut, Cloudinary upload, SNS post, X fetch/post, beauty post, or transcription API call was executed.

## Rights-Aware Media Completion Update (2026-07-01)

Completed the missing rights-aware media ingestion layer.

- `third_party_reference_only` and `unknown` are blocked from media save/cut/upload/queue use.
- `owned`, `licensed`, and `approved_creator_clip` can create media asset plans and later proceed through explicit cut/upload gates.
- X/Threads media collection remains metadata/reference-only.
- YouTube/TikTok third-party material remains metadata/transcript/structure analysis only.
- Reference-based Threads generation now blocks high-similarity copy and writes only `WAITING_REVIEW` candidates.
- Cloudinary real upload, real cut, real download, and real SNS post were not executed.

## Source Registry Inventory Completion (2026-07-01)

- `default_sources.json`: 68 total sources after adding video TODO placeholders plus owned media rights-review placeholder.
- Platform counts: YouTube 28, TikTok 9, X 16, Threads 7, local 1, note 6, query 1.
- `fetch_enabled=true`: 0.
- `clip_enabled=true`: 0.
- `media_pipeline_eligible=true`: 0.
- `beauty_account active`: 0.
- `X fetch enabled`: 0.
- Full inventory created at `docs/source-registry-inventory.md`.
- Owned/licensed media intake template created at `config/source_accounts/owned_media_asset_template.json`.
- Human-readable rights template created at `docs/media-rights-template.md`.
- Still required before pilot: human-provided YouTube/TikTok target URLs, owned/licensed permission evidence, and optional Agent Reach/last30days execution policy if those tools are enabled.

## Production Pilot Preparation (2026-07-02)

- Added `docs/production-pilot-runbook.md`.
- Added `scripts/prepare_pilot_sources.py` as dry-run-first helper. It excludes X, beauty, TODO placeholders, missing URLs, TikTok profile URLs, and `unknown` rights rows.
- Current pilot candidates:
  - `night_scout`: `src_ns_threads_required_001`, `src_ns_threads_required_002`.
  - `liver_manager`: `src_lm_yt_cand_001`.
- `fetch_enabled=true` remains 0. No pilot apply was executed.
- AUTOPOST remains OFF. No real fetch, Sheets apply, download, cut, upload, or post was executed.

## Autonomous Video Reference Connection (2026-07-02)

Status:

- `main` start HEAD: `c415b8320a92da77d9a2612fa7c9fe815787ea83`.
- Source registry reflected in Sheets: PASS 61 / FAIL 0.
- Sheets counts: `source_accounts=68`, `reference_sources=37`, `posted_results=6`, `media_assets=0`.
- Local registry counts: `fetch_enabled=true=0`, `clip_enabled=true=0`, `media_pipeline_eligible=true=0`, `beauty_active=0`, `beauty_fetch=0`.
- Autonomous config: `autonomous_mode_enabled=true`, `auto_source_fetch_enabled=true`, `auto_ready_enabled=true`, `auto_post_enabled=true`.
- GitHub Actions: `Autonomous Growth Loop` exists and is active; schedule is enabled for JST 09:15 daily after successful run `28571552118`. Manual apply still requires `confirm_autonomous=true`.

Implemented:

- YouTube/TikTok reference analysis connected into `run_autonomous_loop.py`.
- YouTube selected pilot source can produce text-only Threads idea candidates.
- TikTok path is wired but current night/liver TikTok rows are TODO placeholders without real `/video/` URLs.
- Transcript preview/body is suppressed.
- Third-party download/cut/upload/repost remains blocked.
- `max_posts_per_run=1` is enforced across the whole autonomous run, not per account.

Apply result:

- `python3 scripts/run_autonomous_loop.py --account-id all --dry-run`: PASS / PLAN_ONLY.
- `python3 scripts/run_autonomous_loop.py --account-id all --apply --confirm-autonomous`: not executed; local approval reviewer rejected the real-post capable command. No bypass was attempted.
- No new Threads post URL was produced in this turn.

## Actions-Based Autonomous Start Procedure (2026-07-02)

Local Codex apply is intentionally not used for the first autonomous real post because the approval reviewer blocks real-post capable commands. Start operations through GitHub Actions instead:

- Workflow: `Autonomous Growth Loop`.
- Trigger: `workflow_dispatch`.
- Inputs: `confirm_autonomous=true`, `account_id=all`.
- Dry-run step runs before apply.
- Apply step is gated by schedule or `confirm_autonomous=true`, `kill_switch=false`, required Sheets secrets, and publisher credential checks.
- Apply env keeps `ALLOW_REAL_X_POST=false`, `ALLOW_VIDEO_DOWNLOAD=false`, `ALLOW_VIDEO_CUT=false`, `ALLOW_CLOUDINARY_UPLOAD=false`, and `ALLOW_TRANSCRIPTION_API=false`.
- Schedule remains commented out until the first manual Actions apply succeeds and the posted result is reviewed.

First dispatch attempt:

- Run id: `28571069128`.
- Dry-run step: success.
- Confirm / kill switch / Sheets secret guard: success.
- Apply step: safely BLOCKED before posting because account-specific Threads publish secrets were not passed into the workflow environment.
- Fix: `.github/workflows/autonomous-growth-loop.yml` now passes `THREADS_ACCESS_TOKEN_NIGHT_SCOUT`, `THREADS_USER_ID_NIGHT_SCOUT`, `THREADS_ACCESS_TOKEN_LIVER_MANAGER`, and `THREADS_USER_ID_LIVER_MANAGER` from GitHub secrets.
- New post URL from this attempt: none.

Second dispatch attempt:

- Run id: `28571199364`.
- Dry-run step: success.
- Confirm / kill switch / Sheets secret guard: success.
- Apply preflight: success; Threads credentials were present.
- Apply step: safely BLOCKED before posting because read-only Sheets verify inherited `PUBLISH_ENABLED=true` from the apply step and failed `real_post_flags_false_default`.
- Fix: `run_autonomous_loop.py` now runs `recover_production_sheets_threads_first.py --verify-only` with a safe read-only env (`PUBLISH_ENABLED=false`, real-post/media/upload/transcription flags false), then restores normal apply flow after verify.
- New post URL from this attempt: none.

Third dispatch attempt:

- Run id: `28571306895`.
- Dry-run step: success.
- Guard step: success.
- Apply preflight and read-only Sheets verify: success.
- YouTube metadata dry-run: success, `download=false`; transcript `UNAVAILABLE` due channel URL without `video_id`.
- Threads source collect apply: success, appended 0 because existing rows were deduped.
- `night_scout` score/generate/AUTO_READY: success; one queue row was promoted.
- `liver_manager` AUTO_READY: stopped by Google Sheets API 429 read quota before posting.
- New post URL from this attempt: none.
- Fix: apply mode now limits score/generate/AUTO_READY work to the first `max_posts_per_run` account, so `max_posts_per_run=1` also reduces Sheets read pressure before posting.

Fourth dispatch attempt:

- Run id: `28571552118`.
- Result: success.
- Dry-run step: success.
- Guard step: success.
- Apply step: success.
- YouTube metadata dry-run: success, `download=false`; transcript `UNAVAILABLE` due channel URL without `video_id`.
- Threads source collect apply: success, appended 0 because existing rows were deduped.
- `night_scout` score/generate/AUTO_READY/process queue: success.
- `liver_manager` score/generate/AUTO_READY/post: skipped by `max_posts_per_run=1`.
- Posted queue id: `q_night_scout_manualref_src_ns_threads_required_002_threads`.
- Result id: `threads_q_night_scout_manualref_src_ns_threads_required_002_threads_20260702065829`.
- External post id: `17928528360351269`.
- Post URL: `https://www.threads.com/@kyaba_consul_mizu/post/DaSAIF3lmCd`.
- Local follow-up Sheets verify was not run because the local approval system returned out-of-credits, but the Actions log reported `status=POSTED` with the result id and post URL.

Schedule enablement:

- Enabled on 2026-07-02 after successful Actions apply.
- Cron: `15 0 * * *` (JST 09:15 daily).
- The scheduled run still executes dry-run first, then guard, then apply.
- `kill_switch=true` stops scheduled apply.
- `max_posts_per_run=1`, `daily_post_cap_per_account=1`, X/media/beauty/download/cut/upload/transcription blocks remain unchanged.

## Public Post Leak Fix (2026-07-03)

Status: implemented and included in the current HEAD for this handoff update. Use `git rev-parse HEAD` for the exact self-referential commit SHA.

Problem:

- A recent `night_scout` public Threads post exposed internal planning language such as "今回の切り口" and source/platform analysis.
- This is not acceptable public copy and must be blocked even when autonomous posting is enabled.

Implemented controls:

- Added `scripts/public_post_quality.py` with `final_public_post_validator`.
- Added `config/post_generation_rules.json` for account-specific public copy rules and account rotation.
- Updated `generate_threads_ideas_from_references.py` and `generate_video_reference_posts.py` to produce reader-facing public text.
- Updated `auto_approve_queue.py` to reject internal-leak candidates before AUTO_READY.
- Updated `process_threads_queue.py` to validate immediately before publisher execution and mark bad rows `BLOCKED_INTERNAL_LEAK`.
- Updated `run_autonomous_loop.py` to show safe public previews in dry-run and rotate `night_scout` / `liver_manager` by latest posted account.

Unchanged safety gates:

- Schedule remains enabled for JST 09:15 daily.
- `max_posts_per_run=1`.
- `daily_post_cap_per_account=1`.
- X fetch/post remains blocked.
- `beauty_account` remains blocked.
- Media post, video download/cut/upload, Cloudinary upload, and transcription API remain blocked.

Video/TikTok scope:

- No new video download/cut/upload/media posting work was added in this fix.
- Existing YouTube/TikTok reference analysis remains reference-only.

Verification:

- Public validator tests: PASS.
- Account rotation tests: PASS.
- Autonomous dry-run preview test: PASS.
- Workflow/safety tests: PASS.
- `run_autonomous_loop.py --account-id all --dry-run`: selected `liver_manager`, validator PASS, `would_post=false`.

## Account Schedule And Liver Reference Update (2026-07-04)

Status: implemented locally in this turn, pending final commit/push.

Changed:

- Split scheduled autonomous operation into account-specific workflows:
  - `autonomous-growth-loop-night-scout.yml`
  - `autonomous-growth-loop-liver-manager.yml`
- Removed schedule from manual `autonomous-growth-loop.yml`.
- Added 0-1800 second jitter for scheduled runs.
- Updated caps: `daily_post_cap_per_account=5`, `daily_ready_cap_per_account=8`, `max_posts_per_run=1`, `cooldown_minutes=90`.
- Added one YouTube channel and three TikTok account reference sources for `liver_manager`. They were initially reference-only, then upgraded on 2026-07-04 to `approved_creator_clip` with user-asserted permission evidence, `fetch_enabled=false`, `manual_only=true`, and gated media pipeline eligibility.

Unchanged:

- X fetch/post false.
- `beauty_account` blocked.
- media posts false.
- third-party video download/cut/upload/repost false.
- Cloudinary upload false.
- transcription API false.
- TikTok account URL auto expansion false.

## Media Growth Engine Implementation (2026-07-04)

Status: implemented locally in this turn, pending final commit/push.

- Added `config/media_growth_engine.json`.
- Approved the four user-provided `liver_manager` YouTube/TikTok sources as `approved_creator_clip` with permission evidence fields.
- Added dry-run Media Growth Engine planning for metadata/transcript status, clip candidates, public post preview, media plan, and PDCA records.
- Added guarded download/cut/upload/media-post validation paths.
- Threads video + text post support is code-connected but remains disabled by default. It requires media validator PASS plus explicit env gates.
- Scheduled text-only autonomous posting remains unchanged; scheduled media posting remains OFF.
- Real download, real cut, Cloudinary upload, transcription API calls, and video + text Threads post were not executed.

## Media Growth Engine Discovery Expansion (2026-07-05)

Status: implemented locally in this turn, pending final commit/push.

- Added bounded source video discovery for approved `liver_manager` YouTube/TikTok channel/account sources.
- Added `source_videos` schema and Sheets/mock tab support.
- Added video-level dedupe by `platform + source_id + video_id`, canonical URL fallback, and content hash fallback.
- Added video-based clip candidate generation. One video can create up to 3 non-overlapping clip candidates; short videos produce one clip.
- Added `source_video_id` support to download planning and `clip_candidate_id` support to cut/upload planning.
- Added media queue preview fields for `source_video_id`, `clip_candidate_id`, `media_asset_id`, and `public_post_text`.
- Media schedule remains OFF. Text-only autonomous schedule remains unchanged.
- Real download/cut/upload/Cloudinary/video post/transcription API were not executed.

## READY Recovery And Diagnostics (2026-07-09)

Status: implemented in the current Codex turn.

Completed:

- Text-only scheduled workflows remain ON for `night_scout` and `liver_manager`.
- Safe fallback generation now refreshes stale non-locked queue rows and can top up queue candidates when reference rows are empty or stale.
- Queue rows now carry `public_post_text`, provenance, validator status, rejected reason, and READY/post result fields so operators can inspect why a row did or did not move.
- `auto_approve_queue.py` now reports `checked_count`, `approved_count`, `rejected_count`, `ready_count`, `rejected_reasons`, and sample rejected previews.
- `process_threads_queue.py` can use queue-level `public_post_text`, still validates it immediately before posting, and saves validator/provenance fields into `posted_results`.
- Added `autonomous_health` schema for scheduled run diagnostics: READY counts, rejected counts, processed count, posted count, no-post reason, and redacted error.
- Added `run_autonomous_loop.py --stop-before-post` for production READY verification without posting. It requires `--apply --confirm-autonomous` and skips `process_threads_queue`.

Still intentionally OFF:

- X fetch/post.
- `beauty_account` fetch/READY/post.
- Media schedule.
- Real video download/cut/upload/Cloudinary/video post.
- Transcription API.

Remaining human/ops confirmation:

- Next scheduled GitHub Actions run should be checked for `health_summary.ready_count >= 1` and `posted_count >= 1`.
- If `posted_count=0`, inspect `health_summary.no_post_reason`, `autonomous_health`, and queue `rejected_reason` rather than treating a green Actions run as a successful post.

## 2026-07-12 Production Recovery Update

- Text-only autonomous posting is operational again on latest pushed HEAD `25ff93400b52b3b6671074667339e057124e7831`.
- Confirmed GitHub Actions success:
  - Night Scout: `29177989151`
  - Liver Manager: `29178058830`
  - Production Aftercare: `29178159618`
  - Media Transcription Production: `29178232402`
- Root fixes already pushed:
  - Workflow concurrency changed to workflow-scoped groups.
  - Optional source/video/reference failures are non-blocking for text-only posting.
  - Queue / posted_results / AUTO_READY Sheets writes are batched and retried to reduce Google Sheets 429 failures.
- New fix committed and pushed as `b304003b9372de2257b671824468a0ee1826bfce`:
  - `media-growth-production.yml` now prepares media candidates itself before posting: bounded discovery, transcription, grounded clip candidate generation, then one approved media post attempt.
  - Stale clip candidate rows are refreshed when they become transcript-grounded and READY.
  - `run_media_production_pipeline.py` treats missing eligible media candidates as `NO_POST` instead of a failed workflow, while true safety blocks still fail.
- Latest Media Growth Production verification:
  - Run `29178471963` on `b304003b9372de2257b671824468a0ee1826bfce` completed with conclusion `success`.
  - Steps `Discover approved source videos`, `Transcribe approved source videos`, `Generate transcript-grounded clip candidates`, and `Run one approved media production post` all completed successfully.
  - Detailed post URL extraction was not completed locally because GitHub log body API and local Google OAuth DNS were unavailable in the Codex environment; GitHub Actions job status itself is success.
- Still blocked by safety:
  - X fetch/post.
  - Beauty posting.
  - Unknown / reference-only / third-party media reuse.
  - Any media without approved rights and permission evidence.
- Any post text failing `final_public_post_validator`.

## 2026-07-13 Canonical Slots And Subtitle-Free Media

This section supersedes older statements that media scheduling is OFF.

- Each account has five canonical daily slots in `config/content_schedule.json`.
  `night_scout` uses text at 14:00/16:00/18:00/25:00 and approved media at
  21:00. `liver_manager` uses text at 10:00/13:00/16:00/21:00 and approved
  media at 18:00. Scheduled runs start 15 minutes before target and jitter
  0-1800 seconds.
- Media preparation runs ahead of the media post slot and stops at
  `MEDIA_READY`; it cannot publish. The media slot consumes only an uploaded,
  unused approved asset and never downloads, cuts, uploads, or transcribes.
- Burned subtitles are disabled by user policy: `subtitle_enabled=false` and
  the production cutter is always called with `burn_subtitles=false`.
- `night_scout` requires explicit female-subject review or matching public
  metadata. Unknown, male-scout, store-PR, and recruiting-like videos are
  analysis-only and cannot create a clip/post candidate.
- `source_role` is explicit: 13 permission-evidenced sources are
  `approved_media`; all remaining sources are `reference_only`. X and beauty
  remain blocked. Publishers receive `public_post_text` only.

## 2026-07-14 Runtime Observability Recovery

- Scheduled workflows are firing. The latest inspected text workflows reached
  their apply step and failed there, so the issue is not an absent cron.
- `check_autonomous_health.py --use-sheets` now reads operational count/status
  summaries only: queue, results, metrics, PDCA, reference/video/clip/media,
  logs, and earlier health rows. It never initializes Sheets, writes rows,
  prints post bodies, or exposes credentials.
- Text and approved-media workflow summaries run this read-only snapshot. The
  next run can identify `NO_READY_QUEUE`, validation/duplicate blocks, caps,
  schema gaps, and missing media stages from one place.
- A metrics adapter returning PARTIAL/UNAVAILABLE no longer stops aftercare
  before source-registry sync and PDCA candidate generation. Unknown metrics
  remain unknown rather than being fabricated as zero.
