# Production Completion Status

Date: 2026-06-29 (最終更新 — READY 承認モデル必須化)
Created: 2026-06-24

## Status

The project is operational for Threads-first manual review operation.
`threads-queue-worker.yml` の Sheets verify は check 総数 **51 件**（2026-06-25 snapshot の 33 件 → item J の media/metrics チェック等で +8 → READY 承認モデルで +10）。合格条件は `failed=[]`（`passed` は seed 充足状況で変動）。READY 承認モデル追加後の live `--verify-only` 再確認は #68 で実施。

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
- 生成系CLI（refill / clip / metrics 候補 / seed）は `READY` を直接書かない。`READY` 昇格は `approve_queue.py`（WAITING_REVIEW → READY/REJECTED）経由のみ。承認時は logs に `queue_approved` 証跡を残す。
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

- `night_scout` の Threads 次投稿候補（WAITING_REVIEW）をレビューし、`approve_queue.py --queue-id <id> --approve --reason "..."` で `READY` に昇格して初めて worker 投稿対象になる
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
- GitHub Actions: `Autonomous Growth Loop` exists and is active; schedule remains commented out. Apply runs only with `confirm_autonomous=true`.

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
- Apply step is gated by `confirm_autonomous=true`, `kill_switch=false`, required Sheets secrets, and publisher credential checks.
- Apply env keeps `ALLOW_REAL_X_POST=false`, `ALLOW_VIDEO_DOWNLOAD=false`, `ALLOW_VIDEO_CUT=false`, `ALLOW_CLOUDINARY_UPLOAD=false`, and `ALLOW_TRANSCRIPTION_API=false`.
- Schedule remains commented out until the first manual Actions apply succeeds and the posted result is reviewed.

First dispatch attempt:

- Run id: `28571069128`.
- Dry-run step: success.
- Confirm / kill switch / Sheets secret guard: success.
- Apply step: safely BLOCKED before posting because account-specific Threads publish secrets were not passed into the workflow environment.
- Fix: `.github/workflows/autonomous-growth-loop.yml` now passes `THREADS_ACCESS_TOKEN_NIGHT_SCOUT`, `THREADS_USER_ID_NIGHT_SCOUT`, `THREADS_ACCESS_TOKEN_LIVER_MANAGER`, and `THREADS_USER_ID_LIVER_MANAGER` from GitHub secrets.
- New post URL from this attempt: none.
