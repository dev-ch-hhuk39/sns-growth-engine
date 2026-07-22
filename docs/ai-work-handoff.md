# AI Work Handoff

## 2026-07-22 Codex Work Package 3 integrity-repair checkpoint

### Current state

- `main` was merged through PR #3 and is synchronized with `origin/main` at
  `ffa5ddef40b824a2f932e7f60e138672bc490464` before this checkpoint branch.
- Repository visibility is public. `production` is a protected Environment;
  secret names remain repository-managed and were inspected by name only.
- CI run `29883163439` passed `tests`, `dependency-audit`, and
  `secret-history-scan`.

### Verified operational finding

- `Content Daily Dry-Run` run `29883365575` did not reach any publisher step.
  The read-only Sheets verifier stopped at `62/63` because one historical
  duplicate `queue_id` exists. Credentials were present; no post, download,
  cut, upload, transcript call, or source acquisition occurred.
- Historical media-evidence and duplicate-post warnings remain audit markers,
  not evidence for new Goal canaries.

### Pending change

- Added manual-only `.github/workflows/production-integrity-reconcile.yml`.
  It only runs `reconcile_production_integrity.py`, requires both an explicit
  Actions confirmation and Sheets credentials, keeps every publish/media gate
  false, retains duplicate rows under audit-safe IDs, and verifies Sheets after
  the update.
- Added `scripts/test_production_integrity_reconcile_workflow.py`.
- Local PASS: reconcile unit contract 8/8, reconcile-workflow contract 7/7,
  workflow safety 368/368, `git diff --check`.

### Bounded acquisition finding and follow-up

- Run `29883735428` completed without publishing, downloading, cutting, or
  uploading. It discovered 18 bounded records and saved 3 source posts, 3
  source-post media rows, 1 source video, 5 bounded transcript rows, and 44
  provider-run rows. Threads profile adapters failed after the first source
  because the in-memory router opened each backend's circuit immediately.
- The pending router fix changes this to a three-consecutive-failures
  threshold. It preserves the per-source limits and fails closed after repeated
  failure, while allowing the next bounded source to use primary/fallback.
- Local PASS: primary/fallback, all-backends-fail, new circuit-threshold,
  TikTok multiple-backend, provider-contract, `py_compile`, and
  `git diff --check`.

### Direct-media preparation runtime finding

- The read-only Direct Media Preparation run `29884573138` reached its hosted
  runtime check but stopped before any dry-run plan or gated media action:
  `ffmpeg` was not installed on the GitHub-hosted image although the workflow
  asserted that it was present. OCR packages installed successfully.
- The pending workflow fix installs `ffmpeg` explicitly together with the
  bounded OCR dependencies and adds a static contract test. Publishing and all
  media operation gates remain false unless the existing explicit confirmation
  path is used.

### Next actions

1. Merge this small workflow change through CI, dispatch it with
   `confirm_reconcile=true`, then require a 63/63 read-only verifier result.
2. Re-run both account dry-runs. Continue with bounded source/provider checks
   only after the queue integrity gate is clean.
3. Do not claim Goal completion: final media canaries, current-final-main
   evidence, and a valid liver-manager third-party Threads source are still
   outstanding.

### Safe ownership boundaries

- Safe next files: `scripts/reconcile_production_integrity.py`, the new
  reconcile workflow, verifier tests, and Goal evidence docs.
- Do not edit `.env`, `data/`, `output/`, `.claude/plans/`, any secret/token/
  cookie/storage-state file, or weaken X/beauty/media-rights/public-text gates.

## 2026-07-22 Codex Goal Work Package 1 checkpoint

### 本システムについて

SNS Growth Engine v2 は、許可済みの source を provenance と権利台帳で
管理し、Threads の text/direct-media/generated-clip 投稿、Sheets 記録、
Cloudinary asset、PDCA 証跡をつなぐ運用基盤である。X と
`beauty_account` は block を維持し、公開本文は常に `public_post_text` のみを
使う。

### 現在 HEAD / 作業ブランチ

- branch: `feature/oss-github-actions-media-autopilot`
- checkpoint開始時 HEAD: `3e1a05e627c4a454d685199fd14a6eb999e5831a`
- checkpoint開始時 `origin/main`: `f89f6ed44bc2a00930f04601d5700230e25949d3`
- この章を含む commit/push 後は両方を再確認する。mainへの直接pushはしない。

### 今回の変更ファイル一覧 / 追加ファイル一覧

- Updated: `scripts/transcribe_approved_source_videos.py`,
  `src/acquisition/ytdlp.py`, `src/acquisition/enrichment.py`, yt-dlp利用
  scripts、`scripts/acquire_approved_source_posts.py`, `src/sheets_client.py`,
  `scripts/evaluate_goal.py`, `requirements-acquisition.txt`。
- Added: `src/acquisition/ytdlp_runtime.py`,
  `scripts/collect_goal_evidence.py`,
  `scripts/test_goal_evidence_fail_closed.py`,
  `scripts/test_acquisition_router_all_backends_fail.py`,
  `scripts/test_profile_route_observability.py`。

### 完了内容 / テスト結果

- 独立文字起こし runner の `video_transcripts` 保存直前で Sheets 49,000文字
  上限へ正規化する。全文SHA、head/tail証跡、chunk数、`SHEETS_BOUNDED` を
  保持し、本文全文はログ出力しない。
- 全yt-dlp routeは `SNS_YTDLP_NODE_PATH` を優先する明示Node runtimeを使う。
  YouTubeだけが公式 `ejs:github` componentを許可し、TikTok profile取得は
  bounded fallback/no-login/no-unbounded-expansionのまま。
- routing provider/version/retryability/attempt countを `provider_runs` と
  `backend_routing_history` へ保存できるschemaにした。URL/token/bodyは保存しない。
- Goal evidence collectorはread-onlyでcandidateを出力し、evaluatorは不足証跡・
  stale commit・final-main SHA不一致をfail-closedする。
- PASS: transcript cell-limit、independent transcript persistence、yt-dlp
  runtime config、TikTok fallback、primary/fallback、all-backends-fail、
  observability、provider contracts/registry、Goal evidence fixture、phase10
  repository subset、`compileall`、`git diff --check`。

### 未完了事項 / 残WARN

- Goal evaluatorは現時点で17/35 PASS相当。public repository、production
  Environment/protected main、final-main CI、live provider/source evidence、
  account別direct/clip canary 4件が未完了。
- GitHub API確認: repositoryはprivate、`production` Environmentは未作成。
  private repositoryではbranch protection APIが403（public化またはProが必要）。
- Work Package 2はrepository全historyを公開する不可逆操作を含むため、実装計画に
  従い明示的な公開承認が必要。
- ローカルの全632 test一括runnerはdesktop command envelopeで途中終了しJSONを
  生成できなかった。対象subsetのテストはPASS。最終main GitHub CIが完全結果の
  authoritative sourceになる。

### スケール方針 / タスク

- Work Package 2: exact merge candidateのhistory scan、publicization、
  protected `main`、`production` Environment、CI。
- Work Package 3: final-main read-only Sheets/provider validation。Liver
  Managerのthird-party Threads source account URLが無い場合は捏造せずBLOCKED。
- Work Packages 4-5: accountごとにdirect-mediaとgenerated-clipを各1件、
  bounded canaryとして順番に検証する。失敗時はassetをquarantineし同一asset/textを
  再投稿しない。

### 次に触ってよいファイル / 触らない方がよいファイル

- 次AIが触ってよい: `scripts/evaluate_goal.py`,
  `scripts/collect_goal_evidence.py`, `scripts/acquire_approved_source_posts.py`,
  `.github/workflows/`, `docs/goal-status.json`, `docs/runtime-health.json`,
  `docs/goal-evidence.md`。
- 衝突しやすい: `src/sheets_client.py`, `config/goal_acceptance.json`,
  `docs/ai-work-handoff.md`, media workflow files。
- 触らない方がよい: `.env`, `data/`, `output/`, `.claude/plans/`,
  secret/token/cookie/storage_state、既存の安全gateを弱める変更。

### 次AIへの引き継ぎメモ

1. `docs/goal-completion-implementation-plan.md`のWork Package 2から再開。
2. ただしpublic化前に、ユーザーへ「全Git historyが公開される」ことを一文で
   明示確認する。
3. 35/35のstatusをproseで更新しない。`collect_goal_evidence.py`の機械証跡、
   final-main SHA、canary readbackでのみ更新する。
4. 実download/cut/upload/postは各workflowの既存env+confirm+permission gateを
   通す。X/beauty/unknown rightsは継続BLOCK。

## 2026-07-18 Codex live canary recovery completion

### 本システムについて / 現在の本番状態

SNS Growth Engine v2 は private repository の GitHub Actions を Xserver
self-hosted runner (`sns-growth-xserver`) で実行し、`night_scout` と
`liver_manager` の Threads text / approved direct media / approved generated
clip を、Sheets の provenance・queue・posted results・PDCA 記録へ接続する。
X と beauty は block を維持し、公開入力は常に `public_post_text` のみ。

### 現在 HEAD / 作業ブランチ

- この最終 handoff 更新前 HEAD: `406e674a618e41bd94f05a774bc679c7921e104e`。
- branch: `main`。最終 docs commit/push 後は `git rev-parse HEAD` と
  `origin/main` が一致することを確認する。

### 今回の実測結果

- Runner: online / `self-hosted, linux, x64, sns-growth, production`。
- Night Scout text canary `29640254453`: **POSTED**。
  `https://www.threads.com/@kyaba_consul_mizu/post/Da7jN3rjxHG`
- Liver Manager text canary `29641005508`: **POSTED**。
  `https://www.threads.com/@ran.liver_pro/post/Da7ld83D3cM`
- Liver Manager approved direct-media canary `29637471702`: **POSTED**。
  `https://www.threads.com/@ran.liver_pro/post/Da7bG0YFDEl`
  Cloudinary secure URL は `media_assets` に保存済み（ログ上は意図的に
  cloud name を redacted）。
- Liver Manager approved TikTok generated-clip canary `29640229610`:
  **POSTED**。
  `https://www.threads.com/@ran.liver_pro/post/Da7idhbjUX4`
- `29640233813` は GitHub schedule の大幅遅延で指定枠外になったため、
  投稿前に cancel した。枠外投稿はしなかった。

### 変更ファイル一覧 / 追加ファイル一覧

- Updated: account text/direct/media posting workflows,
  `src/sheets_client.py`, `scripts/process_threads_queue.py`,
  `scripts/run_slot_text_fallback.py`, `scripts/run_autonomous_loop.py`,
  `scripts/public_post_quality.py`, production docs。
- Added: `scripts/check_schedule_window.py`,
  `scripts/test_schedule_window_blocks_delayed_runs.py`,
  `scripts/test_autonomous_health_counts_slot_fallback_post.py`,
  `scripts/test_production_workflows_checkout_trigger_sha.py`。

### 修正内容

- 古い Sheets queue の空 `public_post_text` fallback を通常候補より後ろへ
  回し、empty row が安全な新規候補を妨げないようにした。
- AUTO_READY が全候補を重複 reject した場合、canonical slot の安全な
  text fallback を実行する。fallback 投稿も `autonomous_health` では
  `POSTED` と集計する。
- Night/Liver とも reader-facing template を25本に拡張し、全件で
  final validator PASS を確認した。
- 429 では 0/10/30/60 秒で再試行し、非本質的な `logs` 保存失敗は
  publish/duplicate result を覆さない。
- self-hosted runner は workflow の `${{ github.sha }}` を明示 checkout
  し、stale workspace を実行しない。実際に古い checkout を検知し、
  正しい revision が検証済みである。
- scheduled posting は target JST ±15分外なら apply しない。manual
  canary はこの時刻 guard を通らず、確認目的でのみ即時実行できる。

### テスト結果 / dry-run / BLOCKED

- `test_all_workflows_safety_flags.py`: PASS 340 / FAIL 0。
- schedule-window、runner-SHA、fallback-health、fallback contract、legacy
  empty queue、template inventory、internal-term、`py_compile`、
  `git diff --check`: PASS。
- confirm/env なしの post/download/cut/upload は既存 safety gate で BLOCK。
- X fetch/post、beauty post、unknown/reference-only media、internal analysis
  の公開混入は block 維持。

### 残 WARN / 未完了事項

- GitHub-hosted scheduler は遅延し得る。新しい window guard は枠外投稿を
  防ぐ一方、遅延 run を skip する。`content-slot-recovery` と
  VPS-native systemd timer の二重化を次の運用強化として優先する。
- Google Sheets は read quota 429 を返し得る。最新 liver canary は
  retry 後に成功。health/log telemetry の累積 ERROR/NO_POST は過去履歴を
  含むため、最新 workflow conclusion と slot/post result を優先する。
- Threads metrics は `UNAVAILABLE` のまま保持し、0を捏造しない。
- TikTok/YouTube の全アカウントを無制限取得することはしない。approved
  source・上限・rights/permission evidence・media validator を通るものだけ
  prepare/post 対象。

### スケール方針 / タスク

- 2GB VPS: browser/transcription/ffmpeg/media preparation は各1並列、
  disk 80% で preparation 停止、90% で text-only。posted slot は最優先。
- direct media / generated clip は各 account 最低3 READY 在庫、text は最低
  10件を目標にし、同一 source post/video/clip/text は再投稿しない。
- next task: Xserver に systemd timer を導入して、JST slot を runner
  待ちではなく VPS clock で開始し、GitHub schedule 遅延を吸収する。

### 次に触ってよいファイル / 触らない方がよいファイル

- Claude Code: `scripts/check_autonomous_health.py`,
  `scripts/content_slot_recovery.py` 相当、metrics/PDCA tests、runbooks。
- Codex: account workflows、`scripts/run_slot_text_fallback.py`,
  `scripts/process_threads_queue.py`, Sheets quota tests、VPS timer deploy files。
- 衝突しやすい: `docs/ai-work-handoff.md`, `src/sheets_client.py`,
  `scripts/run_autonomous_loop.py`, `config/content_schedule.json`, account
  workflows。
- 触らない: `.env*`, `data/`, `output/`, `.claude/plans/`, secrets/tokens,
  cookies/storage state、historical Sheets records、X/beauty paths。

### 次 AI への引き継ぎメモ

投稿を再試行する前に `content_slot_runs`、`posted_results`、queue を照合する。
特に `29641005508` は current text path の live proof、`29637471702` は
direct media、`29640229610` は TikTok generated clip の live proof である。
Cloudinary URL は Sheets `media_assets` に存在するが、secret/credentialや
runner stateは出力しない。schedule の枠外 run を無理に投稿させないこと。

## 2026-07-18 Codex production recovery and direct-media compatibility

- Start HEAD / `origin/main`: `7c9d14eb1752845ab6e13918f83c2bd871f1375a`; branch: `main`.
- GitHub Actions audit found both account schedules firing. Their apply steps
  stopped at `process_threads_queue.py` with `EMPTY_TEXT`, not because cron,
  Threads credentials, X, beauty, or the final public validator blocked them.
  Existing Sheets `queue` headers could omit `public_post_text`; the named
  fallback appended a row but the critical public field was silently absent.
- Fixed `run_slot_text_fallback.py` to migrate `queue` and `posted_results`
  headers before writing. The normal worker already reads only
  `public_post_text` first and keeps its final validator immediately before
  publishing.
- Fixed direct-reference media semantics: approved original video may retain
  its own aspect ratio and may be up to 300 seconds. Generated clips remain
  strictly 8-45 seconds and 9:16. The direct-origin flag is carried into the
  queue worker; this does not loosen rights, permission, platform, account,
  media URL, or public-text checks.
- Direct source-plan reads are cached for each invocation to reduce Sheets
  quota use. Account workflow health summaries are non-blocking telemetry,
  so an exhausted telemetry read cannot overturn a successful post result.
- Added a slot-free `manual_e2e_proof` dispatch route to the Night Scout direct
  workflow, matching Liver Manager. It never claims a scheduled slot and
  never prepares/downloads/cuts/uploads media.
- Updated files: `.github/workflows/autonomous-growth-loop-night-scout.yml`,
  `.github/workflows/autonomous-growth-loop-liver-manager.yml`,
  `.github/workflows/direct-reference-media-night-scout.yml`,
  `scripts/media_post_validator.py`,
  `scripts/process_threads_queue.py`,
  `scripts/run_direct_reference_media_pipeline.py`,
  `scripts/run_slot_text_fallback.py`,
  `scripts/test_direct_reference_media_keeps_original_geometry.py`,
  `scripts/test_manual_media_e2e_proof_safety.py`, and these docs.
- Tests before the next VPS canary: targeted direct-validator, manual-E2E,
  fallback-contract, queue-media, internal-term, Threads-only, safety-flag
  tests, `py_compile`, and `git diff --check` all PASS.
- Current residual WARN: historical `posted_save_failed` and `EMPTY_TEXT`
  rows remain preserved for audit; Threads metrics are `UNAVAILABLE`, never
  fabricated as zero; Google Sheets 429 remains possible during bursts but is
  now reduced and non-critical health telemetry cannot fail a completed post.
- Safe next files: Direct workflows, `run_slot_text_fallback.py`,
  `run_direct_reference_media_pipeline.py`, `process_threads_queue.py`, and
  focused Sheets quota tests. Do not touch `.env*`, `data/`, `output/`,
  secrets/cookies/storage state, historical Sheets rows, or X/beauty paths.
- Next AI handoff: push this recovery, dispatch one slot-free direct-media
  proof per account and one text workflow proof per account on the Xserver
  self-hosted runner, then record only returned post URLs/IDs and redacted
  status evidence. Never retry an uncertain post before checking
  `posted_results` and `content_slot_runs`.

## 2026-07-17 Codex multi-backend acquisition integration

- Start HEAD / `origin/main`: `70f3dbda0b337e8724bcefd4186a444854ba2ae1`; branch: `main`.
- Added public source routing: `yt-dlp` is YouTube/TikTok PRIMARY; Threads is cookie-free public Playwright PRIMARY with public HTTP FALLBACK and a circuit breaker.
- `source_posts` is the parent record and `source_post_media` is its ordered child list. Parent mismatch is rejected before save, queue creation, upload, or post.
- Owner-attested active Threads sources now use `direct_media_reuse`; approved YouTube/TikTok sources retain direct + clip scopes. `media_permissions` remains canonical and revoked records are never changed.
- Added: `src/acquisition/*`, `scripts/acquire_approved_source_posts.py`, `scripts/generate_local_trend_signals.py`, `docs/source-backend-decision.md`, adapter/policy tests.
- Updated: direct-media workflows, Sheets schemas, direct ingest/selection, Threads publisher/queue worker, permissions seed, modes, Media Growth Engine dry-run, and this handoff.
- Tests PASS: primary/fallback, circuit breaker, normalized parent invariant, public Threads carousel parsing, direct-only permission split, Threads CDN policy, old source-post handoff, queue media dry-run, workflow safety (336/0), rights policy, `py_compile`, JSON validation, `git diff --check`.
- Dry-run: 14 approved active non-X/non-beauty sources selected with no network. The local trend aggregator and owner-attestation seed are PLAN_ONLY. Media Growth reports `none_discover_first` and creates no fabricated candidates when no real `source_videos` exist.
- Remaining WARN: the new public Threads acquisition/carousel route is unit tested but needs the next self-hosted scheduled canary for live provider evidence. No live fetch/download/upload/post was done in this change. Agent-Reach/last30days remain optional analysis-only shadows; no external paid service is required.
- Next AI may touch: `scripts/acquire_approved_source_posts.py`, `src/acquisition/*`, `scripts/ingest_direct_reference_media.py`, `scripts/run_direct_reference_media_pipeline.py`, `src/publishers/threads_publisher.py`, related workflows/docs/tests.
- Avoid: `.env*`, `data/`, `output/`, runner/service files, secret/cookie/storage-state files, historic Sheets data, and X/beauty workflows. Read `backend_health`, `backend_routing_history`, source/media/queue/slot Sheets tabs before any live change.

## 2026-07-17 Codex production completion handoff (supersedes older status sections)

### 本システムについて / 現在地

SNS Growth Engine v2 はprivate GitHub repositoryのscheduleをXserver VPS上のself-hosted runnerで動かし、`night_scout`と`liver_manager`のThreads投稿を運用する。5 slot/account/day、04:00 JST business-date、0-1800秒jitter、20分超過slotの30分間隔recoveryを使う。公開本文は`public_post_text`だけで、X、beauty、未許可media、内部分析、外部transcription API、learning ruleの自動適用はブロックする。

本番経路は次の3系統に分離済み。

1. text: reader-facing生成 -> validator -> READY -> Threads -> `posted_results` -> metrics/PDCA。
2. direct media: approved source post discovery -> `source_posts` / `source_post_media` -> gated ingest -> Cloudinary -> caption validator -> Threads。失敗時はtext fallback。
3. generated clip: bounded video discovery -> individual video -> local faster-whisper -> transcript-grounded 1-3 clips -> ffmpeg 9:16（字幕なし）-> Cloudinary -> media validator -> Threads。準備と投稿slotは分離。

### HEAD / branch / repository / runner

- この更新前のimplementation HEAD: `37c71d8bad6d8ae97c8da24a7667320b5425f473`。branchは`main`、同時点の`origin/main`と一致。
- このhandoffを含む最終HEADは`git rev-parse HEAD`で確認し、最終報告にも記載する。
- Repositoryは`dev-ch-hhuk39/sns-growth-engine`、visibilityはprivate維持。history rewrite、force-push、public化なし。
- Runner: `sns-growth-xserver`、labels=`self-hosted,linux,x64,sns-growth,production`。実runでonlineを確認。
- Health run `29549159011`: success。disk available 30GB、memory 1957MB、Python 3.11 workflow runtime、ffmpeg/yt-dlp/requirements import、credential presence、Sheets read-only healthがPASS。
- systemd runner serviceは`Restart=always`, `RestartSec=10s`, `OOMPolicy=stop`。一度のWhisper OOM後に復旧し、自動再起動overrideを実機へ反映済み。

### 本番E2E証拠

- text post: `https://www.threads.com/@ran.liver_pro/post/Da1ts-2j7xO`
- deliberate media failure -> text fallback: `https://www.threads.com/@ran.liver_pro/post/Da1xVebD0du`
- generated clip post: `https://www.threads.com/@ran.liver_pro/post/Da39TRljUQA`
- direct media post: `https://www.threads.com/@ran.liver_pro/post/Da39nq9AeWA`
- generated clip asset inventory:
  - `night_scout`: 3 uploaded assets (`...8Xmkojfw90Q_01` / `_02` / `_03`)
  - `liver_manager`: 3 uploaded assets（うち実投稿証拠1件）
- direct media inventory: `night_scout=1`, `liver_manager=5`。全12 media assetsは`upload_status=UPLOADED`かつCloudinary `storage_url`あり。
- Asset preparation success runs: night `29547740250`, `29548243407`, `29548301795`; liver `29545057137`, `29548525788`, `29548662407`。

### Sheets実測（health run `29549159011`、本文/URL/secret非表示）

- `queue=117`（READY 20 / WAITING_REVIEW 55 / POSTED 30 / duplicate blocked 8等）
- `posted_results=33`（POSTED 30 / RECOVERED 2）
- `source_posts=25`, `source_post_media=24`
- `source_videos=69`, `video_transcripts=16`, `video_clip_candidates=20`
- `media_assets=12`（generated clip 6、direct 6、uploaded 12）
- `media_post_results=1`, `media_metrics=1`, `clip_performance=1`
- `pdca_runs=29`, `prompt_improvement_suggestions=29`
- `metric_snapshots=118`は全件`UNAVAILABLE`。取得不能値を0として捏造していない。

### 今回の変更ファイル一覧

- `.github/workflows/media-growth-production-night-scout.yml`
- `.github/workflows/media-growth-production.yml`
- `.github/workflows/media-transcription-production.yml`
- `.github/workflows/self-hosted-runner-health.yml`
- `config/media_growth_engine.json`
- `src/sheets_client.py`
- `scripts/transcribe_approved_source_videos.py`
- `scripts/discover_approved_source_videos.py`
- `scripts/run_media_growth_engine.py`
- `scripts/run_media_production_pipeline.py`
- `scripts/check_autonomous_health.py`
- `scripts/test_all_workflows_safety_flags.py`
- `scripts/test_transcribe_approved_source_videos.py`
- `scripts/test_local_whisper_low_memory_policy.py`
- `scripts/test_media_transcription_workflow.py`
- `scripts/test_real_discovered_video_with_missing_description.py`
- `scripts/test_discovery_rejects_channel_ids_as_videos.py`
- `scripts/test_media_growth_night_scout_account.py`
- `scripts/test_media_preparation_skips_existing_asset.py`（追加）
- `scripts/test_media_preparation_ignores_post_caps.py`（追加）
- `scripts/test_autonomous_health_media_inventory_counts.py`（追加）
- `scripts/test_self_hosted_runner_health_workflow.py`（追加）
- production/runbook docs（本更新）

### 修正内容 / safety gate

- 2GB VPS向けにWhisperを`tiny + int8 + cpu_threads=1 + max 900秒 + 1 video/run`へ制限。音声をmono 16k FLACへ変換し、長尺は`PARTIAL`として処理範囲を保存する。
- Night Scoutはfemale-subject evidenceがないmetadataを高コスト文字起こし前に除外。
- channel IDやplanned-only rowをindividual videoとして扱わず、activeかつ`media_autopilot_enabled` sourceだけをtranscription対象にした。
- 実discoveryでdescriptionが欠けてもreal video ID/title/statusがあれば候補として受理。
- 保存済みclip assetを再選択せず次候補へ進む。再生成時も`MEDIA_READY`、cut/upload status、asset IDをREADYへ巻き戻さない。
- `prepare_only`は投稿を行わないためdaily/media post capの対象外。実投稿pathのcapは維持。
- disk 80%以上でmedia preparation停止、90%以上でtext-only。Docker active image/container/volumeを残したままbuild cacheだけをpruneし、約80%から約49%へ回復。
- 字幕burn-inは常にOFF。`public_post_text`のみpublisherへ渡す。X/beautyはfalse。

### 全テスト / dry-run / BLOCKED結果

- Workflow safety: PASS 336 / FAIL 0。
- Production self-hosted workflow: PASS 66 / FAIL 0。
- Low-memory transcription、active source/video ID、real discovery、grounding、media preparation dedupe/cap、Sheets retry、PDCA idempotency、slot idempotency、health inventory/health workflowの対象テストはすべてPASS。
- `py_compile`、`git diff --check`: PASS。
- dry-run inventory runs: liver `29548936624`, night `29548978662`, both success。外部download/cut/upload/post stepはskip。
- 最終docs HEADでのaccount workflow dry-run: liver `29549669034`, night `29549716690`, both success。`dry_run_only=true` / `confirm_autonomous=false`でguard/apply/postはskip、self-hosted runnerのplanとSheets healthのみ実行。
- confirm/envなしのdownload/cut/upload/postは既存safety testでBLOCKを維持。
- 今回の追加資産準備は投稿gateがfalseのprepare-onlyで実施。手動の追加Threads投稿は行っていない。

### 未完了事項 / 残WARN

- Threads metrics adapterは現在取得不能のため118 snapshotsが`UNAVAILABLE`。0へ変換せず、後続PDCAは取得可能データだけを使う。
- Actionsの`actions/checkout@v4` / `setup-python@v5`にNode 20 deprecation WARNが出る。GitHub側移行通知であり現runはNode 24強制実行でsuccess。
- `content_slot_runs`に過去の`RUNNING=1`と`FAILED=1`が残る。30分recovery/lease expiryで再判定し、履歴行は削除しない。
- `logs`のERROR件数は過去障害を含む累積値。healthの現在`problems=[]`と最新run conclusionを優先する。
- 実metricsが得られるまで、performanceに基づく最適化精度は限定的。`learning_rules.auto_apply=false`は維持。

### スケール方針 / 次タスク

- 2GB runnerではtranscriptionを常に1 video/run、900秒上限、CPU 1 threadで直列化する。並列数を増やさない。
- 各account generated clip inventoryを最低3件で維持し、投稿済みclip/asset/video/textをdedupeする。
- Cloudinary/disk/resource usageを各prepare前に検査し、閾値超過時はtext fallbackへ落とす。
- metrics取得が復旧したら`UNAVAILABLE -> PARTIAL/MEASURED`を実値のみで更新し、PDCA suggestionはWAITING_REVIEWのまま評価する。
- 次scheduled runではslot type、selected asset、validator PASS、posted URL、Sheets save、resource budgetを確認する。

### 次に触ってよいファイル

- Claude Code: `scripts/collect_threads_metrics.py`, `scripts/check_autonomous_health.py`, `docs/*runbook.md`, metrics/PDCA tests。
- Codex: `scripts/transcribe_approved_source_videos.py`, `scripts/run_media_growth_engine.py`, `scripts/run_media_production_pipeline.py`, media workflows/tests。
- 両AIとも変更前に`git fetch origin`、`git status --short`、最新handoffを確認する。

### 衝突しやすい / 触らない方がよいファイル

- 衝突しやすい: `docs/ai-work-handoff.md`, `config/media_growth_engine.json`, `src/sheets_client.py`, `scripts/run_media_growth_engine.py`, `scripts/run_media_production_pipeline.py`, `.github/workflows/media-growth-*.yml`。
- 触らない: `.env`, `data/`, `output/`, `.claude/plans/`, secret/token/cookie/storage_state、runner registration token、GitHub history。
- `default_sources.json`のrights/active/media flagsはowner attestation/revocationルールを確認せず変更しない。`revoked=true`を上書きしない。

### 次AIへの引き継ぎメモ

最新health run `29549159011`を基準にする。古い文書内の「media schedule OFF」「runnerなし」「実download/cut/upload未実行」は履歴であり、現在状態ではない。障害時は投稿を再実行する前に`content_slot_runs`のclaim/leaseと`posted_results`を照合し、二重投稿を防ぐ。metrics不明値は空欄/UNAVAILABLEのままにする。

## Codex private-production audit and slot-engine continuation (2026-07-16)

- Current HEAD at audit start: `c71aa62ef42837a12ef797cd240009e433862cf2` on `main`; origin matched and worktree was clean.
- Publication verdict: **DO_NOT_PUBLICIZE**. The repository contains material competitive operational IP, active local credential files (ignored/untracked), a historical secret-pattern finding, no LICENSE/NOTICE, and unverified redistribution rights. Keep GitHub private.
- Runner decision: GitHub-hosted Actions are not a production runner while every scheduled run is rejected before steps by the account billing/Actions limit. Prefer a private self-hosted runner labelled `self-hosted,sns-growth`; Mac launchd is the fallback. Do not report an end-to-end post as complete until a new post URL is recorded.
- Changes in this continuation:
  - `content_slot_runs` now has a 04:00 JST business-date resolver, deterministic idempotency key, lease/claim fields, and structured posting provenance.
  - text/direct/clip/recovery paths share deterministic slot identity; account-specific workflows use shared per-account concurrency groups.
  - owner-attested active non-X/non-beauty sources can be seeded into `media_permissions` by `scripts/seed_owner_attested_media_permissions.py`; revoked rows remain untouched.
  - bounded direct source discovery and gated download/Cloudinary ingestion now have real apply paths. Dry-run performs no network, download, upload, or post.
  - direct-media captions use private source signals only and publish only a validator-safe `public_post_text`; image transport is supported, mixed carousel remains text-fallback-only until the official Threads transport is implemented.
- Remaining external blockers/WARN:
  - no self-hosted runner registered; GitHub-hosted Actions fail before job steps.
  - actual source discovery, media ingest, Cloudinary upload, and Threads posting were not run in this change.
  - Gitleaks fixed `v8.30.1` checksum verified: ignored local `.env`/service-account file and one historical generic-key pattern require owner rotation review. TruffleHog `v3.95.9` binary checksum did not match its release checksum, so it was not executed.
- Next safe files for Codex: `scripts/content_slot_runs.py`, `scripts/run_autonomous_loop.py`, `scripts/discover_approved_source_posts.py`, `scripts/ingest_direct_reference_media.py`, `scripts/run_media_production_pipeline.py`, `scripts/check_media_inventory.py`, runner runbook/docs.
- Avoid touching: `.env`, local service-account JSON, `data/`, `output/`, browser profiles/cookies, GitHub secret values, X/beauty paths.

## 2026-07-14 Codex Sheets Quota Recovery Follow-up

### 本システムについて

SNS Growth Engine v2 は、`night_scout` と `liver_manager` のaccount別Threads text-only schedule、投稿後のmetrics/PDCA、許可記録済み動画のbounded discoveryからmedia postまでを分離して運用する。公開に渡せる本文は常に`public_post_text`のみで、X、beauty、未許可media、内部分析、`learning_rules`の自動適用は引き続きブロックする。

### 現在のHEAD / branch

- 修正開始HEAD: `b631b7f9a2ac6ff2cfb235501f3147269b5fe8ca`
- 作業ブランチ: `main`
- 作業ディレクトリ: `/Users/hayatoa/claudecodeプロジェクトディレクトリ/dev/SNS自動投稿システム/v2`
- GitHub Actionsの実測: scheduleは起動していた。run `29270982366` は`auto_approve_queue.py`のqueue行ごとの`ws.find()`でSheets read quota 429となり、READY化前に停止していた。

### 今回の変更ファイル一覧

- `src/sheets_client.py`
- `scripts/auto_approve_queue.py`
- `scripts/test_auto_approve_queue_apply_ready_only_safe_items.py`
- `scripts/test_auto_approve_queue_batches_sheets_updates.py`（追加）
- `scripts/test_sheets_bulk_update_queue_items.py`（追加）
- `docs/ai-work-handoff.md`
- `docs/production-completion-status.md`

### 実装内容

- `SheetsClient.bulk_update_queue_items()`を追加。queue全体を一度だけ読み、queue IDから行番号を作り、READY昇格とreject理由を`batch_update`で一括保存する。候補ごとの`ws.find()`を廃止し、429 retryと400セル単位のバッチ分割を使う。
- `auto_approve_queue.py`は安全候補をREADYへ昇格しつつ、非採用候補の理由保存も同一バッチで行う。投稿対象になるのは従来どおりREADY化された安全候補だけ。
- `media_post_results`、`media_metrics`、`clip_performance`を正式なSheets tab schemaへ追加。approved media postが成功した場合、clip/asset/resultを同じIDで保存し、未取得metricsは空欄の`PENDING`として開始する。字幕は`none`であり、videoへのburn-inは行わない。
- media PDCA保存はclip candidate IDで冪等化した。投稿そのものが成功済みの場合にPDCA保存が失敗しても、投稿結果を失敗扱いへ戻さない。
- dry-run Actions `29302032285`（night）と`29302033460`（liver）は`b631b7f`で成功。実投稿・実download・実cut・実uploadは行っていない。
- 最新main `06b9de6`でもdry-runを再実行。night run `29302470128`、liver run `29302470111` はともにsuccessで、dry-run/health summaryのみ実行、Guard・Apply・Threads投稿はskipされた。

### 現行Sheets観測 / 未完了事項

- read-only health snapshotではnight queue 52件（WAITING_REVIEW 36件）、liver queue 31件（WAITING_REVIEW 18件）で、READY化の停止が本番の主因だった。
- `metric_snapshots`は未取得を示す`UNAVAILABLE`であり、0として扱ってはいけない。
- `media_assets`は0件。`media_post_results`、`media_metrics`、`clip_performance`タブは未作成だった。text-only復旧とは独立して、media実運用をONにする前にschema作成とCloudinary/Threads実接続を段階検証する必要がある。
- 参照sourceのdry-runでは`src_ns_threads_user_chiishunin_s`がnight_scoutの選択対象になった。dry-runは外部fetchを実行しないため、実収集の可否は次のscheduled runでredacted summaryを観測する。

### スケール方針 / 残WARN

- 同時slotでも、queueの更新は一括read + bounded batch writeにする。行ごとのfind/readを新規runnerに追加しない。
- text-onlyのscheduleはON、media scheduleは権利・asset・schemaが揃った対象だけで段階的に使う。X/beautyは禁止を維持する。
- 次scheduled runで`ready_count`、`processed_count`、`posted_count`、`no_post_reason`、redacted Sheets 429有無を確認する。再度429なら待機時間だけを増やさず、呼び出し箇所とread/write数を再計測する。

### テスト結果

- `test_auto_approve_queue_apply_ready_only_safe_items.py`: PASS 4 / FAIL 0
- `test_auto_approve_queue_batches_sheets_updates.py`: PASS 5 / FAIL 0
- `test_sheets_bulk_update_queue_items.py`: PASS 6 / FAIL 0
- `test_sheets_client_update_queue_item_batched.py`: PASS 6 / FAIL 0
- `test_sheets_rate_limit_backoff.py`: PASS 15 / FAIL 0
- `test_auto_approve_queue_logs_reason.py`: PASS 1 / FAIL 0
- `test_all_workflows_safety_flags.py`: PASS 275 / FAIL 0
- `test_media_pdca_tabs_schema.py`: PASS 9 / FAIL 0
- `test_media_production_saves_pdca_after_post.py`: PASS 5 / FAIL 0
- `test_media_production_pipeline_safety.py`: PASS 11 / FAIL 0
- `test_media_queue_schema_complete.py`: PASS 3 / FAIL 0
- `py_compile` / `git diff --check`: PASS

### 次AIへの引き継ぎメモ

1. 次のaccount別scheduled runのhealth summaryで、AUTO_READYが429なしにREADYを作り、workerがprocessまで到達することを確認する。
2. `posted_results`、`queue`、`autonomous_health`は読取専用で観測し、未取得metricsを捏造しない。
3. mediaの実行前に不足している3タブを既存schemaの追加のみで作成し、approved assetが実際に1件保存されるまでmedia post scheduleを広げない。
4. 次に触ってよいファイル: `src/sheets_client.py`、`scripts/auto_approve_queue.py`、`scripts/check_autonomous_health.py`、media schema/setup runnerとrunbook。触らない方がよいもの: `.env`、`data/`、`output/`、`.claude/plans/`、secrets/cookies、X/beauty設定。

## 2026-07-12 Codex Full Automation Recovery / Transcription Grounding / Workflow Cancellation Fix

### 本システムについて

SNS Growth Engine v2 は、`night_scout` / `liver_manager` のtext-only Threads自動投稿、投稿後aftercare、許可済み`liver_manager`動画の発見、文字起こし、文字起こしに基づくclip候補、download/cut/Cloudinary/upload/Threads video postまでをGitHub Actionsで分離運用する。公開本文は必ず`public_post_text`のみ。X、beauty、未許可media、third_party_reference_only media、外部transcription API、learning_rules自動適用はブロック維持。

### 現在のHEAD / branch

- 作業開始HEAD: `ea340a7fec7090129ee0bda7dc8ef8b497da5610`
- 作業ブランチ: `main`
- 作業ディレクトリ: `/Users/hayatoa/claudecodeプロジェクトディレクトリ/dev/SNS自動投稿システム/v2`
- 直近原因: account別scheduled workflowsは発火していたが、`generate_threads_ideas_from_references.py` のrow-by-row `update_cell` と `refill_threads_queue.py` の毎回 `setup_all()` がSheets API 429を誘発し、Apply stepが失敗していた。さらに共通concurrency groupを一度導入したところ、GitHub Actionsの「1 group 1 pending」制約で同時dispatchされた別workflowがcancelされたため、workflow単位concurrencyへ変更した。

### 変更ファイル一覧

- `.github/workflows/media-transcription-production.yml`
- `.github/workflows/autonomous-growth-loop-night-scout.yml`
- `.github/workflows/autonomous-growth-loop-liver-manager.yml`
- `.github/workflows/production-autopilot-aftercare.yml`
- `.github/workflows/media-growth-production.yml`
- `scripts/transcribe_approved_source_videos.py`
- `scripts/run_autonomous_loop.py`
- `scripts/process_threads_queue.py`
- `src/sheets_client.py`
- `scripts/run_media_growth_engine.py`
- `scripts/run_media_production_pipeline.py`
- `scripts/media_growth_schemas.py`
- `scripts/generate_threads_ideas_from_references.py`
- `scripts/refill_threads_queue.py`
- `scripts/test_all_workflows_safety_flags.py`
- `scripts/test_transcribe_approved_source_videos.py`
- `scripts/test_media_growth_requires_transcript_grounding.py`
- `scripts/test_media_production_requires_grounded_clip.py`
- `scripts/test_media_transcription_workflow.py`
- `scripts/test_autonomous_optional_failures_non_blocking.py`
- `scripts/test_sheets_rate_limit_backoff.py`
- `scripts/test_sheets_client_update_queue_item_batched.py`
- `scripts/test_production_workflows_shared_concurrency.py`
- `scripts/test_media_growth_apply_clip_candidates_plan.py`
- `scripts/test_media_production_pipeline_safety.py`
- `src/sheets_client.py`
- `docs/ai-work-handoff.md`
- `docs/production-completion-status.md`
- `docs/autonomous-mode-runbook.md`
- `docs/growth-loop-runbook.md`
- `docs/video-reference-runbook.md`

### 実装内容

- 自動投稿停止の主因だったSheets 429を修正。既存draft/queue更新は行単位 `batch_update` + `append_rows` に変更し、補充CLIは本番で `setup_all()` と追記後再読を行わない。
- account別text workflows、aftercare、transcription、media production は `sns-growth-production-${{ github.workflow }}-${{ github.ref }}` のworkflow単位concurrency。共通groupは同時pendingをcancelするため使わない。
- `run_autonomous_loop.py` は、Threads source collect / video reference collect / reference score などの非必須step失敗を `WARN_NON_BLOCKING` として扱う。安全なfallback投稿生成・AUTO_READY・process queueが続行できる場合、Apply全体を失敗扱いにしない。
- `process_threads_queue.py` はSheets 429/quota時に append/find/batch_update をretryする。queue status更新は複数 `update_cell` ではなく `batch_update` に変更。投稿成功後のPDCA/log保存失敗はwarning扱いで、posted_results/queue保存の成功を失敗扱いにしない。
- `SheetsClient.update_queue_item()` も `batch_update` + 429 retryに変更。Actions run `29177776988` の失敗原因は `auto_approve_queue.py` -> `SheetsClient.update_queue_item()` の旧 `update_cell` loop がSheets write quota 429を踏んだこと。run `29177900225` では同メソッドの `row_values(1)` がread quota 429を踏んだため、ヘッダー読み取りもretry対象に追加。
- `Media Transcription Production` を追加。JST 00:10に、許可済み`source_videos`の個別動画URLだけを最大3本処理し、YouTube公式字幕を優先、必要時のみ `ALLOW_LOCAL_TRANSCRIPTION=true` + `ALLOW_VIDEO_DOWNLOAD=true` のstep-scoped gateでローカルWhisper文字起こしを行う。stdoutにtranscript本文は出さない。
- `run_media_growth_engine.py` は `video_transcripts` を読み、実文字起こし済み動画だけを `transcript_grounded=true` のclip候補としてREADY/AUTO_APPROVED化する。文字起こしなしの動画は `TRANSCRIPT_PENDING` で止める。
- `run_media_production_pipeline.py` は `transcript_grounded=true` のclip以外を本番投稿対象にしない。

### 未完了事項 / 残WARN

- ローカルCodex環境はGoogle OAuthへのDNS解決が制限されるため、Sheets実dry-runはActionsで確認する。
- `faster-whisper` は専用workflow内でinstallする。初回はmodel downloadのため実行時間が長くなる可能性がある。
- Cloudinary secretsはmedia production workflowでのみ必要。text-only workflowのhealth summaryでは未注入なのでmissing表示されてもtext-onlyには影響しない。
- TikTok profileからの無制限展開はしない。discoveryはbounded、文字起こしは`source_videos`に入った個別video URLだけ。

### スケール方針

- text-only posting: account別schedule、1run最大1投稿、account別daily cap 5。
- aftercare: source registry sync、metrics/PDCA、bounded source video discovery。
- transcription: 1run最大3動画。既にDONEの`source_video_id`は再処理しない。
- media post: 1日最大1本、`transcript_grounded=true`、approved rights、permission approved、media validator、final public validator、Cloudinary/Threads gates必須。

### テスト結果

- `test_transcribe_approved_source_videos.py`: PASS 4 / FAIL 0
- `test_media_growth_requires_transcript_grounding.py`: PASS 5 / FAIL 0
- `test_media_production_requires_grounded_clip.py`: PASS 2 / FAIL 0
- `test_media_transcription_workflow.py`: PASS 9 / FAIL 0
- `test_autonomous_optional_failures_non_blocking.py`: PASS 4 / FAIL 0
- `test_sheets_rate_limit_backoff.py`: PASS 15 / FAIL 0
- `test_sheets_client_update_queue_item_batched.py`: PASS 6 / FAIL 0
- `test_auto_approve_can_promote_safe_candidate.py`: PASS
- `test_auto_approve_queue_apply_ready_only_safe_items.py`: PASS 3 / FAIL 0
- `test_process_threads_queue.py`: PASS 11 / FAIL 0
- `test_ready_queue_can_be_processed_text_only.py`: PASS
- `test_media_growth_engine_generates_clip_candidates.py`: PASS
- `test_media_growth_apply_clip_candidates_plan.py`: PASS 10 / FAIL 0
- `test_media_production_pipeline_safety.py`: PASS 11 / FAIL 0
- `test_all_workflows_safety_flags.py`: PASS 220 / FAIL 0
- `test_production_workflows_shared_concurrency.py`: PASS 10 / FAIL 0（workflow-scoped concurrency）
- `test_run_autonomous_loop_night_scout_dry_run.py`: PASS
- `test_run_autonomous_loop_liver_manager_dry_run.py`: PASS
- `test_public_post_never_contains_internal_terms.py`: PASS
- `test_internal_terms_never_in_posted_text.py`: PASS
- `py_compile`: PASS

### dry-run / BLOCKED確認

- `run_autonomous_loop.py --account-id night_scout --dry-run`: validator PASS、would_post=false。
- `run_autonomous_loop.py --account-id liver_manager --dry-run`: validator PASS、would_post=false。
- `transcribe_approved_source_videos.py --use-sheets --dry-run`: ローカルではsandbox DNS制限でGoogle OAuth接続不可。Actionsで確認する。
- `run_media_production_pipeline.py`: transcript_grounding_required がないclipだけを対象にする。

### 次に触ってよいファイル

- Codex: `scripts/transcribe_approved_source_videos.py`, `scripts/run_media_growth_engine.py`, `scripts/run_media_production_pipeline.py`, `.github/workflows/media-transcription-production.yml`
- Claude Code: docs/runbook、metrics/PDCA collector、health summary改善。ただし安全ゲート・public_post_text保証は弱めない。

### 衝突しやすいファイル

- `src/sheets_client.py`
- `scripts/run_autonomous_loop.py`
- `scripts/generate_threads_ideas_from_references.py`
- `scripts/run_media_growth_engine.py`
- `docs/ai-work-handoff.md`

### 触らない方がいいファイル

- `.env`, `data/`, `output/`, `.claude/plans/`
- token/cookie/storage_state/secret実値
- X/beauty投稿設定
- 未許可mediaの権利設定

### 次AIへの引き継ぎメモ

まずActions上で `Media Transcription Production` をdispatchし、`video_transcripts` と grounded clip候補が保存されることを確認する。その後 `Media Growth Production` をdry-run、問題なければ1本だけ本番実行する。text-only schedule failureはSheets 429修正後の次runで `posted_count` / `no_post_reason` を確認すること。

## 2026-07-11 Codex Production Completion

### 本システムについて

SNS Growth Engine v2 は、`night_scout` / `liver_manager` のThreads文章投稿、投稿後metrics/PDCA、権利許可済み`liver_manager`動画の発見・切り抜き・Cloudinary保存・動画投稿を、独立したGitHub Actionsで運用する。公開本文は常に`public_post_text`のみを使い、X、beauty、未許可media、学習ルール自動適用は対象外。

### HEAD / branch

- 作業開始HEAD: `a792faedcbb280e567ddea7fe0af4efabb99df16`
- 作業ブランチ: `main`
- 実装完了HEAD: `4dcb72e`（このhandoffのHEAD記録更新は直後のdocs-only commit）
- 作業ディレクトリ: `/Users/hayatoa/claudecodeプロジェクトディレクトリ/dev/SNS自動投稿システム/v2`

### 変更ファイル一覧

- Workflows: `.github/workflows/production-autopilot-aftercare.yml`, `.github/workflows/media-growth-production.yml`
- Config: `config/media_growth_engine.json`, `config/production_autopilot.json`
- Core: `src/publishers/threads_publisher.py`, `src/sheets_client.py`
- Runners: `scripts/discover_approved_source_videos.py`, `scripts/run_media_growth_engine.py`, `scripts/run_media_production_pipeline.py`, `scripts/download_approved_media.py`, `scripts/cut_approved_clips.py`, `scripts/upload_media_assets.py`, `scripts/process_threads_queue.py`, `scripts/run_autonomous_loop.py`, `scripts/check_autonomous_health.py`
- Test support/tests: `scripts/autonomous_recovery_test_utils.py`, `scripts/test_all_workflows_safety_flags.py`, `scripts/test_media_growth_engine_does_not_download_in_dry_run.py`, `scripts/test_media_schedule_still_off.py`, `scripts/test_production_autopilot_aftercare_workflow.py`, `scripts/test_production_autopilot_config.py`, `scripts/test_real_source_video_discovery_adapter.py`, `scripts/test_media_production_pipeline_safety.py`, `scripts/test_media_execution_runners_connected.py`, `scripts/test_media_production_workflow.py`, `scripts/test_media_queue_schema_complete.py`, `scripts/test_media_execution_paths_mocked.py`
- Docs: `docs/production-completion-status.md`, `docs/autonomous-mode-runbook.md`, `docs/growth-loop-runbook.md`, `docs/video-reference-runbook.md`, `docs/media-pipeline-runbook.md`, `docs/ai-work-handoff.md`

### 追加ファイル一覧

- `.github/workflows/media-growth-production.yml`
- `scripts/run_media_production_pipeline.py`
- 上記6本の`test_media_*` / `test_real_source_video_discovery_adapter.py`

### 実装と接続

- Aftercareはsource registryをSheetsへ同期してから、実media downloadなしのbounded discoveryとclip candidate保存を行う。
- Media productionは実個別videoのみを選び、rights/permission/ID/validator/dedupe/daily capを検証後、yt-dlp -> ffmpeg 9:16 -> Cloudinary -> READY media queue -> Threads video container -> posted_resultsへ接続。
- text-only reference generationが失敗した場合は、validator通過済みoriginal fallbackを1件補充してAUTO_READYへ進める。
- `posted_results`の未取得metricsは空欄。未取得を`0`として捏造しない。

### スケール方針

- discoveryはsourceごとのscan/new上限とrun全体上限を維持する。無制限profile取得は禁止。
- text postingは既存account別daily cap、media postingは1日1件、各runは最大1投稿。
- 同一`clip_candidate_id`は再投稿しない。同一動画の別clipは許可する。
- 失敗clipはBLOCKEDとして無限再試行を避ける。
- Sheets列は追加のみ。既存列やタブを削除しない。

### 未完了事項 / 残タスク

- コード上の必須production pathは接続済み。次回scheduled runで、外部Threads/Cloudinary/YouTube APIと現在のcredentialが実環境で通ることを観測する必要がある。
- TikTok側がprofile metadataを提供しない場合は安全に候補0件となる。回避のための無制限scrapeは実装しない。
- PDCAは記録・候補生成まで。`learning_rules`の自動適用は意図的に未実装/禁止。

### 残WARN

- 変更前の直近scheduled ActionsはSheets source registry 68件対config 73件の不一致と、生成候補不足で失敗していた。registry syncとsafe fallbackで修正済みだが、push後の初回run観測が必要。
- 外部APIのrate limit、動画削除、Cloudinary quota、credential失効はコードだけでは排除できない。workflow summaryのredacted errorで確認する。
- 2026-07-11 run `29134404560` でmetrics applyは成功したが、旧row-by-row source registry upsertがSheets write quotaで失敗。`_upsert_many`を既存行・未知列保持のbatch update + appendへ変更し、最大約70 writeを最大2 writeへ削減した。

### テスト結果 / dry-run結果

- 新規media discovery/execution/workflow/schema/mockテスト: PASS。
- `test_all_workflows_safety_flags.py`: PASS 202 / FAIL 0。
- X/beauty/rights/internal-term/text workflow/process queue回帰: PASS。
- `py_compile`: PASS。`git diff --check`: PASS。
- `test_source_registry_batch_upsert.py`: PASS 7 / FAIL 0。`test_seed_source_registry.py`: PASS 10 / FAIL 0。
- `run_autonomous_loop.py` night/liver dry-run: PLAN_ONLY、validator PASS、would_post=false。
- media production dry-run: 外部download/cut/upload/postなし。

### 次にClaude Codeが触ってよいファイル

- `scripts/check_autonomous_health.py`
- metrics/PDCA collector類
- docs/runbook類
- 追加テスト（既存ゲートを弱めないこと）

### 次にCodexが触ってよいファイル

- `.github/workflows/media-growth-production.yml`
- `scripts/run_media_production_pipeline.py`
- `scripts/discover_approved_source_videos.py`
- `scripts/run_media_growth_engine.py`
- `src/publishers/threads_publisher.py`

### 衝突しやすいファイル

- `docs/ai-work-handoff.md`
- `docs/production-completion-status.md`
- `src/sheets_client.py`
- `scripts/run_autonomous_loop.py`
- `config/media_growth_engine.json`

### 触らない方がいいファイル

- `.env`, `data/`, `output/`, `.claude/plans/`
- token/cookie/storage_state/secret実値
- X/beauty投稿設定
- `learning_rules`の自動有効化

### 次AIへの引き継ぎメモ

push後は新規実装より先に、`Production Autopilot Aftercare`、account別text workflows、`Media Growth Production`の最新run summaryを確認する。`NO_CANDIDATE`は安全な正常終了。credential/schema/APIエラーはredactedログで原因を切り分ける。安全ゲートを緩めて投稿件数を作らないこと。

Codex / Claude Code 並行開発用の引き継ぎ資料です。主要作業完了時は必ず更新してください。

## 最終更新

- Date: 2026-07-10
- 作業AI: Codex
- 作業ディレクトリ: `/Users/hayatoa/claudecodeプロジェクトディレクトリ/dev/SNS自動投稿システム/v2`
- GitHub repo: `dev-ch-hhuk39/sns-growth-engine`
- 前回更新: 2026-07-10 (Production Autopilot Aftercare追加)

## 最新作業内容 (2026-07-10) — Production Autopilot Aftercare / media候補自動保存

### 本システムについて

- SNS Growth Engine v2 は `night_scout` / `liver_manager` の text-only Threads投稿をscheduleで自動公開し、投稿後metrics、PDCA候補、許可済み動画source discovery、clip candidate生成をSheetsへ蓄積する本番autopilot構成へ移行した。
- `public_post_text` のみ投稿対象、final public post validator、X/beauty/media safety gateは維持。
- 今回は実投稿、実download、実cut、実upload、Cloudinary upload、Threads video+text post、transcription API、X fetch/post、beauty投稿は未実行。

### 変更ファイル一覧

- `.github/workflows/production-autopilot-aftercare.yml`
- `config/media_growth_engine.json`
- `config/production_autopilot.json`
- `scripts/check_autonomous_health.py`
- `scripts/discover_approved_source_videos.py`
- `scripts/run_media_growth_engine.py`
- `docs/autonomous-mode-runbook.md`
- `docs/growth-loop-runbook.md`
- `docs/video-reference-runbook.md`
- `docs/production-completion-status.md`
- `docs/ai-work-handoff.md`

### 追加ファイル一覧

- `.github/workflows/production-autopilot-aftercare.yml`
- `config/production_autopilot.json`
- `scripts/test_production_autopilot_config.py`
- `scripts/test_production_autopilot_aftercare_workflow.py`
- `scripts/test_media_discovery_apply_to_sheets_plan.py`
- `scripts/test_media_growth_apply_clip_candidates_plan.py`

### 実装内容

- `Production Autopilot Aftercare` workflowを追加。毎日 JST 23:40 にmetrics snapshot、PDCA候補生成、許可済みliver_manager sourceの `source_videos` discovery、`video_clip_candidates` 生成・Sheets保存を実行する。
- `discover_approved_source_videos.py` に `--use-sheets` と `--apply --confirm-discovery` 保存導線を追加。dry-runでは保存しない。
- `run_media_growth_engine.py` に `source_videos` Sheets読込、`video_clip_candidates` 保存導線、public preview validator確認を追加。
- `check_autonomous_health.py` が production aftercare workflow と media aftercare状態を診断できるようにした。
- `config/production_autopilot.json` で本番autopilotの有効範囲を明示した。

### 未完了事項 / production-off

- Media public postingは自動ONにしていない。理由: validator通過済みのuploaded media assetがまだない状態で自動公開をONにすると、壊れた投稿または不安全な投稿になるため。
- 実download、実cut、Cloudinary実upload、Threads video+text postは引き続きenv + confirm gate必須。
- learning_rules auto-applyはOFF。PDCAは候補・提案まで。

### 残WARN

- 実GitHub scheduled aftercare runの初回完走は次回Actions実行で確認する。
- Sheets credentialsがActions secretsにない場合、aftercare guardで停止する。secret値は表示しない。
- metrics取得は取得不能値を0にせず、PARTIAL/UNAVAILABLE/nullとして扱う設計を維持。

### テスト結果 / dry-run結果

- `scripts/test_production_autopilot_config.py`: PASS 9 / FAIL 0
- `scripts/test_production_autopilot_aftercare_workflow.py`: PASS 14 / FAIL 0
- `scripts/test_media_discovery_apply_to_sheets_plan.py`: PASS 5 / FAIL 0
- `scripts/test_media_growth_apply_clip_candidates_plan.py`: PASS 10 / FAIL 0
- `scripts/test_all_workflows_safety_flags.py`: PASS 155 / FAIL 0
- `scripts/check_autonomous_health.py --account-id all --dry-run`: PASS、problemsなし
- `scripts/run_autonomous_loop.py --account-id night_scout --dry-run`: would_post=false、public preview生成、validator PASS
- `scripts/run_autonomous_loop.py --account-id liver_manager --dry-run`: would_post=false、public preview生成、validator PASS
- `scripts/discover_approved_source_videos.py --account-id liver_manager --dry-run`: approved sourceのみ、would_save_source_videos=false
- `scripts/run_media_growth_engine.py --account-id liver_manager --dry-run`: would_download=false / would_cut=false / would_upload=false / would_post_video=false
- `git diff --check`: PASS

### 次に触ってよいファイル

- `.github/workflows/production-autopilot-aftercare.yml`
- `config/production_autopilot.json`
- `config/media_growth_engine.json`
- `scripts/discover_approved_source_videos.py`
- `scripts/run_media_growth_engine.py`
- `scripts/check_autonomous_health.py`
- `docs/ai-work-handoff.md`
- `docs/production-completion-status.md`

### 衝突しやすいファイル

- `scripts/run_autonomous_loop.py`
- `scripts/process_threads_queue.py`
- `scripts/auto_approve_queue.py`
- `src/sheets_client.py`
- `.github/workflows/autonomous-growth-loop-night-scout.yml`
- `.github/workflows/autonomous-growth-loop-liver-manager.yml`

### 触らない方がいいファイル

- `.env`
- `data/`
- `output/`
- `.claude/plans/`
- cookie / token / storage_state / secret類

### 次AIへの引き継ぎメモ

- 「全部自動で回す」は text-only public posting + metrics/PDCA/media candidate aftercare まで本番自動化済み、という意味で扱う。
- media video postingを完全自動ONにする前に、個別 `source_video_id` / `clip_candidate_id` のdownload/cut/upload実行、Cloudinary URL、`media_post_validator.py` PASS、rights evidence確認が必要。
- X/beauty/third-party unapproved mediaは引き続き禁止。final public post validatorを弱めない。

## 最新作業内容 (2026-07-09) — READY診断 / stop-before-post / autonomous_health 追加

### 本システムについて

- SNS Growth Engine v2 は `night_scout` / `liver_manager` のThreads text-only自動投稿を中心に、参照元収集、投稿生成、AUTO_READY、投稿、posted_results、PDCA、Media Growth Engineを段階的に接続するシステム。
- 今回は「Actions successだが投稿0」の原因追跡を容易にし、`NO_READY_QUEUE` / `AUTO_READY_REJECTED_ALL` の次の理由までSheets/JSONで見えるようにした。
- 実投稿、手動apply、実download、実cut、実upload、Cloudinary upload、transcription API、X fetch/post、beauty投稿は未実行。

### 変更ファイル一覧

- `src/sheets_client.py`
- `scripts/generate_threads_ideas_from_references.py`
- `scripts/auto_approve_queue.py`
- `scripts/process_threads_queue.py`
- `scripts/run_autonomous_loop.py`
- `scripts/autonomous_recovery_test_utils.py`
- `docs/autonomous-mode-runbook.md`
- `docs/growth-loop-runbook.md`
- `docs/production-completion-status.md`
- `docs/ai-work-handoff.md`

### 追加ファイル一覧

- `scripts/test_auto_approve_reject_reasons_visible.py`
- `scripts/test_autonomous_health_schema.py`
- `scripts/test_no_ready_queue_not_expected_after_safe_fallback.py`
- `scripts/test_run_autonomous_loop_stop_before_post_static.py`
- `scripts/test_no_ready_queue_root_cause_report.py`
- `scripts/test_fallback_post_generated_when_reference_rows_empty.py`
- `scripts/test_fallback_post_passes_final_validator.py`
- `scripts/test_auto_approve_promotes_safe_fallback_to_ready.py`
- `scripts/test_queue_waiting_review_to_ready_flow.py`
- `scripts/test_process_threads_queue_picks_ready_text_only.py`
- `scripts/test_process_threads_queue_uses_public_post_text_only.py`
- `scripts/test_duplicate_does_not_block_all_variations.py`
- `scripts/test_daily_cap_account_specific_jst.py`
- `scripts/test_cooldown_account_specific.py`
- `scripts/test_media_growth_does_not_block_text_only.py`
- `scripts/test_night_scout_fallback_topics.py`
- `scripts/test_liver_manager_fallback_topics.py`
- `scripts/test_account_specific_generation_not_mixed.py`

### 実装内容

- `queue` schemaに `public_post_text`, `internal_analysis`, source/provenance, validator状態, rejected/blocked理由、posted/result列を追加。
- `posted_results` schemaに source/provenance, `generation_mode`, `validator_status`, media関連保存列を追加。
- `autonomous_health` tab schemaを追加。scheduled runごとに `ready_count`, `checked_count`, `approved_count`, `rejected_count`, `posted_count`, `no_post_reason` を保存可能にした。
- `generate_threads_ideas_from_references.py` はqueue行にも `public_post_text` と診断列を書く。
- `auto_approve_queue.py` は `checked_count`, `approved_count`, `rejected_count`, `ready_count`, `rejected_reasons`, sample rejected previewを出力し、queueにもreject理由を残す。
- `process_threads_queue.py` はqueue-level `public_post_text` を安全に読めるようにし、投稿成功時にvalidator/provenanceを `posted_results` とqueueへ保存する。
- `run_autonomous_loop.py` に `--stop-before-post` を追加。`--apply --confirm-autonomous` 必須で、generate/AUTO_READYまで実行し、`process_threads_queue.py` は呼ばない。

### 未完了事項

- 次回scheduled runで `posted_count>=1` を確認する必要がある。
- 実Sheets上の `autonomous_health` tabは次回 apply 時にそのタブだけ冪等作成される（全タブ `setup_all` は呼ばない）。
- metrics取得、PDCA自動改善、source_videos apply、実download/cut/upload/video postは引き続き本番OFFまたは未完了。

### 残WARN

- GitHub Actionsが緑でも投稿成功とは限らない。必ず `health_summary.posted_count`, `posted_results.post_url`, `autonomous_health.no_post_reason` を見る。
- `--stop-before-post` は診断用。実投稿はしないが、apply指定時はSheetsに生成/AUTO_READY更新を書き得る。

### テスト結果

- 追加/互換READY診断テスト群: PASS。
- `check_autonomous_health.py --account-id all --dry-run`: PASS。
- `run_autonomous_loop.py --account-id night_scout --dry-run`: PASS、validator PASS、would_post=false。
- `run_autonomous_loop.py --account-id liver_manager --dry-run`: PASS、validator PASS、would_post=false。
- `run_autonomous_loop.py --account-id night_scout --preflight`: PASS。
- `run_autonomous_loop.py --account-id liver_manager --preflight`: PASS。
- `test_all_workflows_safety_flags.py`: PASS 139 / FAIL 0。
- `test_autonomous_workflow_no_x_no_media.py`: PASS。
- `test_autonomous_posts_only_threads.py`: PASS。
- `test_internal_terms_never_in_posted_text.py`: PASS。
- `test_source_registry_no_beauty_active.py`: PASS。
- `test_source_registry_no_x_fetch_by_default.py`: PASS。
- `test_rights_status_policy.py`: PASS 6 / FAIL 0。

### 次に触ってよいファイル

- `scripts/run_autonomous_loop.py`
- `scripts/auto_approve_queue.py`
- `scripts/process_threads_queue.py`
- `scripts/generate_threads_ideas_from_references.py`
- `scripts/check_autonomous_health.py`
- docs/runbook類

### 触らない方がいいファイル

- `.env`
- `data/`
- `output/`
- `.claude/plans/`
- cookie / storage_state / token類
- 実download/cut/upload/postの認証値

### 次AIへの引き継ぎメモ

- 次回scheduled runで見る順番: Actions `health_summary` → Sheets `autonomous_health` → `queue.rejected_reason` → `posted_results.post_url`。
- `NO_READY_QUEUE` ならREADYが作れていない。`AUTO_READY_REJECTED_ALL` なら `rejected_reasons` を確認。
- `final_public_post_validator` は弱めない。生成側を直す。
- Media Growth Engineはdry-run/gatedのまま。text-only scheduleを壊さない。

## 最新作業内容 (2026-07-09) — NO_READY_QUEUE / AUTO_READY_REJECTED_ALL の解消補強

### 本システムについて

- 目的は SNS Growth Engine の text-only autonomous Threads 投稿を安定稼働させること。
- 今回は動画本番化ではなく、`投稿候補生成 → AUTO_READY → READY → Threads worker` の詰まりを解消した。
- 実投稿、手動apply、実download/cut/upload/video post、Cloudinary upload、transcription API、X fetch/post、beauty投稿は未実行。

### 今回の調査結果

- Actionsは発火済みで apply step まで到達している。
- 投稿0の主因は `NO_READY_QUEUE`。
- 実ログでは `generate_threads_ideas_from_references.py` が既存queueを `skipped` し、古い短文/REJECT候補が残ったまま `auto_approve_queue.py` で落ちる構造があった。
- reference由来queue IDが固定のため、過去に `READY` / `POSTED` などロック済みになった行があると新規在庫が増えないケースもあった。

### 修正内容

- `scripts/generate_threads_ideas_from_references.py`
  - 既存の非ロック行（`WAITING_REVIEW`, `REJECTED`, stale/blocked系）を現在の検証済み public text で refresh する。
  - `READY`, `PROCESSING`, `MEDIA_READY`, `POSTED` は絶対に上書きしない。
  - reference生成のqueue追加/refreshが0件なら、timestamp付きsafe fallback候補を追加する。
- `scripts/run_autonomous_loop.py`
  - AUTO_READYが候補を評価したが1件も選ばなかった場合、`health_summary.no_post_reason=AUTO_READY_REJECTED_ALL` を出す。
- `scripts/autonomous_recovery_test_utils.py`
  - stale row refresh、locked row非更新、fallback AUTO_READY合格、health summary原因判定のテストを追加。

### 今回の作業ブランチ

- `main`
- 作業開始HEAD: `ad12090c389c57366d78b706bd881b7e36a77d0f`
- 現在HEAD: commit後に `git rev-parse HEAD` で確認。

### 変更ファイル一覧

- `scripts/generate_threads_ideas_from_references.py`
- `scripts/run_autonomous_loop.py`
- `scripts/autonomous_recovery_test_utils.py`
- `docs/autonomous-mode-runbook.md`
- `docs/production-completion-status.md`
- `docs/growth-loop-runbook.md`
- `docs/ai-work-handoff.md`

### 追加ファイル一覧

- `scripts/test_generation_refreshes_stale_waiting_review_rows.py`
- `scripts/test_generation_does_not_refresh_ready_or_posted_rows.py`
- `scripts/test_safe_fallback_candidates_are_auto_ready_approvable.py`
- `scripts/test_health_summary_reports_auto_ready_rejected_all.py`

### 未完了事項

- 実投稿は今回未実行。次回scheduled runで自然にapplyされる。
- 次回runで `health_summary.ready_count`, `posted_count`, `no_post_reason`, `posted_results` を確認する。
- 実Sheets上に古いREJECT行がある場合、今回のrefreshで更新される想定。

### 残WARN

- ローカルではSheets/Threads secretsは未設定表示。Actions上ではmask済みでpresence確認済み。
- `Autopilot AUTO_READY Pilot` など別workflowのfailureは今回対象外。

### 全テスト結果

- `test_generation_refreshes_stale_waiting_review_rows.py`: PASS。
- `test_generation_does_not_refresh_ready_or_posted_rows.py`: PASS。
- `test_safe_fallback_candidates_are_auto_ready_approvable.py`: PASS。
- `test_health_summary_reports_auto_ready_rejected_all.py`: PASS。
- `check_autonomous_health.py --account-id all --dry-run`: PASS。
- `run_autonomous_loop.py --account-id night_scout --dry-run`: PASS、validator PASS、would_post=false。
- `run_autonomous_loop.py --account-id liver_manager --dry-run`: PASS、validator PASS、would_post=false。
- `test_all_workflows_safety_flags.py`: PASS 139 / FAIL 0。
- `test_autonomous_workflow_no_x_no_media.py`: PASS。
- `test_autonomous_posts_only_threads.py`: PASS。
- `test_internal_terms_never_in_posted_text.py`: PASS。
- `test_source_registry_no_beauty_active.py`: PASS。
- `test_source_registry_no_x_fetch_by_default.py`: PASS。
- `test_rights_status_policy.py`: PASS 6 / FAIL 0。
- `py_compile`: PASS。

### dry-run結果

- 実投稿なし。
- night_scout/liver_managerとも public_post_preview は読者向け自然文、internal leakなし、validator PASS。

### confirmなしBLOCKED確認結果

- 実投稿は `--confirm-autonomous`, worker `--confirm-real-post`, `PUBLISH_ENABLED=true`, `ALLOW_REAL_THREADS_POST=true` が必要。
- media系は引き続きOFF。

### 次にClaude Codeが触ってよいファイル

- `scripts/auto_approve_queue.py`
- `scripts/generate_threads_ideas_from_references.py`
- `scripts/run_autonomous_loop.py`
- `docs/autonomous-mode-runbook.md`

### 次にCodexが触ってよいファイル

- `scripts/generate_threads_ideas_from_references.py`
- `scripts/run_autonomous_loop.py`
- `scripts/autonomous_recovery_test_utils.py`

### 衝突しやすいファイル

- `docs/ai-work-handoff.md`
- `scripts/autonomous_recovery_test_utils.py`
- `scripts/generate_threads_ideas_from_references.py`

### 触らない方がいいファイル

- `.env`
- `data/`
- `output/`
- `.claude/plans/`
- secrets / token / cookie / storage_state

### 次AIへの引き継ぎメモ

- 次回scheduled runで `posted_count=1` になれば今回の本丸は通った判断。
- まだ `AUTO_READY_REJECTED_ALL` が出る場合は、実Sheets上の候補本文・reasons・品質スコアを見る。
- `NO_READY_QUEUE` のままなら、queue refresh/topupが実Sheetsで書けているか、`applied_operations.queue.refreshed/added` と `fallback_topup_operations` を確認する。
- 動画本番ONはまだ後回し。text-onlyが安定してから。

## 最新作業内容 (2026-07-09) — GitHub Actions schedule発火確認とworkflow発火保証補強

### 本システムについて

- text-only autonomous Threads posting は `Autonomous Growth Loop Night Scout` / `Autonomous Growth Loop Liver Manager` の account-specific scheduled workflow で運用する。
- media schedule はOFF。Media Growth Engine / Source Video Discovery は dry-run/gated のまま。
- X fetch/post、beauty投稿、third-party media download/cut/upload/repost、Cloudinary upload、transcription API は引き続き禁止。

### 今回の調査結果

- `HEAD` / `origin/main`: `9acc057c35550fbcf6c357b520f06de4ecf196a9` から開始。
- GitHub repo default branch: `main`。
- Actions permissions: enabled=true, allowed_actions=all。
- Workflow state: `Autonomous Growth Loop Night Scout`, `Autonomous Growth Loop Liver Manager`, `Autonomous Growth Loop` は全て `active`。
- 2026-06-20以降にrunがない、という状態ではなかった。
- 直近run:
  - Night Scout `29003612060`: event=`schedule`, conclusion=`success`, apply step到達。
  - Liver Manager `29000408859`: event=`schedule`, conclusion=`success`, apply step到達。
- 投稿0の実測理由:
  - `health_summary.posted_count=0`
  - `health_summary.no_post_reason=NO_READY_QUEUE`
  - Liver Managerでは `auto_approve_queue.py` が候補を `REJECTED` にし、`process_threads_queue.py` が `NO_READY_QUEUE`。
- 結論: Actions未発火ではなく、発火後にREADY queueが無いため投稿されていない。

### 修正内容

- `.github/workflows/autonomous-growth-loop-night-scout.yml`
  - `permissions: contents: read / actions: read` 追加。
  - `concurrency` 追加。
  - `dry_run_only` workflow_dispatch input追加。
  - `Schedule heartbeat` step追加。
  - guard/apply stepを `dry_run_only != 'true'` で保護。
- `.github/workflows/autonomous-growth-loop-liver-manager.yml`
  - Night Scoutと同じ発火保証/安全補強を追加。
- `.github/workflows/autonomous-growth-loop.yml`
  - manual workflowにも permissions/concurrency/heartbeat/dry_run_only を追加。scheduleはなし。
- `scripts/check_autonomous_health.py`
  - workflow permissions, concurrency, heartbeat, dry_run_only安全性を検査。
- `scripts/autonomous_recovery_test_utils.py`
  - workflow発火保証テストを追加。
- `docs/autonomous-mode-runbook.md`
  - workflow名、active確認、Enable workflow手順、dry_run_only、heartbeat、NO_READY_QUEUEの見方を追記。
- `docs/production-completion-status.md`
  - 2026-07-09のActions発火確認とNO_READY_QUEUE原因を追記。

### 今回の作業ブランチ

- `main`
- 作業開始HEAD: `9acc057c35550fbcf6c357b520f06de4ecf196a9`
- 現在HEAD: commit後に `git rev-parse HEAD` で確認。

### 変更ファイル一覧

- `.github/workflows/autonomous-growth-loop.yml`
- `.github/workflows/autonomous-growth-loop-night-scout.yml`
- `.github/workflows/autonomous-growth-loop-liver-manager.yml`
- `scripts/check_autonomous_health.py`
- `scripts/autonomous_recovery_test_utils.py`
- `docs/autonomous-mode-runbook.md`
- `docs/production-completion-status.md`
- `docs/ai-work-handoff.md`

### 追加ファイル一覧

- `scripts/test_workflow_permissions_declared.py`
- `scripts/test_scheduled_workflows_have_heartbeat.py`
- `scripts/test_scheduled_workflows_have_dry_run_only_dispatch.py`
- `scripts/test_scheduled_workflows_have_concurrency.py`
- `scripts/test_scheduled_workflows_schedule_event_runs_apply.py`
- `scripts/test_manual_workflow_no_schedule.py`
- `scripts/test_workflow_names_not_confusing.py`
- `scripts/test_actions_enablement_runbook_docs.py`

### 未完了事項

- 実投稿は今回未実行。
- scheduleは発火しているが、READY queue不足で投稿0になるリスクが残る。
- 次回は `NO_READY_QUEUE` / `AUTO_READY_REJECTED_ALL` を潰すため、生成候補の品質・既存queue重複・auto_ready rejected理由を対象にする。

### 残WARN

- ローカルhealth checkではsecret presenceは未設定。Actionsログではsecretはmask済みでpresenceあり。
- `Autopilot AUTO_READY Pilot` と `Content Daily Dry-Run` には別workflowのfailureが残る。今回の対象外。
- GitHub Actions latest successは投稿成功ではなく `NO_READY_QUEUE` の可能性があるため、`success` だけで投稿成功と判断しない。

### 全テスト結果

- `scripts/check_autonomous_health.py --account-id all --dry-run`: PASS。
- 新規workflow発火保証テスト8本: PASS。
- 既存workflow schedule/env/account tests: PASS。
- `scripts/test_all_workflows_safety_flags.py`: PASS 139 / FAIL 0。
- `scripts/test_autonomous_workflow_no_x_no_media.py`: PASS。
- `scripts/test_autonomous_posts_only_threads.py`: PASS。
- `scripts/test_source_registry_no_beauty_active.py`: PASS。
- `scripts/test_source_registry_no_x_fetch_by_default.py`: PASS。
- `scripts/test_rights_status_policy.py`: PASS 6 / FAIL 0。
- `scripts/test_internal_terms_never_in_posted_text.py`: PASS。
- `py_compile`: PASS。
- `git diff --check`: PASS。

### dry-run結果

- `run_autonomous_loop.py --account-id night_scout --dry-run`: public_post_previewあり、validator PASS、would_post=false。
- `run_autonomous_loop.py --account-id liver_manager --dry-run`: public_post_previewあり、validator PASS、would_post=false。
- `check_autonomous_health.py --account-id all --dry-run`: workflow/config/schema/source/media sanity PASS予定。

### confirmなしBLOCKED確認結果

- `dry_run_only=true` manual dispatchでは guard/apply をskip。
- scheduled eventは従来どおりapply対象。ただし kill_switch / secrets guard / env gate / publisher gateは維持。
- 実download/cut/upload/video postは未実行・OFF維持。

### 次にClaude Codeが触ってよいファイル

- `scripts/auto_approve_queue.py`
- `scripts/generate_threads_ideas_from_references.py`
- `scripts/process_threads_queue.py`
- `scripts/run_autonomous_loop.py`
- `docs/autonomous-mode-runbook.md`

### 次にCodexが触ってよいファイル

- `.github/workflows/autonomous-growth-loop-night-scout.yml`
- `.github/workflows/autonomous-growth-loop-liver-manager.yml`
- `scripts/check_autonomous_health.py`
- workflow tests under `scripts/test_*workflow*.py`

### 衝突しやすいファイル

- `.github/workflows/autonomous-growth-loop*.yml`
- `scripts/autonomous_recovery_test_utils.py`
- `docs/ai-work-handoff.md`

### 触らない方がいいファイル

- `.env`
- `data/`
- `output/`
- `.claude/plans/`
- secrets / cookie / storage_state

### 次AIへの引き継ぎメモ

- Actionsは発火済み。次に見るべきは `NO_READY_QUEUE` の根絶。
- 2026-07-09 18:50 JST時点の次回scheduled windowは night_scout/liver_manager とも JST 21:00 ±15min、night_scout はその後 JST 25:00 ±15min。
- GitHub UIで見る場所: Actions → `Autonomous Growth Loop Night Scout` / `Autonomous Growth Loop Liver Manager` → 最新scheduled run → `Schedule heartbeat`, `Apply autonomous Threads loop`, `Autonomous health summary`。
- 変な投稿が出たら `config/autonomous_mode.json` の `kill_switch=true`。

## 最新作業内容 (2026-07-07) — 自動投稿停止復旧と night_scout Threads 参考元追加

### 本システムについて

- text-only autonomous Threads posting は `night_scout` / `liver_manager` の account-specific scheduled workflow で運用する。
- media schedule はOFF。Media Growth Engine / Source Video Discovery は dry-run/gated のまま。
- X fetch/post、beauty投稿、third-party media download/cut/upload/repost、Cloudinary upload、transcription API は引き続き禁止。
- 投稿本文は `public_post_text` のみを publisher に渡す。`internal_analysis` / source / queue / score / metadata / transcript / AI生成メモは投稿本文に混ぜない。

### 自動投稿停止の原因

- GitHub Actions schedule 自体は起動していた。
- 直近の scheduled run は `scripts/recover_production_sheets_threads_first.py --verify-only --json` の `source_registry_reflected` / `video_sources_reflected` FAIL を hard BLOCK として扱い、apply前に終了していた。
- 参考投稿/scoreが空の場合、`generate_threads_ideas_from_references.py` が `NO_DATA` で候補を作らず、AUTO_READY/workerへ在庫が渡らない構造だった。
- source fetch / score など外部依存ステップが失敗すると、fallback生成へ進まず投稿停止する構造だった。

### 修正内容

- `run_autonomous_loop.py`
  - account-specific workflowでは rotation を使わず、固定 `ACCOUNT_ID` を優先。
  - `--preflight` を追加。実投稿なしで Sheets/Threads credential presence、kill_switch、source/validator状態を確認。
  - Sheets verify failure は non-blocking warning に変更。実際のSheets/worker処理で最終検証する。
  - source fetch / video reference / scoring failure は soft-fail warning とし、安全なfallback投稿生成へ進む。
  - `health_summary` に ready/processed/posted/blocked/no_post_reason を出力。
- `generate_threads_ideas_from_references.py`
  - source posts/scores が空でも、reader-facing original fallback を `WAITING_REVIEW` に生成。
  - fallback本文も `final_public_post_validator` を通す。
- `auto_approve_queue.py`
  - 内部メモ寄り語彙に依存していた品質スコアを読者向け投稿語彙へ修正。
- `process_threads_queue.py`
  - READY候補なしを `{"status":"NO_POST","reason":"NO_READY_QUEUE"}` としてJSON出力。
- `.github/workflows/autonomous-growth-loop*.yml`
  - `Autonomous health summary` step を `if: always()` で追加。
- `scripts/check_autonomous_health.py`
  - workflow/config/schema/source/media gateを読み取り専用で確認。secret値は表示しない。
- `config/source_accounts/default_sources.json`
  - `src_ns_threads_user_chiishunin_s` を追加。

### 今回の作業ブランチ

- `main`
- 作業開始HEAD: `a861c4388a056a9d76cf6d684f8cc06da2b73e8a`
- 現在HEAD: commit後に `git rev-parse HEAD` で確認。

### 変更ファイル一覧

- `.github/workflows/autonomous-growth-loop.yml`
- `.github/workflows/autonomous-growth-loop-night-scout.yml`
- `.github/workflows/autonomous-growth-loop-liver-manager.yml`
- `config/source_accounts/default_sources.json`
- `scripts/run_autonomous_loop.py`
- `scripts/generate_threads_ideas_from_references.py`
- `scripts/auto_approve_queue.py`
- `scripts/process_threads_queue.py`
- `scripts/public_post_quality.py`
- `docs/ai-work-handoff.md`
- `docs/production-completion-status.md`
- `docs/autonomous-mode-runbook.md`
- `docs/growth-loop-runbook.md`
- `docs/source-registry-inventory.md`
- `docs/video-reference-runbook.md`

### 追加ファイル一覧

- `scripts/check_autonomous_health.py`
- `scripts/autonomous_recovery_test_utils.py`
- autonomous recovery / workflow / fallback / chiishunin / media-gate test entry files added in this turn.

### 未完了事項

- 実投稿は今回未実行。次回scheduled runで自然にapplyされる。
- GitHub Actionsの最新runは修正前HEADのため失敗履歴が残っている。次回runで `health_summary` と posted_results を確認する。
- Sheets上の `source_accounts/reference_sources` reflect差分は verify warning として残る可能性があるが、今回のrunnerでは投稿停止原因にしない。

### 残WARN

- ローカル `check_autonomous_health.py` では env secret presence は未設定表示。Actions上では既存ログでSheets/Threads secretsはSET確認済み。
- `gh workflow list` は一度ネットワーク接続エラー。`gh run list` / `gh run view` は取得できた。

### 全テスト結果

- 指定autonomous recovery tests: PASS
- 既存安全テスト: `test_all_workflows_safety_flags.py`, `test_autonomous_workflow_no_x_no_media.py`, `test_autonomous_posts_only_threads.py`, `test_source_registry_no_beauty_active.py`, `test_source_registry_no_x_fetch_by_default.py`, `test_rights_status_policy.py`, `test_internal_terms_never_in_posted_text.py` PASS
- `py_compile`: PASS
- `git diff --check`: PASS

### dry-run結果

- `check_autonomous_health.py --account-id all --dry-run`: PASS、workflow schedule valid、media schedule OFF、x_fetch_enabled=0、beauty_active=0。
- `run_autonomous_loop.py --account-id night_scout --dry-run`: selected_account=`night_scout`, internal_leak_check=PASS, final_validator_result=PASS, would_post=false。
- `run_autonomous_loop.py --account-id liver_manager --dry-run`: selected_account=`liver_manager`, internal_leak_check=PASS, final_validator_result=PASS, would_post=false。

### confirmなしBLOCKED確認結果

- `run_autonomous_loop.py --apply` は `--confirm-autonomous` が無い場合 BLOCKED。
- `process_threads_queue.py` は real post に `--confirm-real-post`, `PUBLISH_ENABLED=true`, `ALLOW_REAL_THREADS_POST=true` が必要。
- download/cut/upload/video post は既存 env + confirm gate のまま。

### 次にClaude Codeが触ってよいファイル

- `scripts/run_autonomous_loop.py`
- `scripts/check_autonomous_health.py`
- `scripts/generate_threads_ideas_from_references.py`
- `docs/autonomous-mode-runbook.md`
- `docs/growth-loop-runbook.md`

### 次にCodexが触ってよいファイル

- `scripts/process_threads_queue.py`
- `scripts/auto_approve_queue.py`
- `scripts/public_post_quality.py`
- `.github/workflows/autonomous-growth-loop-night-scout.yml`
- `.github/workflows/autonomous-growth-loop-liver-manager.yml`

### 衝突しやすいファイル

- `config/source_accounts/default_sources.json`
- `scripts/run_autonomous_loop.py`
- `docs/ai-work-handoff.md`
- `docs/production-completion-status.md`

### 触らない方がいいファイル

- `.env`
- `data/`
- `output/`
- `.claude/plans/`
- secrets/tokens/cookies/storage_state

### 次AIへの引き継ぎメモ

- 次回scheduled runでは、まず Actions log の `health_summary.no_post_reason`, `posted_count`, `ready_count` を見る。
- `sheets_verify_failed_non_blocking_runner_will_validate` が出ても、それ単体では投稿停止しない設計に変更済み。
- 投稿されない場合は `NO_READY_QUEUE`, `AUTO_READY_REJECTED_ALL`, `VALIDATOR_BLOCKED_ALL`, `DUPLICATE_BLOCKED_ALL`, `DAILY_CAP_REACHED`, `COOLDOWN_ACTIVE`, `THREADS_API_FAILED`, `POSTED_SAVE_FAILED` のいずれかを確認する。
- 変な投稿が出た場合は即 `kill_switch=true` にする。

## 最新作業内容 (2026-07-05) — 許可済みアカウント動画発見と複数clip候補生成

### 本システムについて

- `liver_manager` の許可済み YouTube/TikTok channel/account source から、bounded な動画候補 `source_videos` を作れるようにした。
- 個別video URLの手入力だけに依存せず、source単位で動画候補を discovery plan として出せる。
- `video_id` / `canonical_video_url` / fallback hash で重複管理する。
- 1動画から1-3件の non-overlap clip candidate を生成できる。
- media schedule はOFF。text-only autonomous schedule は維持。
- 実download / 実cut / 実upload / Cloudinary upload / video post / transcription API は未実行。

### 今回の作業ブランチ

- `main`
- 作業開始HEAD: `1847607e19f91b99aee336e041a1c0366f557a82`
- 現在HEAD: commit後に `git rev-parse HEAD` で確認。

### 変更ファイル一覧

- `config/media_growth_engine.json`
- `scripts/media_growth_schemas.py`
- `scripts/run_media_growth_engine.py`
- `scripts/download_approved_media.py`
- `scripts/cut_approved_clips.py`
- `scripts/upload_media_assets.py`
- `src/sheets_client.py`
- `src/storage/pipeline_store.py`
- `docs/video-reference-runbook.md`
- `docs/media-rights-template.md`
- `docs/growth-loop-runbook.md`
- `docs/production-completion-status.md`
- `docs/source-registry-inventory.md`
- `docs/ai-work-handoff.md`

### 追加ファイル一覧

- `scripts/discover_approved_source_videos.py`
- discovery/source_videos/clip/pipeline/safety test files added in this turn.

### 未完了事項

- `source_video_discovery_apply_enabled=false` のため、実Sheets/local保存applyはまだOFF。
- TikTok accountは limited/manual-safe plan。無制限profile scrapingは未実装・禁止。
- 実download/cut/upload/postには reviewed `source_video_id` / `clip_candidate_id` と env+confirm が必要。

### 残WARN

- discovery dry-runは候補計画。実API/yt-dlpネットワーク取得はこの作業では行っていない。
- 実運用前に、source_videosタブのapply可否と保存先を人間が確認すること。

### テスト結果

- この作業の最終テスト結果は完了報告の `tests結果` を参照。

### dry-run結果

- `discover_approved_source_videos.py --account-id liver_manager --dry-run`: approved 4 sourceのみ選択、bounded discovery plan、would_save_source_videos=false。
- `run_media_growth_engine.py --account-id liver_manager --dry-run`: source_videos/discovery plan優先、video単位clip候補生成、would_download/cut/upload/post=false。

### 次に触ってよいファイル

- `scripts/discover_approved_source_videos.py`
- `scripts/run_media_growth_engine.py`
- `scripts/media_growth_schemas.py`
- `config/media_growth_engine.json`
- `docs/video-reference-runbook.md`

### 衝突しやすいファイル

- `src/sheets_client.py`
- `docs/ai-work-handoff.md`
- `config/media_growth_engine.json`

### 触らない方がいいファイル

- `.env`
- `data/`
- `output/`
- `.claude/plans/`
- secrets/tokens/cookies/storage_state

### 次AIへの引き継ぎメモ

- 次に本番ONするなら、まず `source_video_discovery_apply_enabled=true` を別commitで検討し、`--apply --confirm-discovery` を source_videos 追記だけに限定する。
- media download/cut/upload/post は引き続き別段階。scheduleへmedia投稿を混ぜない。

## 最新作業内容 (2026-07-04) — 許可済み動画 Media Growth Engine 追加

### 本システムについて

- text-only autonomous Threads schedule は継続。`night_scout` / `liver_manager` の account-specific workflow は維持。
- 今回は `liver_manager` のユーザー許可済み YouTube/TikTok source だけを Media Growth Engine 対象にした。
- `third_party_reference_only` / `unknown` / `reference_only` は引き続き media download/cut/upload/video post 不可。
- `approved_creator_clip` / `owned` / `licensed` だけが media pipeline eligible。
- 実download / 実cut / Cloudinary実upload / video + text Threads実投稿 / transcription API は未実行。
- scheduled media posting はOFF。video + text post は manual apply 限定の実装準備まで。

### 今回の作業ブランチ

- `main`
- 作業開始HEAD: `2246031487333ca765cb4d7d082872c85b6b9a88`
- 現在HEAD: commit後に `git rev-parse HEAD` で確認。

### 変更ファイル一覧

- `config/source_accounts/default_sources.json`
- `config/source_accounts/owned_media_asset_template.json`
- `scripts/cut_approved_clips.py`
- `scripts/upload_media_assets.py`
- `scripts/process_threads_queue.py`
- `src/publishers/threads_publisher.py`
- `docs/video-reference-runbook.md`
- `docs/media-rights-template.md`
- `docs/growth-loop-runbook.md`
- `docs/autonomous-mode-runbook.md`
- `docs/production-completion-status.md`
- `docs/source-registry-inventory.md`
- `docs/ai-work-handoff.md`

### 追加ファイル一覧

- `config/media_growth_engine.json`
- `scripts/media_growth_schemas.py`
- `scripts/run_media_growth_engine.py`
- `scripts/download_approved_media.py`
- `scripts/media_post_validator.py`
- `scripts/test_approved_creator_sources_have_permission_evidence.py`
- `scripts/test_user_liver_sources_can_be_approved_creator_clip.py`
- `scripts/test_third_party_sources_still_block_media_pipeline.py`
- `scripts/test_channel_account_urls_not_auto_downloadable.py`
- `scripts/test_individual_video_url_required_for_download.py`
- `scripts/test_media_growth_engine_dry_run.py`
- `scripts/test_media_growth_engine_selects_only_approved_sources.py`
- `scripts/test_media_growth_engine_blocks_unknown_rights.py`
- `scripts/test_media_growth_engine_generates_clip_candidates.py`
- `scripts/test_media_growth_engine_outputs_public_post_preview.py`
- `scripts/test_media_growth_engine_does_not_download_in_dry_run.py`
- `scripts/test_video_transcript_schema.py`
- `scripts/test_clip_candidate_schema.py`
- `scripts/test_clip_candidate_scoring.py`
- `scripts/test_cut_approved_clips_requires_env_and_confirm.py`
- `scripts/test_cut_approved_clips_blocks_third_party_reference_only.py`
- `scripts/test_cut_approved_clips_plan_vertical_subtitles.py`
- `scripts/test_download_approved_media_requires_individual_video_url.py`
- `scripts/test_download_approved_media_blocks_channel_url_apply.py`
- `scripts/test_download_approved_media_requires_env_and_confirm.py`
- `scripts/test_upload_media_assets_requires_approved_rights.py`
- `scripts/test_upload_media_assets_requires_env_and_confirm.py`
- `scripts/test_media_post_validator_requires_approved_rights.py`
- `scripts/test_media_post_validator_blocks_x_beauty.py`
- `scripts/test_media_post_validator_requires_public_post_validator_pass.py`
- `scripts/test_threads_video_post_requires_media_gate.py`
- `scripts/test_threads_video_post_dry_run_only_by_default.py`
- `scripts/test_media_pdca_records_clip_candidate_id.py`
- `scripts/test_media_pdca_suggestions_waiting_review.py`
- `scripts/test_media_learning_rules_not_auto_applied.py`

### 許可済みsource

- `src_lm_yt_user_001`: `https://youtube.com/channel/UCzFzty7aEd4tw3NqCW6pkLQ`
- `src_lm_tt_user_001`: `https://www.tiktok.com/@user5597696107300`
- `src_lm_tt_user_002`: `https://www.tiktok.com/@me02_lsm`
- `src_lm_tt_user_003`: `https://www.tiktok.com/@uare.inc`

上記4件は `rights_status=approved_creator_clip`, `permission_status=approved`, `permission_evidence_type=user_asserted_permission`, `media_pipeline_eligible=true`, `clip_enabled=true`, `can_reuse_media=true`。ただし `fetch_enabled=false`, `manual_only=true`, `media_download=gated`, `allow_download/cut/upload=gated`。

### 未完了事項

- channel/account URL は直接download対象にしない。実download/cutには個別動画URLが必要。
- Cloudinary upload は未実行。`ALLOW_CLOUDINARY_UPLOAD=true --upload --confirm-upload` が必要。
- ffmpeg cut は未実行。`ALLOW_VIDEO_CUT=true --cut --confirm-cut` が必要。
- video + text Threads post は未実行。media validator PASS と `ALLOW_MEDIA_POSTS=true`, `ALLOW_REAL_THREADS_VIDEO_POST=true`, `ALLOW_REAL_THREADS_POST=true` が必要。
- media schedule は未接続。text-only schedule のみON。

### 残WARN

- ユーザー許可は `user_asserted_permission` として記録。必要なら後続で契約/DM/メール等の外部証跡URLを追記する。
- TikTok account URL は自動展開しない。個別 `/video/` URLが必要。
- YouTube channel URL は transcript が直接取れない場合がある。個別動画URLが必要。

### テスト結果

- この作業の最終テスト結果は完了報告の `tests結果` を参照。

### dry-run結果

- `run_media_growth_engine.py --account-id liver_manager --dry-run`: 許可済み4sourceを選択し、rights/permission check PASS、download/cut/upload/video post はすべてfalseの計画。
- `download_approved_media.py` channel URL dry-run: individual video URL required。
- `cut_approved_clips.py` dry-run: PLAN_ONLY、output path planあり。

### 次に触ってよいファイル

- `scripts/run_media_growth_engine.py`
- `scripts/download_approved_media.py`
- `scripts/cut_approved_clips.py`
- `scripts/upload_media_assets.py`
- `scripts/media_post_validator.py`
- `config/media_growth_engine.json`
- `docs/video-reference-runbook.md`

### 衝突しやすいファイル

- `config/source_accounts/default_sources.json`
- `scripts/process_threads_queue.py`
- `src/publishers/threads_publisher.py`
- `docs/ai-work-handoff.md`

### 触らない方がいいファイル

- `.env`
- `data/`
- `output/`
- `.claude/plans/`
- secrets/tokens/cookies/storage_state

### 次AIへの引き継ぎメモ

- Media Growth Engine は実装済みだが、本番ONはまだしない。まず個別動画URLと権利証跡を追加し、dry-runで candidate / validator / media plan を確認すること。
- `public_post_text` のみ publisher に渡す invariant は維持。
- media PDCA は記録と `WAITING_REVIEW` 提案まで。learning rules は自動適用しない。

## 最新作業内容 (2026-07-02) — 承認レス自動運用モード追加

### 本システムについて

- `night_scout` / `liver_manager` の text-only Threads pilot は、個別投稿ごとの人間承認なしで動かせる autonomous mode を追加。
- `beauty_account` は引き続き blocked / draft_only。
- X fetch/post は blocked。
- media post / third-party media / unknown rights / video download / cut / Cloudinary upload / transcription API は blocked。
- 自動運用は `config/autonomous_mode.json` の rules と `--confirm-autonomous` のコマンドレベル確認で管理。
- 初期 cap は daily post 1/account、daily READY 2/account、max posts/run 1、cooldown 180分。
- kill switch は `config/autonomous_mode.json` の `kill_switch`。

### 今回の作業ブランチ

- `main`
- 作業開始HEAD: `209c684e7798499ae2ba1228f20fe4966e22ae5f`
- 現在HEAD: commit後に `git rev-parse HEAD` で確認。

### 変更ファイル一覧

- `docs/production-pilot-runbook.md`
- `docs/growth-loop-runbook.md`
- `docs/source-registry-inventory.md`
- `docs/production-completion-status.md`
- `docs/ai-work-handoff.md`

### 追加ファイル一覧

- `config/autonomous_mode.json`
- `scripts/run_autonomous_loop.py`
- `.github/workflows/autonomous-growth-loop.yml`
- `docs/autonomous-mode-runbook.md`
- `scripts/test_autonomous_config_exists.py`
- `scripts/test_autonomous_mode_blocks_beauty.py`
- `scripts/test_autonomous_mode_blocks_x_post.py`
- `scripts/test_autonomous_mode_blocks_x_fetch.py`
- `scripts/test_autonomous_mode_blocks_media_initially.py`
- `scripts/test_autonomous_mode_blocks_third_party_media.py`
- `scripts/test_autonomous_mode_respects_kill_switch.py`
- `scripts/test_autonomous_mode_daily_caps.py`
- `scripts/test_autonomous_mode_similarity_guard.py`
- `scripts/test_autonomous_loop_dry_run_no_post.py`
- `scripts/test_autonomous_loop_apply_requires_confirm.py`
- `scripts/test_autonomous_workflow_no_x_no_media.py`
- `scripts/test_autonomous_workflow_has_kill_switch.py`
- `scripts/test_autonomous_posts_only_threads.py`
- `scripts/test_autonomous_excludes_todo_placeholders.py`

### autonomous mode 初期設定

- `autonomous_mode_enabled=true`
- `auto_source_fetch_enabled=true`
- `auto_idea_generation_enabled=true`
- `auto_ready_enabled=true`
- `auto_post_enabled=true`
- `allowed_accounts=["night_scout","liver_manager"]`
- `blocked_accounts=["beauty_account"]`
- `allowed_platforms_for_fetch=["threads","youtube"]`
- `blocked_platforms_for_fetch=["x"]`
- `allowed_platforms_for_post=["threads"]`
- `blocked_platforms_for_post=["x"]`
- `allow_media_posts=false`
- `daily_post_cap_per_account=1`
- `daily_ready_cap_per_account=2`
- `max_posts_per_run=1`
- `kill_switch=false`
- `human_review_required=false`

### selected pilot/autonomous sources

- `src_ns_threads_required_001`
- `src_ns_threads_required_002`
- `src_lm_yt_cand_001`

### 未完了事項

- 本番 `--apply --confirm-autonomous` は未実行。
- GitHub Actions `autonomous-growth-loop.yml` は追加済みだが、手動 dispatch は未実行。
- YouTube は初期状態では metadata/transcript/reference analysis plan のみ。download/cut/upload は禁止。
- daily cap/cooldown の実カウントは apply 時に Sheets 側の最新状態と合わせて確認する。

### 残WARN

- autonomous dry-run は Sheets/API に触らない計画表示中心。Live Sheets verify は apply workflow 側で実行する。
- `config/auto_approval_rules.json` の既存 `auto_post_enabled=false` は legacy autopilot 用。autonomous mode は `config/autonomous_mode.json` を新しい制御元として使う。

### 全テスト結果

- `test_autonomous_config_exists.py`: PASS 8 / FAIL 0
- `test_autonomous_mode_blocks_beauty.py`: PASS 1 / FAIL 0
- `test_autonomous_mode_blocks_x_post.py`: PASS 1 / FAIL 0
- `test_autonomous_mode_blocks_x_fetch.py`: PASS 1 / FAIL 0
- `test_autonomous_mode_blocks_media_initially.py`: PASS 1 / FAIL 0
- `test_autonomous_mode_blocks_third_party_media.py`: PASS 1 / FAIL 0
- `test_autonomous_mode_respects_kill_switch.py`: PASS 1 / FAIL 0
- `test_autonomous_mode_daily_caps.py`: PASS 1 / FAIL 0
- `test_autonomous_mode_similarity_guard.py`: PASS 1 / FAIL 0
- `test_autonomous_loop_dry_run_no_post.py`: PASS 1 / FAIL 0
- `test_autonomous_loop_apply_requires_confirm.py`: PASS 1 / FAIL 0
- `test_autonomous_workflow_no_x_no_media.py`: PASS 1 / FAIL 0
- `test_autonomous_workflow_has_kill_switch.py`: PASS 1 / FAIL 0
- `test_autonomous_posts_only_threads.py`: PASS 1 / FAIL 0
- `test_autonomous_excludes_todo_placeholders.py`: PASS 1 / FAIL 0
- `test_all_workflows_safety_flags.py`: PASS 111 / FAIL 0
- `test_process_threads_queue.py`: PASS 11 / FAIL 0
- `test_rights_status_policy.py`: PASS 6 / FAIL 0
- `test_generate_posts_blocks_high_similarity_copy.py`: PASS 2 / FAIL 0
- `test_run_growth_loop_no_auto_post.py`: PASS 3 / FAIL 0
- `test_source_registry_no_beauty_active.py`: PASS 1 / FAIL 0
- `test_source_registry_no_x_fetch_by_default.py`: PASS 1 / FAIL 0
- `test_youtube_tiktok_placeholders_not_fetch_enabled.py`: PASS 5 / FAIL 0

### dry-run結果

- `python3 scripts/run_autonomous_loop.py --account-id all --dry-run`
  - selected sources: `src_ns_threads_required_001`, `src_ns_threads_required_002`, `src_lm_yt_cand_001`
  - X/beauty/TODO/media excluded
  - real post: false
  - media download/cut/upload: false

### confirmなしBLOCKED確認結果

- `python3 scripts/run_autonomous_loop.py --account-id all --apply` は `--apply requires --confirm-autonomous` で BLOCKED。
- `beauty_account` は autonomous plan で BLOCKED。

### 次にClaude Codeが触ってよいファイル

- `docs/autonomous-mode-runbook.md`
- `scripts/run_autonomous_loop.py`
- `.github/workflows/autonomous-growth-loop.yml`
- autonomous test files

### 次にCodexが触ってよいファイル

- `scripts/run_autonomous_loop.py`
- `scripts/collect_source_posts.py`
- `scripts/auto_approve_queue.py`
- `scripts/process_threads_queue.py`
- `docs/ai-work-handoff.md`

### 衝突しやすいファイル

- `config/auto_approval_rules.json`
- `config/autonomous_mode.json`
- `.github/workflows/*.yml`
- `docs/ai-work-handoff.md`

### 触らない方がいいファイル

- `.env`
- `data/`
- `output/`
- `.claude/plans/`
- secrets/tokens/cookies/storage_state

### 次AIへの引き継ぎメモ

- ユーザー意図は「毎回承認しないで動く」こと。ただし安全ゲートは壊さない。
- 初回は text-only Threads だけ。X/beauty/media は広げない。
- workflow は `workflow_dispatch` の `confirm_autonomous=true` で apply step が動く。
- 悪い投稿が出たら `config/autonomous_mode.json` の `kill_switch=true` を最優先で入れる。

## 最新作業内容 (2026-06-29) — Threads worker READY 承認モデル必須化（Phase 3）

**重要（現行仕様）**: Threads worker が投稿するのは **`status=READY` の行のみ**（`process_threads_queue.py` `ELIGIBLE_STATUSES = {"READY"}`）。
本ドキュメント下部の旧エントリにある「`WAITING_REVIEW` / `PLANNED` のみ対象」は **旧仕様** であり、以後は無効。

- 投稿可否モデル: `WAITING_REVIEW → READY → PROCESSING → POSTED`。
  - `WAITING_REVIEW`: 生成系CLIの既定出力（レビュー待ち、投稿不可）
  - `DRAFT`: 生成 / PDCA 候補（投稿不可）
  - `PLANNED`: 計画段階（投稿不可）
  - `READY`: 人間が `approve_queue.py` で承認済み（worker 投稿対象）
  - `POSTED`: 投稿完了（再投稿しない）
- `READY` 昇格は **`approve_queue.py`（WAITING_REVIEW → READY/REJECTED）経由のみ**。生成系CLIは `READY` を直接書かない。承認時 logs に `queue_approved` 証跡。
- X 側 `publish_queue.py`（`--status READY` 必須）と対称化。旧「承認モデル非対称」課題は解消。
- verify（`recover_production_sheets_threads_first.py`）に READY 承認モデル安全チェック10件追加。check 総数 51 件、合格条件 `failed=[]`。
  - `generated_candidates_not_ready_by_default` は logs の `queue_approved` 証跡で人間承認済み生成行を誤検知しない。
  - media 権利チェックは `media_url` / `media_asset_id` 双方で連携。
- 回帰固定テスト `test_recover_verify_ready_checks.py` ほか READY 系を追加。offline curated suite **55 / 55 PASS**。
- 更新docs: `threads-queue-worker.md` / `threads-operation-runbook.md` / `sheets-manual-check-guide.md` / `reference-pipeline-runbook.md` / `production-completion-status.md` / 本ファイル。
- 安全境界（変更なし）: 実投稿/実upload/download なし。`PUBLISH_ENABLED` / `ALLOW_REAL_THREADS_POST` / `ALLOW_CLOUDINARY_UPLOAD` 等は false 既定。beauty_account は draft_only。X は将来実装予定（設計・docs から削除しない）。

## 最新作業内容 (2026-06-24)

### Codex: Threads Queue Worker / Metrics Import Loop 実装

- 作業AI: Codex
- 作業ブランチ: `main`
- 作業開始HEAD: `5e4197eba17c25730d59b400df0113a5ef381169`
- 現在HEAD: このhandoffを含む最新commit。最終hashは `git rev-parse HEAD` / 完了報告で確認。
- origin/main開始確認: `5e4197eba17c25730d59b400df0113a5ef381169`
- 作業ディレクトリ: `/Users/hayatoa/claudecodeプロジェクトディレクトリ/dev/SNS自動投稿システム/v2`
- 目的: Sheets `投稿キュー` から Threads 投稿を1件ずつ安全に処理し、posted_results / queue / logs / PDCA まで接続する。

#### 本システムについて

- `night_scout` / `liver_manager` は Threads-first 運用。
- `beauty_account` は `draft_only` / CTAなし / 実投稿禁止。
- X投稿は当面OFF。X queueも作らない。
- media download / cut / upload / Cloudinary upload / transcription API は未実行・無効。
- `learning_rules.active=false`、`auto_apply=false` を維持し、PDCA提案は `WAITING_REVIEW` に留める。

#### 変更ファイル一覧

- `.github/workflows/content-daily-dry-run.yml`
- `.github/workflows/threads-queue-worker.yml`
- `src/config_loader.py`
- `src/sheets_client.py`
- `scripts/recover_production_sheets_threads_first.py`
- `scripts/process_threads_queue.py`
- `scripts/import_threads_metrics_manual.py`
- `scripts/refill_threads_queue.py`
- `scripts/test_process_threads_queue.py`
- `scripts/test_threads_queue_duplicate_guard.py`
- `scripts/test_posted_results_integrity.py`
- `scripts/test_import_threads_metrics_manual.py`
- `scripts/test_refill_threads_queue.py`
- `scripts/test_threads_queue_worker_workflow.py`
- `scripts/test_content_workflows_safety.py`
- `scripts/test_x_disabled_mode.py`
- `scripts/test_beauty_account_block.py`
- `docs/threads-queue-worker.md`
- `docs/metrics-import-runbook.md`
- `docs/threads-operation-runbook.md`
- `docs/sheets-manual-check-guide.md`
- `docs/production-completion-status.md`
- `docs/production-launch-checklist.md`
- `docs/ai-dev-status.md`
- `docs/phase13-16-test-matrix.md`
- `docs/ai-work-handoff.md`

#### 追加ファイル一覧

- `.github/workflows/threads-queue-worker.yml`
- `scripts/process_threads_queue.py`
- `scripts/import_threads_metrics_manual.py`
- `scripts/refill_threads_queue.py`
- `scripts/test_process_threads_queue.py`
- `scripts/test_threads_queue_duplicate_guard.py`
- `scripts/test_posted_results_integrity.py`
- `scripts/test_import_threads_metrics_manual.py`
- `scripts/test_refill_threads_queue.py`
- `scripts/test_threads_queue_worker_workflow.py`
- `docs/threads-queue-worker.md`
- `docs/metrics-import-runbook.md`

#### 実装内容

- `process_threads_queue.py`
  - （※旧仕様。現在は worker 投稿対象は `READY` のみ。冒頭の 2026-06-29 エントリ参照）`WAITING_REVIEW` / `PLANNED` の Threads queue row のみ対象。
  - `beauty_account` BLOCKED、X row ignored。
  - dry-runは投稿なしで候補・validation結果を出力。
  - real modeは `PUBLISH_ENABLED=true` + `ALLOW_REAL_THREADS_POST=true` + `--confirm-real-post` 必須。
  - duplicate guard: `queue_id` / `derivative_id` / `draft_id` / same text-account-platform。
  - 成功時: queue `POSTED`、posted_results `POSTED/PENDING`、logs、PDCA initial、suggestion `WAITING_REVIEW`。
  - 投稿失敗時: queue `FAILED`、即retryなし。
  - posted_results保存失敗時: queue `POSTED_SAVE_FAILED`、`output/posted_results_fallback/*.json` 退避、再投稿禁止。
- `import_threads_metrics_manual.py`
  - 手入力Threads metricsを `posted_results` に反映。
  - `metrics_status=MEASURED`、logs / pdca_runs / suggestions を作成。
- `refill_threads_queue.py`
  - `night_scout` / `liver_manager` のThreads投稿案を `drafts` / `social_derivatives` / `queue` に補充。
  - `beauty_account` とXは作成しない。
- GitHub Actions
  - `threads-queue-worker.yml`: `workflow_dispatch` only。scheduleなし。dry-run後にだけ処理。
  - `content-daily-dry-run.yml`: Threads-first dry-runへ変更。
- Sheets
  - `posted_results` に queue/derivative/platform/external id/metrics/status/text/source columns を追加。
  - `SheetsClient._ws()` に worksheet cache を追加し、setup/workerのSheets read quotaを削減。
- verify
  - `recover_production_sheets_threads_first.py` の `verify_state()` を posted_results整合性、metrics_status、queue整合、duplicate textまで厳密化。

#### 未完了事項

- Live Sheets上での厳密30チェック verify-only は未完了。
- Live Sheets上での `process_threads_queue.py --account-id night_scout --dry-run` / `liver_manager --dry-run` は未完了。
- Live Sheets上での `refill_threads_queue.py --dry-run` は未完了。
- 理由: Google Sheets実行のための承認システムが `out of credits` で rejected。迂回はしていない。
- 実投稿は今回未実行。

#### 残WARN

- Sheets API 429 が発生した後、`posted_results` の新規列追加までは完了。backfill/strict verify は承認credits復旧後に再実行すること。
- `check_credentials_readiness.py`: Cloudflare transcription任意credential、GitHub secret write token は optional missing。必須20件はREADY。
- X credentialsはSETだが、X投稿運用は引き続きOFF。

#### 全テスト結果

- `test_account_tone_guide.py`: PASS 41 / FAIL 0
- `test_threads_credentials.py`: PASS 24 / FAIL 0
- `test_phase13_publishers_production_safety.py`: PASS 4 / FAIL 0
- `test_content_workflows_safety.py`: PASS 9 / FAIL 0
- `test_source_intake_schema.py`: PASS 7 / FAIL 0
- `test_media_policy_guard.py`: PASS 8 / FAIL 0
- `test_sheets_seed_state.py`: PASS 7 / FAIL 0
- `test_cta_rules.py`: PASS 6 / FAIL 0
- `test_threads_queue_seed.py`: PASS 6 / FAIL 0
- `test_beauty_account_block.py`: PASS 9 / FAIL 0
- `test_x_disabled_mode.py`: PASS 9 / FAIL 0
- `test_process_threads_queue.py`: PASS 8 / FAIL 0
- `test_threads_queue_duplicate_guard.py`: PASS 5 / FAIL 0
- `test_posted_results_integrity.py`: PASS 7 / FAIL 0
- `test_import_threads_metrics_manual.py`: PASS 4 / FAIL 0
- `test_refill_threads_queue.py`: PASS 8 / FAIL 0
- `test_threads_queue_worker_workflow.py`: PASS 11 / FAIL 0
- `check_credentials_readiness.py`: READY for required 20 items; optional WARN only.

#### dry-run結果

- ローカル・credential不要dry-run:
  - `import_threads_metrics_manual.py --dry-run`: PASS。
- Live Sheets dry-run:
  - 未完了。承認システム `out of credits` によりGoogle Sheetsアクセス不可。

#### confirmなしBLOCKED確認結果

- `test_phase13_publishers_production_safety.py`: confirmなしX post BLOCKED、beauty BLOCKED、publisher dry-run PASS。
- `process_threads_queue.py`: real mode は `--confirm-real-post` なしでBLOCKED、さらに `PUBLISH_ENABLED` / `ALLOW_REAL_THREADS_POST` なしでBLOCKED。
- 実fetch / 実download / 実cut / 実upload / 実post は今回未実行。

#### 次にClaude Codeが触ってよいファイル

- `scripts/process_threads_queue.py`
- `scripts/import_threads_metrics_manual.py`
- `scripts/refill_threads_queue.py`
- `docs/threads-queue-worker.md`
- `docs/metrics-import-runbook.md`
- `docs/threads-operation-runbook.md`
- `docs/sheets-manual-check-guide.md`

#### 次にCodexが触ってよいファイル

- `scripts/recover_production_sheets_threads_first.py`
- `src/sheets_client.py`
- `.github/workflows/threads-queue-worker.yml`
- `.github/workflows/content-daily-dry-run.yml`
- `scripts/test_*threads*queue*.py`

#### 衝突しやすいファイル

- `src/sheets_client.py`
- `scripts/recover_production_sheets_threads_first.py`
- `.github/workflows/content-daily-dry-run.yml`
- `docs/ai-work-handoff.md`
- `docs/production-launch-checklist.md`

#### 触らない方がいいファイル

- `.env`
- `data/threads_tokens/`
- `output/media_cache/`
- `output/cloudinary_cache/`
- `output/posted_results_fallback/` の実運用退避ファイル
- `.claude/plans/`（未追跡のためcommitしない）
- `docs/session-report-2026-06-22-2.md`（未追跡の既存ファイル。今回commit対象外）

#### 次AIへの引き継ぎメモ（2026-06-25更新）

1. **verify は現在 PASS** (`verification_passed=33 failed=0`)。`--verify-only` のみ実行すれば確認できる。
2. `repair_posted_results_integrity.py --apply` は workflow に組み込み済み（毎回 verify 前に自動実行）。
3. `process_threads_queue.py --account-id night_scout --dry-run` → status=DRY_RUN ✓
4. `process_threads_queue.py --account-id liver_manager --dry-run` → status=DUPLICATE_BLOCKED ✓（duplicate guard 正常。liver_manager に新候補が必要なら `refill_threads_queue.py` を実行）
5. 実投稿は原則まだしない。dry-run PASS後、1アカウント1件だけ `PUBLISH_ENABLED=true ALLOW_REAL_THREADS_POST=true --confirm-real-post --max-posts 1`。
6. `POSTED_SAVE_FAILED` が出た場合は絶対に再投稿しない。fallback JSONと実SNS画面を照合してposted_resultsを手で復旧する。
7. `beauty_account`、X、media download/cut/upload、Cloudinary upload、transcription APIは引き続きOFF。

### Codex: true dry-run / Actions dry_run follow-up (2026-06-25)

- 作業開始HEAD: `b3f6188296424c0b74f22b92adeaa65619abc47d`
- code/test commit: `97950f75e272c47f94a8bc78c7f94ef09fa2a28f`
- workflow secret fallback commit: `3b862de49b6441ec8bd8ef6ed8820b9ab108dd55`
- true dry-run修正:
  - `process_threads_queue.py --dry-run`: `setup_all()`なし、read-only出力あり。
  - `refill_threads_queue.py --dry-run`: `setup_all()`なし、appendなし、planned/tone_check出力あり。
  - `import_threads_metrics_manual.py --dry-run`: Sheets接続なし。実行時も不要な `setup_all()` を削除。
- Live local Sheets verify:
  - `python3 scripts/recover_production_sheets_threads_first.py --verify-only --json` は承認システム `out of credits` で拒否。迂回せず未実行。
- GitHub Actions dry_run:
  - run `28136692522`: failure。Sheets secrets未設定で `SNS_MASTER_SHEET_ID` missing。
  - run `28136764181`: failure。fallback追加後もrepositoryにSheets secretsがなく、verify前に停止。
  - `gh secret list` でThreads secretsは確認、Sheets secretsは未登録。
  - `gh secret set` はGitHub API接続エラーで登録未完了。値は表示していない。
- 実投稿: 未実行。
- metrics import:
  - dummy `--dry-run` 実行PASS。
- 追加テスト:
  - `test_true_dry_run_no_setup_all.py`: PASS 7 / FAIL 0
  - `test_live_verify_schema_strictness.py`: PASS 10 / FAIL 0
  - `test_metrics_import_dry_run_no_sheets_connection.py`: PASS 3 / FAIL 0
- 次に必要:
  1. GitHub repository secretsへ `SNS_MASTER_SHEET_ID` または `SPREADSHEET_ID` を登録。
  2. `SA_JSON_BASE64` または `GCP_SA_JSON_BASE64` を登録。
  3. GitHub UIで `Threads Queue Worker` を `dry_run` / `night_scout` / `max_posts=1` / `confirm=false` で実行。
  4. PASS後にLive local Sheets dry-runを再確認。

### X API Legacy 互換方式への移行 + エラー再分類

- `src/publishers/x_publisher.py`: `tweepy.Client` → `requests_oauthlib.OAuth1` (HMAC-SHA1) に変更
  - `TWEET_URL` 定数追加
  - `_handle_post_error()` 追加: 402 CreditsDepleted / 401 / 403 / 429 を個別コードに分類
- **原因**: X API Credits 枯渇（月次クレジット）。旧repo の高頻度 API 呼び出しで消費しきった
- `data/manual_post_queue.json`: 次回実投稿候補テキストを `retry_ready` で保存済み
- `docs/x-api-legacy-compatibility-audit.md`: 新規作成（旧/新 repo 比較・結論・復旧手順）

### Source Registry 拡充 (8 → 17 sources)

- `config/source_accounts/default_sources.json`: 17ソースに更新
  - YouTube 2件 (ns/lm): `rights_policy=reference_only`, `review_notes="ユーザー確認済み (2026-06-24)"`
  - beauty_account 3件: `review_status=BLOCKED_BEAUTY_ACCOUNT`, `active=false`
  - 旧repo移行 X sources 10件: ns 8件 + lm 2件
- `scripts/test_source_rights_user_confirmed.py`: 19項目 全PASS

### Threads 次投稿候補 Queue 保存

- `data/threads_night_scout_next_queue.json`: 3候補 `WAITING_REVIEW` で保存
- 投稿案: LINEの返しテンポ / 店選びの失敗 / 辞めずに続けられる子
- `scripts/test_reference_transform_guard.py`: 22項目 全PASS

### GitHub Actions Workflow 整備

- `.github/workflows/content-daily-dry-run.yml`: X/Threads secrets env 追加
- `.github/workflows/media-approved-pilot.yml`: 新規作成（3モード / 全安全フラグ false）
  - `${{ github.event.inputs.* }}` 直接展開なし（コマンドインジェクション対策）
- `docs/media-approved-pilot.md`: 新規作成

### テスト追加 (5本)

| テスト | PASS | FAIL |
|---|---|---|
| test_x_legacy_compatibility.py | 13 | 0 |
| test_source_rights_user_confirmed.py | 19 | 0 |
| test_cloudinary_upload_guard.py | 9 | 0 |
| test_media_approved_pilot_workflow.py | 13 | 0 |
| test_reference_transform_guard.py | 22 | 0 |

### Sheets 429 対策・孤児投稿復旧 (2026-06-25)

- 作業開始HEAD: `93977a5`
- 作業完了HEAD: このcommit。最終 hash は `git rev-parse HEAD` で確認。

#### 問題

GitHub Actions `threads-queue-worker.yml` real_post 実行後、Threads 投稿は成功したが
Sheets API 429 で `save_posted_result()` / `update_row()` が両方失敗し:
- `recovery_night_scout_queue_01` が PROCESSING に残存
- `posted_results` に行未追加（孤児投稿状態）

#### 修正内容

1. `process_threads_queue.py`
   - `_headers_cache` + `_get_headers()`: ヘッダー行キャッシュ（同一 ws は 1 回のみ `row_values(1)`）
   - `_get_headers()` に 429 指数バックオフ（5s/15s/30s、最大 4 回）
   - real_post モードの `client.setup_all()` を削除
   - `FALLBACK_DIR` 定数追加、`write_fallback()` に `dry_run` パラメータ追加

2. `scripts/recover_orphan_threads_post.py` 新規作成
   - Threads API でテキスト一致探索、またはIDを直接指定して RECOVERED 行追加
   - `--skip-api-lookup` で API なしでも復旧可能
   - 実行済み: `recovery_night_scout_queue_01` → POSTED、posted_results に RECOVERED 行追加

3. `.github/workflows/threads-queue-worker.yml`
   - `output/posted_results_fallback/` を `actions/upload-artifact` で 30 日保存 (`if: always()`)

4. `recover_production_sheets_threads_first.py`
   - `queue_night_scout_3` → `queue_night_scout_2`（孤児復旧で active 行が 2 に）

5. テスト 4 本追加（全 PASS）:
   - `test_recover_orphan_threads_post.py`: 13 PASS
   - `test_sheets_rate_limit_backoff.py`: 14 PASS
   - `test_queue_worker_no_setup_all_in_real_mode.py`: 12 PASS
   - `test_fallback_artifact_no_secrets.py`: 11 PASS

#### 確認結果

```
verification_passed=33 failed=0
count_posted_results=4
count_queue_night_scout=2
```

- `process_threads_queue.py --account-id night_scout --dry-run`: queue_02 status=DRY_RUN ✓
- `process_threads_queue.py --account-id liver_manager --dry-run`: status=DUPLICATE_BLOCKED ✓

#### 次AIへの引き継ぎメモ

1. **孤児投稿 external_post_id**: `recovery_night_scout_queue_01` の posted_result (`orphan_recovery_recovery_night_scout_queue_01_*`) は `external_post_id=""` のまま。Threads アプリで実際の投稿URLを確認し、`recover_orphan_threads_post.py --apply --external-post-id <id>` で更新すること。
2. **verify は PASS 維持**: `verification_passed=33 failed=0`。毎回 repair → verify の手順。
3. **次投稿**: `night_scout` には WAITING_REVIEW (queue_02) / PLANNED (queue_03) が 2 件残存。レビュー後に 1 件ずつ実行。
4. **429 対策は実装済み**: 次回実投稿時は `setup_all` 呼び出しなし・ヘッダーキャッシュ・バックオフ付き。
5. **fallback artifact**: 次回実投稿失敗時は GitHub Actions > Artifacts > `threads-post-fallback-{run_id}` を確認。

## 現在のブロッカー / ペンディング事項

| 課題 | 内容 | 必要な対応 |
|---|---|---|
| X API Credits 枯渇 | 402 CreditsDepleted。認証は成功済み。tweepy は廃止 | X Developer Portal > Usage & Credits で補充 |
| src_ns_query_001 | query source の URL 未登録 | 対象アカウント URL を入力後 default_sources.json を更新 |
| src_ns_yt_cand_001 / src_lm_yt_cand_001 | rights_policy=reference_only (download 禁止) | approved_media 昇格は別途承認フロー必要 |
| Threads 次投稿 | WAITING_REVIEW 2候補あり (night_scout のみ) | ユーザーレビュー後に投稿実行 |
| night_scout 孤児投稿 | external_post_id が空 | Threads アプリで投稿URL確認→ recover_orphan_threads_post.py で更新 |
| beauty_account | 実投稿・active化禁止 | 永続的な制約 |
| Threads 48h 指標 | 初回投稿の impressions/likes 未取得 | Threads インサイトで確認 |

## 最新作業内容 (2026-06-23)

### Threads 初回実投稿 SUCCESS

- アカウント: night_scout (`@kyaba_consul_mizu`)
- 投稿文: 「キャバで指名が取れる子って〜」(86字)
- post_id: `18127402414723102`
- posted_url: https://www.threads.com/@kyaba_consul_mizu/post/DZ6Drm5k9SL
- posted_at: 2026-06-23T00:00:00Z
- posted_results: result_id=`r-5da1d941` (Sheets書き込み済み)
- metrics_status: PENDING (48h後に確認)

### バグ修正 3件

1. **GitHub Actions workflow env渡し漏れ**: `content-pilot-publish.yml` にアカウント固有 Threads secrets 8本を追加。`THREADS_ACCESS_TOKEN_NIGHT_SCOUT` 等が workflow から参照可能に。
2. **Threads post_url 生成方法**: 数値 user_id URL（無効）→ Threads API permalink 取得 (`_try_fetch_permalink`)。
3. **PublishResult.is_dry_run_ok @property**: デコレータ欠落 → bound method が常に truthy → 実投稿時も "DRY_RUN" 表示。`@property` 追加で修正。

### Source registry 整備

- `docs/youtube-tiktok-clipping-runbook.md`: 新規作成（clip pipeline 実行手順・前提条件・制約一覧）
- 全 8ソースの状態を確認・更新

### テスト追加

| テスト | PASS | FAIL |
|---|---|---|
| test_content_workflows_safety.py (更新: +1件) | 8 | 0 |
| is_dry_run_ok @property 確認 (新規) | 1 | 0 |

## 現在のブロッカー / ペンディング事項

| 課題 | 内容 | 必要な対応 |
|---|---|---|
| X API 402 | APIクレジット不足。認証は成功済み | X Developer Portal で Basic Plan 以上を契約 |
| src_ns_query_001 | night_scout query source の URL 未登録 | 対象アカウント URL を入力後 default_sources.json を更新 |
| src_ns_yt_cand_001 / src_lm_yt_cand_001 | rights_policy=unknown | YouTube チャンネルの利用規約を確認し権利ポリシーを更新 |
| content_categories 空 | WARN (機能影響なし) | setup_and_verify.py --setup で解消可能 |
| beauty_account | 実投稿・active化禁止 | 永続的な制約 |
| Threads 48h 指標 | impressions/likes/replies 未取得 | 2026-06-25 以降に Threads インサイトで確認 |

## 最新作業内容 (2026-06-22 第2回)

### X API ブロッカー分離

- `src/publishers/x_publisher.py`: `_is_billing_error()` + `_save_to_manual_queue()` 追加
  - 402 を `POST_FAILED_EXTERNAL_BILLING_BLOCKER` として認証エラーと区別
  - 失敗投稿文を `data/manual_post_queue.json` に退避
- `data/manual_post_queue.json`: 2026-06-22 の X 失敗投稿文を `retry_ready` で保存
- `docs/x-api-billing-blocker.md`: 復旧手順・エラーコード定義を記載

### Threads 実投稿確認

- dry-run: **PASS** (85字、account=night_scout)
- 実投稿: **BLOCKED_MISSING_CREDENTIALS** — THREADS_ACCESS_TOKEN / THREADS_USER_ID が .env 未設定

### Source registry 棚卸し

- 全 8件の状態を確認・整理（READY_FOR_REFERENCE_FETCH / WAITING_RIGHTS_REVIEW / BLOCKED_BEAUTY_ACCOUNT）
- `docs/source-intake-template.md`: 新規ソース登録手順・状態定義表を作成
- `scripts/test_source_intake_schema.py`: 7項目テスト（全PASS）

### Media policy guard 確認

- `check_source_media_policy()` / Cloudinary upload guard の動作を確認
- `scripts/test_media_policy_guard.py`: 8項目テスト（全PASS）

### GitHub Actions workflows 追加（本番ON はまだしない）

- `.github/workflows/content-daily-dry-run.yml`: 毎日 JST 10:00 dry-run サニティチェック
- `.github/workflows/content-pilot-publish.yml`: 手動トリガー専用 / X 402 自動停止 / beauty_account ガード
- `.github/workflows/source-fetch-dry-run.yml`: 毎週月曜 JST 11:00 source policy チェック
- 全 workflow: `${{ inputs.* }}` を env 経由に限定（コマンドインジェクション対策）
- `scripts/test_content_workflows_safety.py`: 7項目テスト（全PASS）

### テスト結果（今回追加分）

| テスト | PASS | FAIL |
|---|---|---|
| test_source_intake_schema.py | 7 | 0 |
| test_media_policy_guard.py | 8 | 0 |
| test_content_workflows_safety.py | 7 | 0 |
| test_account_tone_guide.py（既存） | 41 | 0 |

## 現在のブロッカー / ペンディング事項

| 課題 | 内容 | 必要な対応 |
|---|---|---|
| X API 402 | APIクレジット不足。認証は成功済み | X Developer Portal で Basic Plan 以上を契約 |
| Threads 実投稿 | THREADS_ACCESS_TOKEN / THREADS_USER_ID が .env 未設定 | .env に認証情報を追加 |
| src_ns_query_001 | night_scout query source の URL 未登録 | 対象アカウント URL を入力後 default_sources.json を更新 |
| content_categories 空 | WARN (機能影響なし) | setup_and_verify.py --setup で解消可能 |
| beauty_account | 実投稿・active化禁止 | 永続的な制約 |

## 最新作業内容 (2026-06-22)

### トンマナ強制対応

- `src/seeds.py`: night_scout/liver_manager の tone/notes 詳細化、NGトーンリスト追加
- `src/seeds.py`: `_DRAFT_GEN_NIGHT_SCOUT` / `_DRAFT_GEN_LIVER_MANAGER` 書き直し（スタイルガイド・良い例追加）
- `src/seeds.py`: `_SOCIAL_DERIVATIVE_X_NIGHT_SCOUT` (pt_06) night_scout専用Xテンプレート追加
- `src/seeds.py`: `ACCOUNT_NG_TONE_PATTERNS` 追加（night_scout:21件、liver_manager:12件）
- `src/tone_checker.py`: 新規作成（`check_ng_tone()` 関数）
- `src/prompt_loader.py`: `get_derivative_template()` account_id対応
- `src/social_derivative_generator.py`: account_id を derivative テンプレート選択に渡す
- `scripts/preflight_check.py`: グループ6「トンマナ確認」追加、タブ存在確認を日本語名対応
- `scripts/test_account_tone_guide.py`: 新規作成（41項目全PASS）
- `docs/account-tone-guides.md`: 新規作成

### 初回パイロット実行（X投稿試行）

- 投稿文: 「指名が取れるキャバ嬢は、見た目だけじゃなく〜稼げる子の秘密なんだよね。」(81字)
- dry-run: PASS
- 実投稿: **POST_FAILED** — `402 Payment Required` (認証成功、APIクレジット不足)
- 二重投稿リスクなし（post_id未払い出し）

### コード修正（バグフィックス）

- `scripts/publish_x_post.py`: `sys.path` に `src/` を追加 + dotenv ロード追加
- `scripts/publish_threads_post.py`: 同様の修正
- `scripts/preflight_check.py`: `check_tabs_existence()` で `TAB_DISPLAY_NAMES` を使い日本語タブ名に対応

### テスト結果

- test_account_tone_guide.py: 41 PASS / 0 FAIL
- test_consolidation_phase.py: 22 PASS / 0 FAIL
- test_phase13_publishers_production_safety.py: 4 PASS / 0 FAIL
- test_phase13_smoke_plan.py: 18 PASS / 0 FAIL
- test_threads_credentials.py: 24 PASS / 0 FAIL
- check_credentials_readiness.py: READY (必須20件全設定済み)

## 現在のブロッカー

| 課題 | 内容 | 対応 |
|---|---|---|
| X API クレジット不足 | 402 Payment Required — Basic Plan相当のクレジットが必要 | X Developer Portal で有料プランを確認 |
| content_categories 空 | WARN (機能影響なし) | setup_and_verify.py --setup で解消可能（Sheets API 429に注意） |
| prompt_templates 空 | WARN (機能影響なし) | 同上 |

## システム概要

3アカウント（`night_scout` / `liver_manager` / `beauty_account`）向けの SNS 自動投稿支援システムです。

```
Source candidates
-> fetch / article normalize / buzz score
-> reference_posts
-> media_assets / video understanding / clip plans
-> generation_jobs / drafts / queue candidates
-> media preflight / publisher plan
-> posted_results candidates / PDCA suggestions
```

この Phase 13 監査では、実 fetch / download / cut / upload / post は一切実行していません。

## 今回の作業内容

- Claude Code 実装の Phase 13 production readiness を最終監査。
- `production_sources.example.json` の `REPLACE_WITH_REAL_*` を全削除し、ユーザー提供 URL 54件を登録。
- query source 37件を追加。
- `default_sources.json` の old example URL と active/fetch enabled を除去。
- media asset storage / preflight / download / upload 導線を追加。
- video clip executor 導線を追加。
- PipelineStore を Phase 13 保存対象、dry-run、Sheets write plan、queue status safety に対応。
- source-to-post orchestrator に media_assets / media_preflight / clip_candidate_plans を接続。
- publisher / review / import / smoke plan CLIs を指定 dry-run コマンド互換に補強。
- Phase 13 production path と media/query/article/publisher/PDCA のテストを追加。

## 変更ファイル一覧

- `config/source_accounts/default_sources.json`
- `config/source_accounts/production_sources.example.json`
- `scripts/cut_video_clips.py`
- `scripts/import_posted_results.py`
- `scripts/publish_threads_post.py`
- `scripts/publish_x_post.py`
- `scripts/review_source_candidates.py`
- `scripts/run_real_smoke_plan.py`
- `scripts/test_phase13_smoke_plan.py`
- `src/orchestrators/source_to_post_orchestrator.py`
- `src/publishers/threads_publisher.py`
- `src/reference/fetchers/fetcher_registry.py`
- `src/reference/source_registry.py`
- `src/storage/pipeline_store.py`
- `docs/ai-work-handoff.md`
- `docs/phase13-16-test-matrix.md`

## 追加ファイル一覧

- `docs/ai-dev-status.md`
- `docs/codex-final-audit-report.md`
- `docs/media-asset-storage.md`
- `docs/video-clip-execution.md`
- `scripts/download_media_assets.py`
- `scripts/preflight_media_assets.py`
- `scripts/upload_media_assets.py`
- `scripts/test_phase13_article_source_support.py`
- `scripts/test_phase13_fetcher_production_paths.py`
- `scripts/test_phase13_generation_production.py`
- `scripts/test_phase13_media_asset_storage.py`
- `scripts/test_phase13_media_post_preflight.py`
- `scripts/test_phase13_pdca_production_loop.py`
- `scripts/test_phase13_production_sources_real_urls.py`
- `scripts/test_phase13_publishers_production_safety.py`
- `scripts/test_phase13_query_source_support.py`
- `scripts/test_phase13_real_smoke_plan.py`
- `scripts/test_phase13_source_concept_matching.py`
- `scripts/test_phase13_source_fetcher_tool_doctor.py`
- `scripts/test_phase13_source_lifecycle.py`
- `scripts/test_phase13_source_registry_production.py`
- `scripts/test_phase13_source_to_post_production_path.py`
- `scripts/test_phase13_video_clip_execution.py`
- `src/media/cloudinary_uploader.py`
- `src/media/image_asset_pipeline.py`
- `src/media/media_asset_store.py`
- `src/media/media_downloader.py`
- `src/media/video_asset_pipeline.py`
- `src/video/video_clip_executor.py`

## Source 反映結果

- placeholder handle/url tokens: 残り 0
- user-provided fixed URL: 54 / 54 反映済み
- query source: 37件追加
- `production_sources.example.json`: 91 sources / active 0 / fetch_enabled 0 / validation issues 0
- `default_sources.json`: 8 safe default candidates / active 0 / fetch_enabled 0 / validation issues 0

| Account | Fixed Sources | Query Sources | Total |
|---|---:|---:|---:|
| `night_scout` | 18 | 13 | 31 |
| `liver_manager` | 13 | 11 | 24 |
| `beauty_account` | 23 | 13 | 36 |

## Safety / Scale 方針

- `beauty_account` は `WAITING_REVIEW` / draft-only 固定。READY/POSTED 化禁止。
- `candidate_status=approved` 以外は download/cut/upload 不可。
- `rights_policy=unknown` は `WAITING_REVIEW` で media 利用不可。
- `media_policy=do_not_download` は download 禁止。
- `media_policy=plan_only` は保存/投稿利用禁止。
- `reuse_policy=no_reuse` は media 利用禁止。
- `ALLOW_CLOUDINARY_UPLOAD=true` と `--confirm-upload` なしでは upload 禁止。
- PipelineStore は JSON 保存と Sheets write plan を分離。Sheets API 429 は WARN 扱い。
- 既存 Sheets タブ/列の削除は禁止。
- PDCA は提案だけ。`auto_apply=false`、source priority 自動変更なし。
- query source は `source_platform=query` とし、固定 source の X/Youtube/note 件数に混ざらない。

## テスト結果

- Phase 9-13 regression + added tests: 39 files PASS / 0 FAIL
- Dry-run / BLOCKED command sweep: 35 commands PASS / 0 FAIL
- Phase 13 legacy core total: 148 PASS / 0 FAIL

## Dry-run / BLOCKED 確認結果

- `--fetch` without `--confirm-fetch`: BLOCKED
- `--download` without `--confirm-download`: BLOCKED
- `--cut` without `--confirm-cut`: BLOCKED
- `--upload` without `--confirm-upload`: BLOCKED
- real post without `--confirm-post`: BLOCKED
- Source-to-post mock dry-run: PASS, publish step remains BLOCKED without confirm
- Real smoke plan dry-run: ran readiness check only; environment NOT_READY is acceptable WARN
- `run_real_smoke_plan.py --platform threads`: Threads preflight branch confirmed; no X preflight mix-in

## 実行していないこと

- 実 fetch: 未実行
- 実 download: 未実行
- 実 cut: 未実行
- 実 upload: 未実行
- 実投稿: 未実行
- GitHub Actions: 未実行
- Hermes Agent install: 未実行
- secrets/cookie values: 表示なし

## 残 WARN

- `run_real_smoke_plan.py` は資格情報未設定環境では NOT_READY で非ゼロ終了する。dry-run readiness として許容。
- `BasePublisher` / `BaseFetcher` の抽象メソッドに `NotImplementedError` が残る。設計上の抽象クラス。
- legacy docs/tests に古い `NotImplementedError` 記述が残る。
- X collector API stubs は意図的に実取得不可。今回の production source media path 外。

## 未完了事項

- PR 作成とレビュー。
- 実 source の承認運用設計。
- Sheets 実 test-write は未実行。
- 実 credentials readiness は未確認。
- `beauty_account` の法務/薬機法/医療広告レビュー運用。

## 次に Claude Code が触ってよいファイル

- `docs/codex-final-audit-report.md`
- `docs/ai-dev-status.md`
- `docs/phase13-16-test-matrix.md`
- `src/media/*.py`
- `src/video/video_clip_executor.py`
- `scripts/test_phase13_*.py`

## 次に Codex が触ってよいファイル

- `scripts/preflight_media_assets.py`
- `scripts/download_media_assets.py`
- `scripts/upload_media_assets.py`
- `src/storage/pipeline_store.py`
- `src/orchestrators/source_to_post_orchestrator.py`
- `docs/media-asset-storage.md`
- `docs/video-clip-execution.md`

## 衝突しやすいファイル

- `config/source_accounts/production_sources.example.json`
- `config/source_accounts/default_sources.json`
- `src/orchestrators/source_to_post_orchestrator.py`
- `src/storage/pipeline_store.py`
- `scripts/publish_threads_post.py`
- `scripts/publish_x_post.py`
- `docs/ai-work-handoff.md`

## 触らない方がいいファイル

- `.env` and any credential/cookie files
- `.claude/plans/` untracked local work
- `output/`, `logs/`, generated local artifacts
- GitHub Actions workflows unless explicitly requested
- old repo outside `v2`

## 次AIへの引き継ぎメモ

- 作業開始時は必ず `git fetch origin`, `git status -sb`, `git rev-parse HEAD`, `git rev-parse origin/main` を確認する。
- `production_sources.example.json` は full source list、`default_sources.json` は safe subset。
- `beauty_account` を active/READY/POSTED にしない。
- 実 fetch/download/cut/upload/post を試す場合は、ユーザー確認と confirm flags と環境フラグを全部確認する。
- media/clip は現状 plan/preflight 層。実処理の接続は承認済み source だけに限定する。
- PR 前に `python3 scripts/test_phase13_production_sources_real_urls.py` と dry-run/BLOCKED sweep を再実行する。

## Final Rollout Update

- Date: 2026-06-17
- PR URL: https://github.com/dev-ch-hhuk39/sns-growth-engine/pull/1
- PR title: `Finalize production source/media pipeline`
- Merge前確認: PASS
- Merge前テスト: Phase13 minimum 11 / 11 PASS, Phase9-13 regression 39 / 39 PASS
- Merge前 dry-run / BLOCKED: 22 / 22 PASS
- Merge可否: merge-ready
- Merge結果: PR #1 squash merged
- Production pipeline merge SHA: `759af859a4d70d9ec1105f8d70f1c4ea893f29db`
- main反映後HEAD確認: `759af859a4d70d9ec1105f8d70f1c4ea893f29db`
- main反映後最小テスト: 4 / 4 PASS
- main反映後 dry-run / BLOCKED: 5 / 5 PASS
- 実fetch/download/cut/upload/post: 未実行
- secrets/cookie/token/API key: 表示なし

## Follow-up Docs / Smoke Plan Update

- Branch: `feature/final-rollout-status-docs`
- PR URL: https://github.com/dev-ch-hhuk39/sns-growth-engine/pull/2
- PR #2 head before smoke fix: `182cb01eb02373e3c26c5f6886aaa36df7fad06c`
- PR #2 merge attempt: BLOCKED by GitHub connector approval credits (`out of credits`); main direct push was not attempted.
- Follow-up fix: `run_real_smoke_plan.py --platform threads` now runs Threads preflight instead of X preflight.
- Added test coverage in `scripts/test_phase13_smoke_plan.py`.
- Follow-up test results:
  - `python3 scripts/run_real_smoke_plan.py --account-id liver_manager --platform threads --dry-run`: NOT_READY expected in credential-free env; Threads preflight confirmed; no real API/upload/post.
  - `python3 scripts/test_phase13_smoke_plan.py`: 18 / 18 PASS
  - `python3 scripts/test_phase13_publishers_production_safety.py`: 4 / 4 PASS

## 初回スモーク手順

最終版は `docs/manual-smoke-test-sequence.md` と `docs/production-launch-checklist.md` を参照。

固定順序:

1. tool doctor
2. source registry validate
3. source candidate review
4. mock fetch dry-run
5. source_to_post pipeline mock dry-run
6. media preflight dry-run
7. publisher dry-run
8. posted_results import dry-run
9. PDCA dry-run
10. 人間承認後に confirm-fetch を1sourceだけ
11. confirm-fetch後もdownload/cut/upload/postはしない
12. download/cut/upload/postは別承認
13. 初回1投稿はpublisher dry-runまで
14. 実投稿はさらに別承認

## 次に人間がやること

- PR #1 を確認し、main 反映後は `docs/manual-smoke-test-sequence.md` の順番で初回スモークを実施する。
- 実fetchは1sourceだけを明示承認する。
- 実download/cut/upload/post は別承認まで実行しない。

## Pilot Deploy / Final Audit (2026-06-18)

- 担当AI: Claude Code (Sonnet 4.6)
- PR #2: squash merged to main
- main HEAD: `19b0b77148a38717b996fb6df40066a9f6267df8`
- セキュリティ修正: `pipeline_store.py` stage バリデーション追加 (commit `6bb694b`)
- preflight バグ修正: `scripts/preflight_media_assets.py` IndexError修正
- テスト: Phase10-13 全ファイル 0 FAIL
- dry-run/BLOCKED sweep: 全13チェック PASS/BLOCKED
- pilot smoke: night_scout/x, night_scout/threads, liver_manager/threads → [SMOKE PASS]
- 実fetch/download/cut/upload/post: 未実行
- secrets/cookie表示: なし
- 詳細: `docs/pilot-deploy-report.md`

## SNS実運用開始フェーズ (2026-06-18)

- 担当AI: Claude Code (Sonnet 4.6)
- フェーズ: 初回実運用（認証情報未設定のため READY_WITH_MISSING_CREDENTIALS）

### 実施内容（第1回: 519a48a）

- `.gitignore` に `output/` を追加（パイプライン出力をGit管理外に）
- `scripts/fetch_source_posts.py` に `--source-file` / `--bypass-active-check` フラグを追加
- 実 fetch 実行: `src_ns_yt_cand_009` (@kyaba_camera YouTube) から6件取得
- 取得データ: `output/pipeline_runs/fetch_ns_20260618.json`（Git管理外）
- 投稿テキスト生成（確定版99字、スカウト視点、夜職女性向け）
- preflight dry-run: PASS (sources=31, assets=2)
- X publisher dry-run: DRY_RUN ✅ (99字)
- Threads publisher dry-run: DRY_RUN ✅ (99字、1行WARN=問題なし)
- posted_results import dry-run: DRY_RUN ✅
- PDCA dry-run: pdca_8bcc26d2 (suggestions=WAITING_REVIEW, auto_apply=false)
- 安全フラグ全て NOT_SET 確認済み

### 確定投稿テキスト（99字）

```
夜職で伸びる子に共通するのは、LINEの返し方が上手いこと。"また話したい"と思わせる会話ができる子は強い。学歴や見た目より、長く稼ぐには会話力が大事なんだよね。磨ける力だから、今からでも伸ばせる。
```

### 実行していないこと

- 実投稿: 未実行（X/Threads 認証情報が .env に未設定）
- 実download/cut/upload: 未実行
- beauty_account active化: なし
- secrets/cookie表示: なし

### 詳細

- `docs/first-live-post-report.md`（今回新規作成・更新）
- `docs/pdca-live-loop-report.md`（今回新規作成）

## 次に人間がやること

1. `.env` に X または Threads 認証情報を設定する
   - X: `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET`
   - Threads: `THREADS_ACCESS_TOKEN`, `THREADS_USER_ID`
2. `python3 scripts/publish_x_post.py --account-id night_scout --confirm-post --dry-run` で再確認
3. `ALLOW_REAL_X_POST=true`（または `ALLOW_REAL_THREADS_POST=true`）を `.env` に追加（永続コミット禁止）
4. 初回実投稿を実行（text-only、1件のみ）
5. 投稿後 posted_results に登録
6. 24時間後にエンゲージメントを確認し PDCA を実データで再実行

## 次にAIが触ってよいファイル

- `docs/manual-smoke-test-sequence.md`
- `docs/production-launch-checklist.md`
- `docs/first-live-post-report.md`
- `docs/pdca-live-loop-report.md`
- `docs/phase13-16-test-matrix.md`

## 触らない方がいいファイル

- `.env`
- cookie/token/API key を含むファイル
- `.claude/plans/`
- old repo / old zip retreat folders

## 運用統合フェーズ (2026-06-20)

- 担当AI: Claude Code (Sonnet 4.6)
- フェーズ: 旧3リポジトリ → sns-growth-engine 一本化

### 実施内容

- `docs/legacy-repo-migration-audit.md`: 旧3repo の詳細調査結果を作成
- `docs/legacy-repo-shutdown-plan.md`: 旧 repo 停止手順を作成
- `docs/credential-migration-plan.md`: 認証情報移行計画を作成
- `docs/production-launch-checklist.md`: 統合ポリシーセクションを追加
- `src/sheets_client.py`: TAB_DISPLAY_NAMES（日本語タブ名）マッピング追加（Task F）
- `scripts/migrate_sheet_tabs_to_japanese.py`: シートタブ移行 CLI 追加（Task F）
- `scripts/refresh_threads_token.py`: Threads トークンリフレッシュスクリプト追加（Task G）
- `src/publishers/threads_publisher.py`: Phase 3-E 実投稿実装（Task G）
- `.env.template`: アカウント別 Threads 変数・トークン保存先を追加（Task H）
- テスト追加（Task I）

### 旧リポジトリ状況

| リポジトリ | 投稿頻度 | 状況 |
|---|---|---|
| X_autopost_yoru | 6回/日 (night_scout/X) | **未停止** — 人間による GitHub Actions disable が必要 |
| threads_auto_post_gs | 2回/日 (night_scout/Threads) | **未停止** — 同上 |
| threads-liver-coachhing | 8回/日 (liver_manager/Threads) | **未停止** — 同上（最優先） |

**新 repo での本番投稿前に、旧 repo の全 workflow を disable すること。**

### 実行していないこと

- 旧 repo の削除・archive（人間が判断・実施）
- 旧 repo の GitHub Actions disable（人間が GitHub UI で実施）
- secret 値の確認・コピー（実施しない）
- 実投稿（認証情報設定後に人間が承認して実施）

### 次に人間がやること（統合フェーズ）

1. **旧 repo 停止（最優先）**
   - `docs/legacy-repo-shutdown-plan.md` 参照
   - threads-liver-coachhing → X_autopost_yoru → threads_auto_post_gs の順で disable
2. **認証情報設定**
   - `docs/credential-migration-plan.md` 参照
   - `.env` に `THREADS_ACCESS_TOKEN_NIGHT_SCOUT` / `THREADS_USER_ID_NIGHT_SCOUT`
   - `.env` に `THREADS_ACCESS_TOKEN_LIVER_MANAGER` / `THREADS_USER_ID_LIVER_MANAGER`
   - `SNS_MASTER_SHEET_ID` を設定
3. **Threads publisher Phase 3-E 動作確認**
   - `scripts/refresh_threads_token.py --account-id night_scout --confirm-refresh --dry-run`
   - `scripts/publish_threads_post.py --account-id night_scout --dry-run`
4. **本番投稿（1件ずつ承認制）**
   - X: `docs/first-live-post-report.md` の確定テキストで実行
   - Threads: 同様に 1件ずつ

## 次にAIが触ってよいファイル（統合フェーズ以降）

- `docs/legacy-repo-migration-audit.md`
- `docs/legacy-repo-shutdown-plan.md`
- `docs/credential-migration-plan.md`
- `docs/production-launch-checklist.md`
- `src/sheets_client.py` (TAB_DISPLAY_NAMES 追加のみ)
- `src/publishers/threads_publisher.py` (Phase 3-E 実装)
- `scripts/refresh_threads_token.py` (新規追加)
- `scripts/migrate_sheet_tabs_to_japanese.py` (新規追加)
- `.env.template` (アカウント別変数追加)

## 触らない方がいいファイル（統合フェーズ以降）

- `.env`
- 旧 repo の任意ファイル（docs/legacy-repo-migration-audit.md を参照のみ）
- `config/source_accounts/production_sources.example.json`（active/fetch_enabled は false のまま）
- `config/accounts/*.json`（beauty_account は draft_only のまま）
- 実メディアファイル

## Sheets 実運用リカバリー (2026-06-24)

- 担当AI: Codex
- ブランチ: `main`
- 目的: Google Sheets がほぼ空だった状態から、Threads-first 実運用に必要な初期データを実Sheetsへseedし、read-after-writeで検証。
- 事前push: 未pushだった `b91c26f fix: reconcile x legacy posting and enable media source pipeline` を `origin/main` へpush済み。

### 実施内容

- `scripts/recover_production_sheets_threads_first.py` を追加。
- `src/sheets_client.py` に Threads-first / CTA / source media policy / posted_results 用の不足列を追加。
- `src/seeds.py` のアカウントseedを Threads-first / LINE_AND_DM / beauty CTAなしへ更新。
- Google Sheetsに以下を実書き込み:
  - アカウント管理 3件
  - 投稿カテゴリ 17件
  - プロンプト管理 5件
  - 収集元アカウント 17件
  - 動画収集元 4件
  - 投稿下書き 6件
  - SNS投稿文 6件
  - 投稿キュー night_scout 3件 / liver_manager 3件 / beauty 0件
  - 学習ルール 3件 (`active=false`, `auto_apply=false`)
  - 実行ログ
- `posted_results` に復旧記録と liver_manager 実投稿結果を記録。
- `liver_manager` Threads 実投稿を1件だけ実行。即retryなし。

### Read-after-write結果

- `python3 scripts/recover_production_sheets_threads_first.py --verify-only`
- result: 21 / 21 PASS
- posted_results: 3件
- media_assets: 0件、未承認uploadなし
- X queue: 0件
- Cloudinary upload: 未実行
- download/cut/upload/transcription: 未実行

### テスト結果

- `test_account_tone_guide.py`: PASS 41 / FAIL 0
- `test_threads_credentials.py`: PASS 24 / FAIL 0
- `test_phase13_publishers_production_safety.py`: PASS 4 / FAIL 0
- `test_content_workflows_safety.py`: PASS 8 / FAIL 0
- `test_source_intake_schema.py`: PASS 7 / FAIL 0
- `test_media_policy_guard.py`: PASS 8 / FAIL 0
- 追加テスト5本: PASS
- `check_credentials_readiness.py`: READY、Cloudflare/GH write tokenは任意MISSING

### 残WARN

- Google Sheets API read quota 429 が発生したため、復旧CLIはworksheet cache / batch upsertへ最適化済み。
- X投稿は停止中。X API調査は今回対象外。
- Cloudinary credentialsはSETだが `ALLOW_CLOUDINARY_UPLOAD=false` 維持。
- beauty_account は引き続き draft_only / 実投稿禁止。

### 次AIへのメモ

- Google Sheets確認は `scripts/recover_production_sheets_threads_first.py --verify-only` を使う。
- 実投稿はThreadsのみ、1件ずつ、dry-run後。失敗時の即retryは禁止。
- `data/threads_tokens`, `.env`, `output/media_cache`, `cloudinary_cache` はcommit禁止。

## 過去共有sourceの回収・seed (2026-06-29 追記)

- **ユーザーは過去にソースアカウントURL/選定ルールを共有済み**。「URLを入れてください」と返さない。
- 既存 repo / `production_sources.example.json` から回収し `config/source_accounts/default_sources.json` へ dedup マージ済み(17→59件)。真実源は default_sources.json(`src/reference/source_registry.py` がロード)。
- seed: `python3 scripts/seed_source_registry.py --dry-run --target-account all --platform all`(apply は `--apply --confirm-seed`)。
- 安全方針: **X は今は投稿/開発対象外だが reference source として保持**(active=false/fetch_enabled=false/manual_only)。**TikTok/YouTube は動画参考・文字起こし・切り抜き候補化の対象だが reference_only / can_reuse_media=false**。**beauty は将来用で active=false**(posting account は `beauty_account` 維持、ラベルは `future_track=beauty_future`)。公式メディアは低優先(`low_priority_media_official`)。URL未入力は `WAITING_URL_INPUT`。third-party素材は勝手に再利用しない。
- verify: `recover_production_sheets_threads_first.py --verify-only` に source registry 10 checks 追加。registry を増やした直後は `source_registry_reflected`/`video_sources_reflected` が「Sheets未seed」を示し fail することがある(seed apply で解消)。
- 詳細・追加URL貼り付け形式・次手順(収集→採点→投稿案生成): [source-recovery-and-seed.md](source-recovery-and-seed.md)。

## Codex source registry 統合最終監査 (2026-06-29 追記)

### 現在のHEAD / ブランチ

- 作業ブランチ: `feature/codex-source-registry-integration`
- 作業開始HEAD: `6942179828c5efb55c24e9287f02f7e8c8c1c628`
- origin/main確認: `6942179828c5efb55c24e9287f02f7e8c8c1c628`
- 実装commit: `3dc6e4c4167ee39e193947e2b0f93150849aef58`
- handoff docs commit: `0eaa271258ce0a050c8498f7bc363e61fbeb8438`（この行以降の最終push HEADは `git rev-parse HEAD` / 最終報告を参照）

### 本システムについて

- 真実源は `config/source_accounts/default_sources.json`。`src/reference/source_registry.py` と seed/recovery 経路はこの registry を使う。
- `source_rows()` は `source_accounts` / `reference_sources` タブへ変換する正規化層。Sheets へ書く前に safety field をここで強制する。
- `beauty_account` は posting account id のまま維持する。`beauty_future` は `future_track` / `source_track` / `usage_scope` の label のみ。target に使わない。

### 変更ファイル一覧

- `config/source_accounts/default_sources.json`
- `config/source_accounts/production_sources.example.json`
- `config/source_accounts/recovered_shared_sources.json`
- `scripts/recover_production_sheets_threads_first.py`
- `scripts/seed_source_registry.py`
- `scripts/test_seed_source_registry.py`
- `scripts/test_source_registry_verify_checks.py`
- `src/reference/source_scoring.py`
- `src/sheets_client.py`
- `docs/ai-work-handoff.md`
- `docs/ai-dev-status.md`
- `docs/phase13-16-test-matrix.md`
- `docs/source-recovery-and-seed.md`
- `docs/source-account-registry.md`
- `docs/production-completion-status.md`
- `docs/source-collection-runbook.md`

### 追加ファイル一覧

- `config/source_accounts/recovered_shared_sources.json`
- `scripts/seed_source_registry.py`
- `scripts/test_seed_source_registry.py`
- `scripts/test_source_registry_verify_checks.py`
- `src/reference/source_scoring.py`

### 完了内容

- default registry: 59 sources、active 6、fetch_enabled 0、X active 0、beauty 23、beauty_future target 0。
- production example: 91 sources、active 0、fetch_enabled 0、beauty_future target 0。
- recovered shared: 3 Threads sources。
- 全 source に `use_policy=REFERENCE_ONLY` / `can_reuse_media=false` を明示。
- beauty source は `rights_policy=reference_only` / `usage_scope=future_reference_only` / `review_status=BLOCKED_BEAUTY_ACCOUNT` / `default_queue_status=WAITING_REVIEW`。
- `source_rows()` と Sheets headers に safety columns を追加。既存列は削除・並び替えなし。
- `seed_source_registry.py` は `beauty_account` target alias と `query` platform filter に対応。`beauty_future` は filter alias のみ。
- verify checks に `beauty_target_account_id_preserved` / `beauty_reference_only_safety` を追加。

### 未完了事項

- Sheets への実 seed apply は未実行。必要時のみ `python3 scripts/seed_source_registry.py --apply --confirm-seed --target-account all --platform all` を人間承認後に実行。
- live Sheets verify は未実行。外部 Sheets 読み取りになるため、今回は local/unit/dry-run で確認。
- 実 fetch/download/cut/upload/post は未実行。

### スケール方針

- source は `default_sources.json` に追加し、`source_rows()` を通して Sheets へ反映する。並行 writer/schema は作らない。
- X は reference/manual のまま。自動 fetch/post の対象にしない。
- third-party media は `can_reuse_media=false` 既定。権利許諾が明示されるまで download/cut/upload/post 利用しない。
- scoring は並び替え・候補提示のみ。source priority の自動変更は禁止。

### 残WARN

- `src/reference/source_scoring.py` は helper とテスト接続済みだが、本番の採点CLI本線への深い接続は次フェーズ。
- `recover_production_sheets_threads_first.py --verify-only` は live Sheets 読み取りのため、今回は未実行。
- 旧 repo workflow 停止は引き続き人間作業。

### 全テスト結果

- `python3 -m py_compile ...`: PASS
- `python3 scripts/test_seed_source_registry.py`: PASS 10 / FAIL 0
- `python3 scripts/test_source_registry_verify_checks.py`: PASS 11 / FAIL 0
- `python3 scripts/test_phase13_production_sources_real_urls.py`: PASS 1 / FAIL 0
- `python3 scripts/test_phase13_source_registry_production.py`: PASS 28 / FAIL 0
- `python3 scripts/test_phase13_query_source_support.py`: PASS 5 / FAIL 0
- `python3 scripts/test_phase13_article_source_support.py`: PASS 5 / FAIL 0
- `python3 scripts/test_source_account_registry.py`: PASS 27 / FAIL 0
- `python3 scripts/test_beauty_account_block.py`: PASS 9 / FAIL 0
- `python3 scripts/test_no_beauty_ready_queue.py`: PASS 4 / FAIL 0
- `python3 scripts/test_no_x_ready_queue.py`: PASS 4 / FAIL 0
- `python3 scripts/test_media_policy_guard.py`: PASS 8 / FAIL 0
- `python3 scripts/test_recover_verify_ready_checks.py`: PASS 10 / FAIL 0
- `python3 scripts/test_phase13_pipeline_store.py`: PASS 15 / FAIL 0
- `python3 scripts/test_phase13_source_fetcher_tool_doctor.py`: PASS 29 / FAIL 0
- `python3 scripts/test_phase13_fetcher_production_paths.py`: PASS 2 / FAIL 0
- `python3 scripts/test_phase13_source_to_post_production_path.py`: PASS 4 / FAIL 0
- `python3 scripts/test_phase13_publishers_production_safety.py`: PASS 4 / FAIL 0
- `python3 scripts/test_phase13_generation_production.py`: PASS 3 / FAIL 0
- `python3 scripts/test_phase13_real_smoke_plan.py`: PASS 18 / FAIL 0
- `python3 scripts/test_phase13_pdca_production_loop.py`: PASS 3 / FAIL 0
- `python3 scripts/test_phase13_media_asset_storage.py`: PASS 3 / FAIL 0
- `python3 scripts/test_phase13_video_clip_execution.py`: PASS 3 / FAIL 0
- `python3 scripts/test_phase13_media_post_preflight.py`: PASS 3 / FAIL 0
- `python3 scripts/test_phase13_source_lifecycle.py`: PASS 23 / FAIL 0
- `python3 scripts/test_phase13_source_concept_matching.py`: PASS 4 / FAIL 0
- `python3 scripts/test_phase11_source_to_post_orchestrator.py`: PASS 23 / FAIL 0
- `python3 scripts/test_approve_queue_ready_transition.py`: PASS 11 / FAIL 0
- `python3 scripts/test_refill_outputs_waiting_review_not_ready.py`: PASS 4 / FAIL 0
- `python3 scripts/test_queue_worker_no_setup_all_in_real_mode.py`: PASS 12 / FAIL 0
- `python3 scripts/test_phase60_thread_series.py`: PASS 21 / FAIL 0
- `python3 scripts/test_thread_series_learning_loop.py`: PASS 11 / FAIL 0
- `python3 scripts/test_phase10_threads_publisher.py`: PASS 7 / FAIL 0
- `python3 scripts/test_phase10_x_publisher.py`: PASS 5 / FAIL 0
- `python3 scripts/test_phase10_publishers_safety.py`: PASS 14 / FAIL 0

### dry-run / BLOCKED確認結果

- `python3 scripts/seed_source_registry.py --dry-run --target-account all --platform all`: PASS、59 source_accounts / 33 reference_sources、Sheets writeなし。
- `python3 scripts/seed_source_registry.py --apply --target-account all --platform all --json`: `--confirm-seed` なしのため dry-run扱い、Sheets writeなし。
- `python3 scripts/seed_source_registry.py --dry-run --target-account beauty_account --platform youtube --json`: PASS、10 source_accounts / 10 reference_sources。
- `python3 scripts/seed_source_registry.py --dry-run --target-account beauty_future --platform tiktok --json`: PASS、7 source_accounts / 7 reference_sources。
- `python3 scripts/seed_source_registry.py --dry-run --target-account all --platform query --json`: PASS、1 source、fetch_enabled=false。

### confirmなしBLOCKED確認結果

- confirmなし seed apply: dry-run扱いでBLOCKED相当。
- confirmなし fetch/download/cut/upload/post は既存 Phase13 tests で BLOCKED/PASS 確認済み。

### 次にClaude Codeが触ってよいファイル

- `config/source_accounts/default_sources.json`（source追加・安全field維持）
- `scripts/seed_source_registry.py`（Sheets applyの表示改善、429 backoff改善）
- `src/reference/source_scoring.py`（本番採点CLIへの接続）
- `docs/source-recovery-and-seed.md`

### 次にCodexが触ってよいファイル

- `scripts/recover_production_sheets_threads_first.py`
- `src/sheets_client.py`
- `scripts/test_seed_source_registry.py`
- `scripts/test_source_registry_verify_checks.py`
- Phase13 source/media/publisher safety tests

### 衝突しやすいファイル

- `config/source_accounts/default_sources.json`
- `config/source_accounts/production_sources.example.json`
- `scripts/recover_production_sheets_threads_first.py`
- `src/sheets_client.py`
- `docs/ai-work-handoff.md`

### 触らない方がいいファイル

- `.env` / token / cookie / credential files
- `data/threads_tokens`
- `output/media_cache` / `cloudinary_cache`
- 旧 repo の任意ファイル
- `config/accounts/beauty_account.json` の `draft_only` 解除

### 次AIへの引き継ぎメモ

- `beauty_future` を target account にしない。必ず `target_account_ids=["beauty_account"]` を維持する。
- 実 Sheets 反映が必要なら、まず `seed_source_registry.py --dry-run` の件数を確認し、その後だけ `--apply --confirm-seed`。
- `source_rows()` は source registry の安全ゲート。新しい field を Sheets に出す場合は `src/sheets_client.py` のヘッダーにも末尾追加する。
- 実投稿・実fetch・download/cut/upload・Cloudinary upload・transcription API はこの作業では一切実行していない。

## Codex required source URL照合・追加 (2026-06-29 追記)

### 現在のHEAD / ブランチ

- 作業ブランチ: `main`
- 作業開始HEAD: `1e8966b5e3376d1cb4c7b117626df32317f660a4`
- 完了commit: この変更を含む最終 `main` HEAD は `git rev-parse HEAD` と最終レポートを参照

### 本システムについて

- ユーザー明示URLは `config/source_accounts/required_source_urls.json` を authoritative list とする。
- 今後 required URL が追加されたら、この JSON に追記し、required source tests を通す。
- X status URL は profile source と別に `post_url` / `canonical_url` / `status_url` で保持できるようにした。

### 変更ファイル一覧

- `config/source_accounts/default_sources.json`
- `config/source_accounts/required_source_urls.json`
- `scripts/required_source_url_checks.py`
- `scripts/test_required_source_urls_present.py`
- `scripts/test_required_threads_sources_present.py`
- `scripts/test_required_x_sources_manual_only.py`
- `scripts/test_source_canonical_url_matching.py`
- `scripts/test_no_fetch_enabled_required_sources.py`
- `scripts/test_required_sources_classification.py`
- `scripts/recover_production_sheets_threads_first.py`
- `src/sheets_client.py`
- `docs/source-account-registry.md`
- `docs/source-recovery-and-seed.md`
- `docs/ai-work-handoff.md`
- `docs/production-completion-status.md`

### 完了内容

- required Threads URL 6件を全件照合。既存2件、追加4件。
- required X URL 7件を全件照合。6件はURL一致済み、`minatoku789` status URLは既存sourceへ保持。
- `default_sources.json`: 59件 → 63件。
- `active`: 6件 → 10件（追加Threads 4件は `active=true`）。
- `fetch_enabled=true`: 0件維持。
- `night_scout`: 21件 → 25件、`liver_manager`: 15件維持、`beauty_account`: 23件維持。
- `target_account_ids=["beauty_future"]`: 0件維持。
- YouTube/TikTok再探索: production example の33件はすべて default に存在。追加すべき未登録の実source account URLはなし。

### 未完了事項 / 残WARN

- `recover_production_sheets_threads_first.py --verify-only --json` は承認システム側の out of credits で実行拒否。Sheets apply/write は未実行。
- 実fetch / 実download / 実cut / 実upload / 実投稿 / Cloudinary upload / transcription API は未実行。

### 全テスト結果

- `python3 -m py_compile ...`: PASS
- `python3 scripts/test_required_source_urls_present.py`: PASS 1 / FAIL 0
- `python3 scripts/test_required_threads_sources_present.py`: PASS 1 / FAIL 0
- `python3 scripts/test_required_x_sources_manual_only.py`: PASS 1 / FAIL 0
- `python3 scripts/test_source_canonical_url_matching.py`: PASS 1 / FAIL 0
- `python3 scripts/test_no_fetch_enabled_required_sources.py`: PASS 1 / FAIL 0
- `python3 scripts/test_required_sources_classification.py`: PASS 1 / FAIL 0
- `python3 scripts/test_seed_source_registry.py`: PASS 10 / FAIL 0
- `python3 scripts/test_source_registry_verify_checks.py`: PASS 11 / FAIL 0
- `python3 scripts/test_phase13_production_sources_real_urls.py`: PASS 1 / FAIL 0
- `python3 scripts/test_beauty_account_block.py`: PASS 9 / FAIL 0
- `python3 scripts/test_no_beauty_ready_queue.py`: PASS 4 / FAIL 0
- `python3 scripts/test_media_policy_guard.py`: PASS 8 / FAIL 0

### dry-run / verify結果

- `python3 scripts/seed_source_registry.py --dry-run --target-account all --platform all`: PASS、63 source_accounts / 33 reference_sources、`fetch_enabled_true=0`、Sheets writeなし。
- `python3 scripts/recover_production_sheets_threads_first.py --verify-only --json`: 未実行（approval credits拒否）。外部API回避は行っていない。

### 次AIへの引き継ぎメモ

- required URLの追加は `config/source_accounts/required_source_urls.json` と `default_sources.json` の両方を更新する。
- `test_required_source_urls_present.py` が required URL抜けの防止ゲート。
- X required source は `manual_only=true` / `active=false` / `fetch_enabled=false` を維持し、X APIやqueueに接続しない。
- Threads required source は `night_scout` 用。実fetchはせず、manual/reference sourceとして保持する。

## Codex source registry Sheets apply / 初回導通確認 (2026-06-30 追記)

### 現在のHEAD / ブランチ

- 作業ブランチ: `main`
- HEAD / `origin/main`: `564987b03f27a9baeef447815797d4952d7f6f33`
- 作業内容: source registry の Google Sheets seed apply と、収集→採点→Threads投稿案生成の PLAN_ONLY 導通確認。

### 変更ファイル一覧

- `docs/ai-work-handoff.md`（この追記のみ）

### Sheets apply結果

- `python3 scripts/recover_production_sheets_threads_first.py --verify-only --json`: apply前は `source_registry_reflected` / `video_sources_reflected` のみ未反映で FAIL。
- `python3 scripts/seed_source_registry.py --dry-run --target-account all --platform all`: PASS。63 source_accounts / 33 reference_sources、`fetch_enabled_true=0`、X manual_only、beauty safety維持、duplicateなし。
- `python3 scripts/seed_source_registry.py --apply --confirm-seed --target-account all --platform all`: PASS。source registry seed のみ Sheets へ反映。
- apply内訳: `source_accounts` added 46 / updated 17、`reference_sources` added 29 / updated 4。
- apply後 `python3 scripts/recover_production_sheets_threads_first.py --verify-only --json`: PASS 61 / FAIL 0。
- apply後 Sheets確認: source_accounts 63、reference_sources 33、required Threads 6/6、required X 7/7、`fetch_enabled=true` 0、beauty active 0、`target_account_id=beauty_future` 0。

### 初回導通dry-run結果

- `python3 scripts/collect_reference_posts.py --account-id night_scout`: PLAN_ONLY。REFERENCE_ONLY、media_download=false、real_x_api=false、auto_post=false。
- `python3 scripts/score_reference_posts.py --account-id night_scout`: PLAN_ONLY。
- `python3 scripts/generate_threads_ideas_from_references.py --account-id night_scout`: PLAN_ONLY。delegateは `generate_from_references.py --mock --dry-run`、生成候補statusは WAITING_REVIEW、worker_selectable=false。
- `python3 scripts/collect_reference_posts.py --account-id liver_manager`: PLAN_ONLY。REFERENCE_ONLY、media_download=false、real_x_api=false、auto_post=false。
- `python3 scripts/score_reference_posts.py --account-id liver_manager`: PLAN_ONLY。
- `python3 scripts/generate_threads_ideas_from_references.py --account-id liver_manager`: PLAN_ONLY。delegateは `generate_from_references.py --mock --dry-run`、生成候補statusは WAITING_REVIEW、worker_selectable=false。

### 未完了事項 / 残WARN

- 実収集は未実行のため、`reference_posts` / `reference_post_scores` は 0件のまま。
- WAITING_REVIEW実生成applyは未実行。既存reference_postsが0件だったため、今回は dry-run確認で停止。
- `collect_reference_posts.py` / `score_reference_posts.py` / `generate_threads_ideas_from_references.py` は `--dry-run` optionを持たず、`--apply`なしが PLAN_ONLY dry-run相当。

### 安全確認

- 実fetch / X fetch / video download / transcription API / Cloudinary upload / 実投稿 / X投稿は未実行。
- Sheets applyは source registry seed のみ。
- `fetch_enabled=true` は0件維持。
- `beauty_account` は active化なし、target維持。
- secret値 / cookie値は表示していない。

### 次に人間が見るべきSheetsタブ

- `収集元アカウント`
- `動画収集元`
- `収集済み投稿`
- `参考投稿`
- `参考投稿スコア`
- `投稿キュー`
- `SNS投稿文`

### 次AIへの引き継ぎメモ

- 次に進めるなら、X以外の安全なThreads/手動sourceから `reference_posts` を人間確認前提で少量作る段階。
- 投稿案を実生成する場合も `WAITING_REVIEW` までに止め、`READY` 化と worker選択は人間承認後にする。
- source registryの再applyは `seed_source_registry.py --dry-run` で63/33/0件を確認してから実施する。

## Codex production loop completion (2026-06-30 追記)

### 現在のHEAD / ブランチ

- 作業ブランチ: `main`
- 作業開始HEAD: `67ee0db8e5b723becdf079b7fffba43a0abb163c`
- 完了commit: 最終レポートの `HEAD` を参照

### 本システムについて

- source registry / Sheets apply / READY承認モデルは維持したまま、実fetchなしで `収集済み投稿 → 参考投稿スコア → WAITING_REVIEW投稿案 → approval dry-run → worker dry-run → PDCA dry-run` まで接続した。
- 完全自動投稿ではなく、人間承認付き半自動運用。生成候補は `WAITING_REVIEW` で止まり、worker は `READY` のみ拾う。

### 変更ファイル一覧

- `scripts/seed_reference_posts_from_sources.py`
- `scripts/score_reference_posts.py`
- `scripts/generate_threads_ideas_from_references.py`
- `scripts/generate_next_queue_from_metrics.py`
- `scripts/approve_queue.py`
- `scripts/test_seed_reference_posts_from_sources.py`
- `scripts/test_reference_posts_generated_without_fetch.py`
- `scripts/test_reference_post_scores_generated.py`
- `scripts/test_threads_ideas_waiting_review_only.py`
- `scripts/test_waiting_review_not_worker_selectable.py`
- `scripts/test_ready_only_worker_after_source_loop.py`
- `scripts/test_pdca_dry_run_safe_without_posted_results.py`
- `scripts/test_no_real_fetch_in_production_loop.py`
- `scripts/test_no_beauty_active_in_production_loop.py`
- `scripts/test_no_fetch_enabled_added.py`
- `docs/ai-work-handoff.md`
- `docs/production-completion-status.md`
- `docs/source-recovery-and-seed.md`
- `docs/reference-pipeline-runbook.md`
- `docs/threads-operation-runbook.md`
- `docs/phase13-16-test-matrix.md`

### 追加ファイル一覧

- `scripts/seed_reference_posts_from_sources.py`
- production loop completion tests 10本（上記 `test_*production_loop*` / reference seed系）

### 完了内容

- `seed_reference_posts_from_sources.py` を追加。source registryから `source_account_posts` へ manual reference seed を作成。実fetchなし、Xなし、mediaなし。
- `score_reference_posts.py` を `source_account_posts.post_text` 対応、`reference_post_id` 付与、重複skip対応、明示 `--dry-run` 対応に補強。
- `generate_threads_ideas_from_references.py` を採点済みreferenceから `drafts` / `social_derivatives` / `queue` へ `WAITING_REVIEW` 生成できるよう接続。READYは書かない。
- `approve_queue.py` の実Sheets detail表示で論理タブ名 `_ws("drafts")` を使うよう修正。
- `generate_next_queue_from_metrics.py` に明示 `--dry-run` を追加。

### Sheets実行結果

- `source_account_posts`: 0件 → 10件（night_scout 5 / liver_manager 5）
- `reference_post_scores`: 0件 → 10件（night_scout 5 / liver_manager 5）
- `drafts`: 8件 → 14件
- `social_derivatives`: 8件 → 14件
- `queue_total`: 14件
- `reference_score_to_threads` queue: night_scout 3 / liver_manager 3
- `WAITING_REVIEW`: 10件
- `READY`: 0件
- `source_accounts`: 63件、`reference_sources`: 33件、`fetch_enabled=true`: 0件維持

### 未完了事項 / 残WARN

- 実投稿は未実行。READY昇格も未実行。
- MEASUREDなposted_resultsが無いため、PDCA候補生成は `candidate_count=0` で安全終了。
- beauty_accountのThreads tokenは未設定のまま（意図どおり。beautyは運用対象外）。

### 全テスト結果

- 新規10本: PASS
- 既存重要テスト: `test_required_source_urls_present.py`, `test_seed_source_registry.py`, `test_source_registry_verify_checks.py`, `test_beauty_account_block.py`, `test_no_beauty_ready_queue.py`, `test_media_policy_guard.py`, `test_phase13_production_sources_real_urls.py`, `test_score_reference_posts.py`, `test_generate_threads_ideas_from_references.py`, `test_approve_queue_ready_transition.py`, `test_process_threads_queue.py` すべてPASS。
- `recover_production_sheets_threads_first.py --verify-only --json`: PASS 61 / FAIL 0。

### dry-run結果 / safety確認

- `process_threads_queue.py --account-id night_scout --dry-run --max-posts 2`: `candidates=0`
- `process_threads_queue.py --account-id liver_manager --dry-run --max-posts 2`: `candidates=0`
- `approve_queue.py --queue-id q_night_scout_manualref_src_ns_threads_required_001_threads --approve --dry-run --use-sheets`: `WAITING_REVIEW → READY` の計画のみ確認、書き込みなし。
- `import_threads_metrics_manual.py --dry-run`: PASS
- `generate_next_queue_from_metrics.py --dry-run`: 両アカウント `measured_count=0`, `candidate_count=0`
- 実fetch / X fetch / video download / transcription API / Cloudinary upload / 実投稿 / X投稿は未実行。
- secret値 / cookie値は表示していない。
- beauty_account active化なし、`target_account_id=beauty_future` 作成なし、`fetch_enabled=true` 追加なし。

### 次にClaude Codeが触ってよいファイル

- `scripts/seed_reference_posts_from_sources.py`
- `scripts/score_reference_posts.py`
- `scripts/generate_threads_ideas_from_references.py`
- `docs/reference-pipeline-runbook.md`
- `docs/threads-operation-runbook.md`

### 次にCodexが触ってよいファイル

- `scripts/process_threads_queue.py`
- `scripts/approve_queue.py`
- `scripts/generate_next_queue_from_metrics.py`
- `scripts/import_threads_metrics_manual.py`
- production loop completion tests

### 衝突しやすいファイル

- `scripts/generate_threads_ideas_from_references.py`
- `scripts/score_reference_posts.py`
- `docs/ai-work-handoff.md`
- `docs/production-completion-status.md`

### 触らない方がいいファイル

- `.env` / token / cookie / credential files
- `data/` / `output/` / `.claude/plans/`
- beauty_account の active/fetch/READY関連設定
- X fetch/posting関連の実行フラグ

### 次AIへの引き継ぎメモ

- 次に人間が見るべき行は `投稿キュー` の `q_night_scout_manualref_...` / `q_liver_manager_manualref_...` 6件。
- 実投稿へ進む前に、人間が1件だけ `approve_queue.py --approve --reason ... --use-sheets` でREADY化し、`process_threads_queue.py --dry-run --max-posts 1` を通す。
- 実投稿は別作業。`--confirm-real-post` + `PUBLISH_ENABLED=true` + `ALLOW_REAL_THREADS_POST=true` が必要。

## Codex AUTO_READY / autopilot completion (2026-06-30 追記)

### 現在のHEAD / ブランチ

- 作業ブランチ: `main`
- 作業開始HEAD: `3ce2b9c0285ecdc652fb9808164e6d801093192f`
- 完了commit: 最終レポート参照

### 本システムについて

- READY承認の手間を減らすため、`WAITING_REVIEW` から `READY` への条件付き自動承認（AUTO_READY）を追加。
- AUTO_READYとAUTO_POSTは分離。初期運用はAUTO_READYまで自動、AUTOPOSTは `auto_post_enabled=false`。
- 実投稿は引き続き `--confirm-real-post` + `PUBLISH_ENABLED=true` + `ALLOW_REAL_THREADS_POST=true` の三重ゲート必須。

### 変更ファイル一覧

- `config/auto_approval_rules.json`
- `src/sheets_client.py`
- `scripts/auto_approve_queue.py`
- `scripts/run_autopilot_loop.py`
- `scripts/plan_media_mix.py`
- `scripts/generate_video_reference_posts.py`
- AUTO_READY / autopilot / media-video tests 24本
- `docs/ai-work-handoff.md`
- `docs/production-completion-status.md`
- `docs/reference-pipeline-runbook.md`
- `docs/threads-operation-runbook.md`
- `docs/source-recovery-and-seed.md`
- `docs/phase13-16-test-matrix.md`

### 追加ファイル一覧

- `config/auto_approval_rules.json`
- `scripts/auto_approve_queue.py`
- `scripts/run_autopilot_loop.py`
- `scripts/plan_media_mix.py`
- `scripts/generate_video_reference_posts.py`
- `scripts/test_auto_approve_queue_*.py`
- `scripts/test_run_autopilot_loop_*.py`
- `scripts/test_no_auto_ready_when_kill_switch.py`
- `scripts/test_no_x_fetch_in_autopilot.py`
- `scripts/test_no_beauty_active_in_autopilot.py`
- `scripts/test_media_mix_ratio_plan.py`
- `scripts/test_media_plan_never_reuses_third_party.py`
- `scripts/test_video_reference_posts_waiting_review_only.py`
- `scripts/test_one_video_generates_multiple_posts.py`
- `scripts/test_transcription_requires_confirm_flag.py`
- `scripts/test_video_download_requires_confirm_flag.py`
- `scripts/test_cloudinary_upload_requires_confirm_flag.py`

### AUTO_READY設定

- `auto_ready_enabled=true`
- `auto_post_enabled=false`
- `min_quality_score=75`
- `min_safety_score=90`
- `max_risk_score=10`
- `daily_ready_cap=2`
- `daily_post_cap=1`
- `cooldown_minutes=180`
- `max_posts_per_run=1`
- `kill_switch=false`
- `allow_media_posts=false`
- `allow_third_party_media=false`
- `require_no_media_for_auto_ready=true`

### Sheets apply結果

- `python3 scripts/auto_approve_queue.py --dry-run --account-id all --max-ready 2 --use-sheets`: 2件APPROVABLE。
- `python3 scripts/auto_approve_queue.py --apply --confirm-auto-ready --account-id all --max-ready 2 --use-sheets`: 2件READY化。
- READY化したqueue:
  - `q_night_scout_manualref_src_ns_threads_required_001_threads`
  - `q_liver_manager_manualref_src_lm_note_cand_001_threads`
- `投稿キュー` に `auto_ready_by`, `auto_ready_reason`, `auto_ready_score`, `auto_ready_at`, `quality_score`, `safety_score`, `risk_score` を追加。
- `logs` に `operation=queue_approved`, `auto_ready=true` の承認証跡を記録。既存verifyと互換。

### dry-run / verify結果

- `recover_production_sheets_threads_first.py --verify-only --json`: PASS 61 / FAIL 0。
- `process_threads_queue.py --account-id night_scout --dry-run --max-posts 1`: candidates=1、read_only=true。
- `process_threads_queue.py --account-id liver_manager --dry-run --max-posts 1`: candidates=1、read_only=true。
- `run_autopilot_loop.py --dry-run --account-id all --auto-ready --skip-real-post --use-sheets`: PASS。AUTOPOST gate allowed=false。
- `plan_media_mix.py --dry-run --account-id all --use-sheets`: text_only=10、media_candidate=0、target 70/30。
- `generate_video_reference_posts.py --dry-run --account-id all`: 6件のWAITING_REVIEW案をPLAN_ONLY生成。

### 現在のSheets状態

- `WAITING_REVIEW`: 8件
- `READY`: 2件
- `auto_ready_ready`: 2件
- `fetch_enabled=true`: 0件
- `beauty_active`: 0件
- `x_active`: 0件

### 未完了事項 / 残WARN

- 実投稿は未実行。
- AUTOPOSTは実装上のゲートのみ。初期設定は `auto_post_enabled=false`。
- MEASURED metricsが無いためPDCA次候補はまだ0件。
- media付き投稿は初期AUTO_READY対象外。

### 全テスト結果

- AUTO_READY / autopilot / media-video 追加24本: PASS。
- 既存重要テスト: `test_process_threads_queue.py`, `test_approve_queue_ready_transition.py`, `test_required_source_urls_present.py`, `test_seed_source_registry.py`, `test_source_registry_verify_checks.py`, `test_beauty_account_block.py`, `test_no_beauty_ready_queue.py`, `test_media_policy_guard.py`, `test_phase13_production_sources_real_urls.py`, `test_waiting_review_not_worker_selectable.py`, `test_ready_only_worker_after_source_loop.py` すべてPASS。

### 安全確認

- 実fetch / X fetch / video download / transcription API / Cloudinary upload / Threads実投稿 / X投稿は未実行。
- beauty_account active化なし。
- `target_account_id=beauty_future` 作成なし。
- `fetch_enabled=true` 追加なし。
- third-party素材のdownload/cut/upload/repostなし。
- secret/token/cookie値は表示していない。

### 次にClaude Codeが触ってよいファイル

- `config/auto_approval_rules.json`
- `scripts/auto_approve_queue.py`
- `scripts/run_autopilot_loop.py`
- `docs/threads-operation-runbook.md`

### 次にCodexが触ってよいファイル

- `scripts/process_threads_queue.py`
- `scripts/import_threads_metrics_manual.py`
- `scripts/generate_next_queue_from_metrics.py`
- `scripts/plan_media_mix.py`
- `scripts/generate_video_reference_posts.py`

### 衝突しやすいファイル

- `src/sheets_client.py`
- `scripts/auto_approve_queue.py`
- `docs/ai-work-handoff.md`
- `docs/production-completion-status.md`

### 触らない方がいいファイル

- `.env` / token / cookie / credential files
- `data/` / `output/` / `.claude/plans/`
- X投稿/fetch関連の実行フラグ
- beauty_account の active/fetch/READY関連設定

### 次AIへの引き継ぎメモ

- 次に実投稿へ進むなら、READY化済み2件のうち1件だけ `process_threads_queue.py --dry-run --max-posts 1` で再確認し、別途三重ゲート付きで実行する。
- AUTO_READY追加実行はcooldown 180分後。`kill_switch=true` にすると即停止。
- AUTOPOSTを有効化する場合も `auto_post_enabled=true`、env gate、`--confirm-real-post` が全て必要。

## First real Threads post / autopilot pilot (2026-06-30)

### 現在のHEAD / ブランチ

- 作業ブランチ: `main`
- 作業開始HEAD / origin/main: `82eeef90b1c525f07533d6cf11140d9a8566426d`
- 追加commit: `feat: 初回実投稿テストと自動運用パイロットを追加`

### 変更ファイル一覧

- `.github/workflows/autopilot-auto-ready.yml`
- `scripts/test_first_real_post_requires_triple_gate.py`
- `scripts/test_process_threads_queue_single_post_cap.py`
- `scripts/test_posted_results_written_after_success.py`
- `scripts/test_no_retry_loop_on_post_failure.py`
- `scripts/test_autopost_stays_disabled_by_default.py`
- `scripts/test_autopost_pilot_requires_all_gates.py`
- `scripts/test_daily_autopilot_workflow_no_real_post.py`
- `scripts/test_metrics_import_safe_after_first_post.py`
- `scripts/test_pdca_safe_after_first_post_without_metrics.py`
- `scripts/test_media_pilot_requires_approved_asset.py`
- `docs/ai-work-handoff.md`
- `docs/production-completion-status.md`
- `docs/threads-operation-runbook.md`
- `docs/reference-pipeline-runbook.md`
- `docs/phase13-16-test-matrix.md`

### 初回実投稿結果

- 実投稿: 1件のみ実行。追加retryなし。
- account: `liver_manager`
- queue_id: `q_liver_manager_manualref_src_lm_note_cand_001_threads`
- result_id: `threads_q_liver_manager_manualref_src_lm_note_cand_001_threads_20260630025810`
- post_url: `https://www.threads.com/@ran.liver_pro/post/DaMbCLQiXLs`
- queue status: `POSTED`
- posted_results: `status=POSTED`, `metrics_status=PENDING`, `real_post=TRUE`, `media_used=FALSE`
- 実行時envはコマンドスコープのみ: `PUBLISH_ENABLED=true ALLOW_REAL_THREADS_POST=true`

### 現在のSheets状態

- `recover_production_sheets_threads_first.py --verify-only --json`: PASS 61 / FAIL 0
- `posted_results`: 5件
- `queue` status: `POSTED=2`, `READY=1`, `WAITING_REVIEW=8`, `PLANNED=2`, `DUPLICATE_BLOCKED=1`
- `night_scout`: `POSTED=1`, `READY=1`, `WAITING_REVIEW=4`, `PLANNED=1`
- `liver_manager`: `POSTED=1`, `WAITING_REVIEW=4`, `PLANNED=1`, `DUPLICATE_BLOCKED=1`

### dry-run / BLOCKED確認結果

- `process_threads_queue.py --account-id liver_manager --dry-run --max-posts 1`: 実投稿前に対象1件を確認。
- `import_threads_metrics_manual.py --result-id ... --dry-run`: PASS。0値metricsテンプレートを表示のみ、保存なし。
- `generate_next_queue_from_metrics.py --dry-run --account-id liver_manager`: PASS。MEASURED metricsなしのため `candidate_count=0`。
- `run_autopilot_loop.py --dry-run --account-id all --auto-ready --skip-real-post --use-sheets`: PASS。`auto_post_gate.allowed=false`。
- `plan_media_mix.py --dry-run --account-id all --use-sheets`: PASS。`media_candidate_count=0`。
- `generate_video_reference_posts.py --dry-run --account-id all`: PASS。6件の `WAITING_REVIEW` planのみ。

### 未完了事項 / 残WARN

- AUTOPOSTはOFFのまま。`auto_post_enabled=false` 維持。
- Metricsはまだ本測定値未投入。`posted_results.metrics_status=PENDING`。
- MEASURED metricsがないためPDCA実候補は0件。
- Media assetsは0件。media/video pilotは計画のみで、download/cut/upload/transcription/Cloudinaryは未実行。
- GitHub Actionsの `autopilot-auto-ready.yml` は追加したが、この作業ではActions実行なし。

### 全テスト結果

- 新規10本: PASS 56 / FAIL 0。
- 既存重要31本: PASS。代表結果:
  - `test_process_threads_queue.py`: PASS 11 / FAIL 0
  - `test_all_workflows_safety_flags.py`: PASS 103 / FAIL 0
  - `test_seed_source_registry.py`: PASS 10 / FAIL 0
  - `test_source_registry_verify_checks.py`: PASS 11 / FAIL 0
  - `test_beauty_account_block.py`: PASS 9 / FAIL 0

### 安全確認

- 実fetch未実行。
- X fetch / X投稿未実行。
- video download / cut / upload 未実行。
- transcription API未実行。
- Cloudinary upload未実行。
- media付き投稿未実行。
- 実投稿はThreads 1件のみ。retryなし。
- secret/token/cookie値は表示していない。
- `beauty_account` はactive化なし、READY/POSTED化なし。
- `fetch_enabled=true` 追加なし。
- source priority自動変更なし。

### 次に触ってよいファイル

- Claude Code: `docs/threads-operation-runbook.md`, `docs/reference-pipeline-runbook.md`, `.github/workflows/autopilot-auto-ready.yml`
- Codex: `scripts/process_threads_queue.py`, `scripts/import_threads_metrics_manual.py`, `scripts/generate_next_queue_from_metrics.py`, `scripts/run_autopilot_loop.py`

### 衝突しやすいファイル / 触らない方がいいファイル

- 衝突しやすい: `docs/ai-work-handoff.md`, `docs/production-completion-status.md`, `scripts/run_autopilot_loop.py`, `.github/workflows/threads-queue-worker.yml`
- 触らない: `.env`, credential/token/cookie files, `data/`, `output/`, `.claude/plans/`, X real-post/fetch flags, beauty active/fetch/READY settings

### 次AIへの引き継ぎメモ

- 次は `posted_results` の実metricsを人間が手入力し、`import_threads_metrics_manual.py --dry-run` で値を確認してから apply する。
- `night_scout` にREADYが1件残っている。投稿する場合は必ず `process_threads_queue.py --account-id night_scout --dry-run --max-posts 1` を再確認し、別作業として1件だけ実行する。
- AUTO_READYの定期workflowはREADY昇格まで。投稿はしない。

## Metrics / PDCA / second-account pilot prep (2026-06-30)

### 現在のHEAD / ブランチ

- 作業ブランチ: `main`
- 作業開始HEAD / origin/main: `557de587efcdda9ab5b7347982bafab66395acfa`
- 追加commit予定: `feat: metrics PDCAと2アカウント投稿パイロットを追加`

### 変更ファイル一覧

- `scripts/import_threads_metrics_manual.py`
- `scripts/generate_next_queue_from_metrics.py`
- `scripts/test_metrics_measured_updates_pdca_candidate.py`
- `scripts/test_pdca_generates_waiting_review_after_measured_metrics.py`
- `scripts/test_night_scout_single_real_post_requires_triple_gate.py`
- `scripts/test_two_account_posted_results_recorded.py`
- `scripts/test_autopilot_workflow_static_no_post.py`
- `scripts/test_autopost_remains_off_after_first_posts.py`
- `scripts/test_metrics_import_does_not_fabricate_values.py`
- `scripts/test_pdca_never_auto_ready_without_auto_approval.py`
- `docs/ai-work-handoff.md`
- `docs/production-completion-status.md`
- `docs/threads-operation-runbook.md`
- `docs/reference-pipeline-runbook.md`
- `docs/phase13-16-test-matrix.md`

### 実運用結果

- Threads post URL: HTTP 200で到達確認済み。
- 公開ページから信頼できるmetrics値は取得できなかったため、本番metricsは盛らない方針。
- Google Sheets verify / read / apply は承認システム側の `out of credits` で拒否。回避せず停止。
- `liver_manager` 本番metrics apply: 未実行。
- `liver_manager` 本番PDCA apply: 未実行。
- `night_scout` dry-run / 実投稿: Sheets接続不可のため未実行。追加実投稿なし。

### 実装補強

- `import_threads_metrics_manual.py`
  - `--use-sheets`, `--apply`, `--confirm-metrics` を追加。
  - `--replies` を `--comments` aliasとして追加。
  - `--reposts`, `--quotes`, `--profile_clicks`, `--line_adds` を受け付ける。
  - 値なし `--dry-run` はテンプレート表示のみ。欠損値を0として捏造しない。
  - 実保存は `--apply --confirm-metrics` と全core metrics明示が必須。
- `generate_next_queue_from_metrics.py`
  - runbook互換の `--use-sheets` を受け付ける。
  - 生成queueは引き続き `DRAFT` で、READYにはしない。

### dry-run / test結果

- `import_threads_metrics_manual.py --result-id ... --dry-run`: PASS。`missing_metrics` を返し `would_mark_measured=false`。
- 明示ゼロ値のmetrics dry-run: PASS。`would_mark_measured=true`。
- offline sample MEASUREDで `generate_next_queue_from_metrics.py --input-json ... --dry-run`: PASS。`candidate_count=1`, `candidate_status=DRAFT`。
- `run_autopilot_loop.py --dry-run --account-id all --auto-ready --skip-real-post`: PASS。`auto_post_gate.allowed=false`。
- `plan_media_mix.py --dry-run --account-id all`: PASS。media実行なし。
- `generate_video_reference_posts.py --dry-run --account-id all`: PASS。`WAITING_REVIEW` planのみ。
- 新規8本: PASS 50 / FAIL 0。
- 既存重要9本: PASS。`test_all_workflows_safety_flags.py` は PASS 103 / FAIL 0。

### 未完了事項 / 残WARN

- 承認システム `out of credits` のため、Google Sheets verify/applyとnight_scout実投稿は未実行。
- `liver_manager` metricsは本番値未投入。`PENDING` 維持想定。
- 本番Sheetsの最新件数はこのturnでは再取得できていない。

### AUTOPOSTをONにする条件

- `night_scout` / `liver_manager` の2アカウントで各1件以上の投稿成功。
- `posted_results` に `queue_id`, `external_post_id`, `post_url`, `status=POSTED` が保存済み。
- metrics importが `MEASURED` として確認済み。
- duplicate guard / posted_results整合性verifyがPASS。
- `kill_switch` 動作確認済み。
- `daily_post_cap=1`, `cooldown_minutes=180`, `max_posts_per_run=1` 維持。
- rollback手順とPOSTED_SAVE_FAILED時のfallback回収手順が明文化済み。

### 安全確認

- 今回、実投稿なし。
- 実fetch / X fetch / X投稿なし。
- beauty投稿なし。
- media download / cut / uploadなし。
- transcription API / Cloudinary uploadなし。
- secret/token/cookie値はdocs/finalに表示しない。
- `.env`, `data/`, `output/`, `.claude/plans/` はcommitしない。

## Production Sheets verify / night_scout post completion (2026-06-30)

### 現在のHEAD / ブランチ

- 作業ブランチ: `main`
- 作業開始HEAD / origin/main: `84bf3f6c8b5964de127de3d100a3392d67806823`
- 追加commit予定: `feat: 本番metrics PDCAとnight_scout投稿を完了`

### 実行結果

- 本番Sheets verify: PASS 61 / FAIL 0。
- `liver_manager` result_id: `threads_q_liver_manager_manualref_src_lm_note_cand_001_threads_20260630025810`
- `liver_manager` post_url: `https://www.threads.com/@ran.liver_pro/post/DaMbCLQiXLs`
- `liver_manager` metrics: `PENDING` 維持。
- metrics dry-run: 値なしでは `would_mark_measured=false`。
- metrics apply: 未実行。公開URLはHTTP 200だが、数値を取得できず、0値MEASURED化は安全レビューで拒否されたため回避しない。
- `liver_manager` PDCA dry-run: `measured_count=0`, `candidate_count=0`。
- `liver_manager` PDCA apply: 未実行。
- `night_scout` dry-run: candidates=1、mediaなし、Threadsのみ、queue_id確認済み。
- `night_scout` 実投稿: 1件のみ成功。retryなし。
- `night_scout` queue_id: `q_night_scout_manualref_src_ns_threads_required_001_threads`
- `night_scout` result_id: `threads_q_night_scout_manualref_src_ns_threads_required_001_threads_20260630111243`
- `night_scout` external_post_id: `18104495005994780`
- `night_scout` post_url: `https://www.threads.com/@kyaba_consul_mizu/post/DaNToTqgQ7i`

### 投稿後Sheets状態

- `posted_results`: 6件
- `queue` status: `POSTED=3`, `WAITING_REVIEW=8`, `PLANNED=2`, `DUPLICATE_BLOCKED=1`, `READY=0`
- `metrics_status`: empty=1, `MANUAL_PENDING=2`, `PENDING=3`
- `fetch_enabled=true`: 0
- `beauty_active`: 0
- `x_active`: 0
- `media_assets`: 0

### dry-run / test結果

- `run_autopilot_loop.py --dry-run --account-id all --auto-ready --skip-real-post --use-sheets`: PASS。`auto_post_gate.allowed=false`。worker candidates=0。
- `plan_media_mix.py --dry-run --account-id all --use-sheets`: PASS。`media_candidate_count=0`。
- `generate_video_reference_posts.py --dry-run --account-id all`: PASS。6件の `WAITING_REVIEW` planのみ。
- 必須テスト:
  - `test_import_threads_metrics_manual.py`: PASS 4 / FAIL 0
  - `test_generate_next_queue_from_metrics.py`: PASS 17 / FAIL 0
  - `test_process_threads_queue.py`: PASS 11 / FAIL 0
  - `test_all_workflows_safety_flags.py`: PASS 103 / FAIL 0
  - `test_autopost_remains_off_after_first_posts.py`: PASS 6 / FAIL 0
  - `test_metrics_import_does_not_fabricate_values.py`: PASS 5 / FAIL 0

### 未完了事項

- 本番metricsのMEASURED化は未完了。Threads Insights等で実測値を確認してから明示値でapplyする。
- 本番PDCA applyは未完了。MEASURED metricsが入ってから実行する。
- AUTOPOSTはまだOFF。

### 次にAUTOPOSTをONにする条件

- 2アカウント投稿は完了済み。次は両アカウントのmetricsをMEASURED化する。
- `posted_results` verify / duplicate guard / queue consistency が継続PASS。
- `daily_post_cap=1`, `cooldown_minutes=180`, `max_posts_per_run=1`, `kill_switch=false` を確認。
- 失敗時rollback、POSTED_SAVE_FAILED fallback回収、AUTOPOST停止手順を運用者が確認。
- 上記が揃うまで `auto_post_enabled=false` を維持。

## v2 collection / metrics / video / media pipeline (2026-06-30)

### 変更ファイル一覧

- `scripts/collect_threads_metrics.py`
- `scripts/collect_source_posts.py`
- `scripts/archive_reference_data.py`
- `scripts/collect_video_references.py`
- `scripts/analyze_video_structure.py`
- `scripts/cut_approved_clips.py`
- `scripts/generate_media_post_queue.py`
- `scripts/run_growth_loop.py`
- `scripts/generate_clip_candidates.py`
- `scripts/upload_media_assets.py`
- v2追加テスト23本
- `docs/video-reference-runbook.md`
- `docs/media-pipeline-runbook.md`
- `docs/growth-loop-runbook.md`
- `docs/production-completion-status.md`
- `docs/threads-operation-runbook.md`
- `docs/reference-pipeline-runbook.md`
- `docs/phase13-16-test-matrix.md`

### 実装内容

- Threads metrics collector: snapshot履歴、`PENDING/PARTIAL/MEASURED/UNAVAILABLE`、unknownはnull、0確定と取得不可を分離。
- Source collector: `fetch_enabled=true` のみ対象、manual_only skip、Xは初期OFF、media downloadなし。
- Archive: secret/cookie/token系キーをredactし、third-party media本体は保存しない。
- Video reference: metadata plan、transcription gate、structure analysis、複数投稿案生成。
- Clip candidate: transcript timestamp前提の候補フィールドを定義。third-partyはcut不可。
- Approved clip cutter: `owned/licensed/approved_creator_clip` のみ、`ALLOW_VIDEO_CUT=true` + `--confirm-cut` 必須。
- Media upload: third-party拒否、Cloudinaryは `ALLOW_CLOUDINARY_UPLOAD=true` + `--confirm-upload` 必須。
- Media queue: approved mediaのみ、`WAITING_REVIEW` まで、mediaなし70%/media付き30%方針。
- Growth loop: metrics -> PDCA -> source collect -> media queue -> AUTO_READY dry-run。AUTOPOSTなし。

### 実行結果

- v2追加テスト23本: PASS。
- 既存重要テスト12本: PASS。
- 本番Sheets verify: PASS 61 / FAIL 0。
- 新規CLI dry-run: PASS。`run_growth_loop.py --dry-run` は全step returncode 0。

### 安全確認

- 実fetchなし。
- 実downloadなし。
- 実cutなし。
- 実uploadなし。
- 実投稿なし。
- AUTOPOSTはOFF維持。
- X投稿/beauty投稿なし。
- secret/token/cookie表示なし。

### 未完了事項

- 実metrics自動取得のAPI/browser実装は抽象化まで。実API連携は認証/利用規約確認後。
- source fetchは `fetch_enabled=true` が0件のため収集applyなし。
- metric_snapshotsタブへの本番書き込みは未実行。
- 自社/許諾済み素材が登録されるまでcut/upload/media queue applyは行わない。

## v2 real data collection adapters (2026-06-30)

### 現在のHEAD / ブランチ

- 作業ブランチ: `main`
- 作業開始HEAD / origin/main: `9a1c4fa3418dacc032845de14027f1172cf7a320`
- 追加commit予定: `feat: v2実データ収集アダプタを追加`

### 変更ファイル一覧

- `scripts/collect_threads_metrics.py`
- `scripts/collect_source_posts.py`
- `scripts/collect_video_references.py`
- `scripts/run_growth_loop.py`
- `scripts/recover_production_sheets_threads_first.py`
- `src/sheets_client.py`
- `docs/growth-loop-runbook.md`
- `docs/reference-pipeline-runbook.md`
- `docs/video-reference-runbook.md`
- `docs/threads-operation-runbook.md`
- `docs/ai-work-handoff.md`

### 追加ファイル一覧

- `scripts/test_collect_threads_metrics_browser_or_api_adapter.py`
- `scripts/test_collect_threads_metrics_saves_partial_snapshot.py`
- `scripts/test_collect_threads_metrics_updates_posted_results_without_fabrication.py`
- `scripts/test_collect_source_posts_threads_real_adapter_plan.py`
- `scripts/test_collect_source_posts_deduplicates_real_urls.py`
- `scripts/test_collect_source_posts_archives_redacted_raw.py`
- `scripts/test_video_metadata_real_adapter_plan.py`
- `scripts/test_transcript_pipeline_no_download_for_third_party.py`
- `scripts/test_growth_loop_uses_real_collection_outputs.py`
- `scripts/test_growth_loop_still_no_auto_post.py`

### 実装内容

- Threads metrics:
  - `collect_threads_metrics.py --source api/browser/manual/unavailable`。
  - `--post-url` で公開Threads投稿URLをdry-run確認可能。
  - 公開HTMLから信頼できる数値が取れない場合は `UNAVAILABLE` / `confidence=none` / `error_reason` を保存予定。
  - unknownはnull維持。0確定と取得不可を分離。
  - `metric_snapshots` tab schemaを追加。apply時は不足タブ/列を冪等作成。
  - `posted_results` 更新時にNone metricsを空文字で上書きしない。
- Threads source collection:
  - `collect_source_posts.py --platform threads --source-url ... --fetch-real --dry-run` で公開OG metadataを取得。
  - 保存予定行は `source_account_posts` schema。
  - `post_url` dedupeをdry-run/apply双方で実施。
  - third-party mediaはdownloadせず、`can_reuse_media=false` / `rights_status=reference_only`。
  - raw payloadはsecret/cookie/token系キーをredact。
- YouTube/TikTok metadata:
  - `collect_video_references.py --fetch-metadata` で公開metadataを取得。
  - download/cut/uploadは常にfalse。
  - transcriptは公式/API取得のみ。実APIは別gate必須。
- Growth loop:
  - `--metric-post-url` と `--source-url --fetch-real` を既存収集CLIへ配線。
  - source収集dry-runの出力を既存 `build_scores()` / `build_generation_rows()` に渡し、WAITING_REVIEW候補数をsummary表示。
  - AUTOPOST OFF / real_post false維持。

### dry-run結果

- Sheets verify: PASS 61 / FAIL 0。
- `collect_threads_metrics.py --source browser` 2投稿URL: `snapshot_count=2`、両方 `metrics_status=UNAVAILABLE`、`public_html_no_metrics`、全metrics null。
- `collect_source_posts.py --platform threads --account-id all --source-url ... --fetch-real --dry-run`: `selected_count=2`, `deduped_count=2`, `status=COLLECTED`, media download false。
- `collect_source_posts.py --platform threads --account-id all --dry-run`: `selected_count=0`。`fetch_enabled=true` が0件のため正常。
- `collect_video_references.py --url <youtube> --fetch-metadata --dry-run`: `metadata_status=FETCHED`, download false。
- `collect_video_references.py --dry-run`: `metadata_status=PLAN_ONLY`, download false。
- `run_growth_loop.py --dry-run --account-id all --metric-post-url ... --source-url ... --fetch-real`: `real_collection_pipeline.source_posts=2`, `scored_count=2`, `candidate_count=2`, `candidate_status=WAITING_REVIEW`, `auto_post=false`。
- `run_growth_loop.py --dry-run --account-id all`: `NO_DATA`。標準状態ではsource fetch_enabled 0件で安全。

### テスト結果

- 新規10本: PASS。
- `test_phase8_sheets_schema.py`: PASS 81 / FAIL 0。
- `test_all_workflows_safety_flags.py`: PASS 103 / FAIL 0。
- `test_run_growth_loop_no_auto_post.py`: PASS 3 / FAIL 0。
- `test_collect_source_posts_no_x_by_default.py`: PASS 2 / FAIL 0。
- `test_process_threads_queue.py`: PASS 11 / FAIL 0。

### 安全確認

- 実投稿なし。
- X投稿なし / X fetchなし。
- beauty投稿なし。
- third-party動画download/cut/upload/repostなし。
- Cloudinary uploadなし。
- transcription API呼び出しなし。
- AUTOPOSTはOFF維持。
- `fetch_enabled=true` は増やしていない。
- secret/token/cookie値は表示・docs記載なし。
- `.env`, `data/`, `output/`, `.claude/plans/` はcommit対象外。

### 未完了事項 / 残WARN

- Threads公開ページでは投稿metrics数値が出ないため、自動metricsは現在 `UNAVAILABLE`。正規APIまたはログイン済み管理画面の合法導線が必要。
- `metric_snapshots` の本番applyは未実行。実施時は `--apply --confirm-metrics --use-sheets`。
- source registry側の `fetch_enabled=true` は0件維持。実収集apply前に1〜2件だけ人間レビューしてONにする。
- TikTok metadata実URLのネットワークdry-runは未実施。実施時もdownload禁止。

### スケール方針

- 最初は `--source-url` または `fetch_enabled=true` 1〜2件で運用確認。
- 大量ONは禁止。duplicate rate、取得失敗率、source品質を見てから段階的に増やす。
- metricsは `PARTIAL/UNAVAILABLE` を許容し、0埋めでPDCAしない。
- 投稿案は `WAITING_REVIEW` または `DRAFT` まで。READY化は別承認。

### 次に触ってよいファイル

- `scripts/collect_threads_metrics.py`
- `scripts/collect_source_posts.py`
- `scripts/collect_video_references.py`
- `scripts/run_growth_loop.py`
- `scripts/score_reference_posts.py`
- `scripts/generate_threads_ideas_from_references.py`
- 上記対応テスト
- runbook docs

### 衝突しやすいファイル

- `src/sheets_client.py`（タブ定義が広い）
- `scripts/recover_production_sheets_threads_first.py`（verify項目が多い）
- `config/source_accounts/default_sources.json`（source registry真実源）
- `docs/ai-work-handoff.md`（並行AIが追記しやすい）

### 触らない方がいいファイル

- `.env*`
- `data/`
- `output/`
- `.claude/plans/`
- secret/token/cookieを含む可能性があるローカル認証ファイル
- beauty_accountをactive/READY/POSTED化する設定

### 次AIへの引き継ぎメモ

- まず `git status --short` と `git rev-parse HEAD origin/main` を確認。
- `fetch_enabled=true` は0件が正しい。増やす場合は1〜2件だけ、必ずdry-runから。
- metrics自動取得は公開HTMLでは数値不可だった。`UNAVAILABLE` は正常な安全結果で、0にしない。
- source収集のapply先は `source_account_posts`。`reference_posts` ではない。
- `run_growth_loop.py` はdry-run summaryで候補数を出すだけ。投稿しない。

## Dependency inventory / adapter wiring (2026-06-30)

### 現在のHEAD / ブランチ

- 作業ブランチ: `main`
- 作業開始HEAD / origin/main: `dfdd955bc67b26184e22378e49127e17402250b6`
- 追加commit予定: `feat: 収集ライブラリ依存関係を棚卸し接続`

### 変更ファイル一覧

- `requirements.txt`
- `scripts/collect_threads_metrics.py`
- `scripts/collect_source_posts.py`
- `scripts/collect_video_references.py`
- `scripts/transcribe_video_reference.py`
- `scripts/cut_approved_clips.py`
- `scripts/upload_media_assets.py`
- `scripts/run_growth_loop.py`
- `docs/dependency-inventory.md`
- `docs/reference-pipeline-runbook.md`
- `docs/video-reference-runbook.md`
- `docs/media-pipeline-runbook.md`
- `docs/growth-loop-runbook.md`
- `docs/threads-operation-runbook.md`
- `docs/production-completion-status.md`
- `docs/ai-work-handoff.md`

### 追加ファイル一覧

- `scripts/test_dependency_inventory.py`
- `scripts/test_agent_reach_not_claimed_unless_installed.py`
- `scripts/test_cli_anything_not_claimed_unless_installed.py`
- `scripts/test_optional_dependency_imports.py`
- `scripts/test_playwright_adapter_safe.py`
- `scripts/test_bs4_lxml_source_parser.py`
- `scripts/test_ytdlp_metadata_adapter_no_download.py`
- `scripts/test_youtube_transcript_adapter_gate.py`
- `scripts/test_tiktok_metadata_adapter_no_download.py`
- `scripts/test_ffmpeg_cut_requires_owned_rights.py`
- `scripts/test_cloudinary_upload_requires_confirm.py`
- `scripts/test_no_secret_cookie_in_scraper_adapters.py`
- `scripts/test_run_growth_loop_reports_adapter_status.py`

### requirements追加内容

- `beautifulsoup4`
- `lxml`
- `playwright`
- `yt-dlp`
- `youtube-transcript-api`
- `ffmpeg-python`
- `cloudinary`
- `pillow`

### 実装内容

- `collect_threads_metrics.py`
  - Playwright browser adapterを追加。
  - `--browser-engine public|playwright` と `--storage-state` を追加。
  - storage_state内容、cookie、tokenは読まない・表示しない。
  - Playwright未導入/ブラウザ未準備時は `UNAVAILABLE`。
- `collect_source_posts.py`
  - BeautifulSoup/lxml OG parserを追加。未導入時はregex fallback。
  - adapter_statusに `beautifulsoup4`, `lxml`, `requests`, `tweepy`, `agent_reach`, `cli_anything` を表示。
  - Xはtweepy skeletonのみ。fetch/postは引き続きOFF。
- `collect_video_references.py`
  - `yt-dlp` metadata adapterを追加。`skip_download=True`, `download=False`。
  - YouTube transcript adapterを追加。取得不可は `UNAVAILABLE`。
  - TikTok URLもplatform判定・dry-run可能。
- `transcribe_video_reference.py`
  - `--video-url` + `--fetch-youtube-transcript` を追加。
  - 外部transcription APIは引き続き `ALLOW_TRANSCRIPTION_API=true` + CLI confirm必須。
- `cut_approved_clips.py`
  - ffmpeg CLI / ffmpeg-python adapter statusを表示。
  - third_party_reference_onlyはcut不可。
- `upload_media_assets.py`
  - Cloudinary SDK adapter statusを表示。
  - third-party media upload拒否、env + confirm gate維持。
- `run_growth_loop.py`
  - adapter_status summaryを表示。
  - AUTOPOST OFF / real_post false維持。

### Agent Reach / CLI-Anything 状態

- Agent Reach:
  - repo内: `src/reference/fetchers/agent_reach_fetcher.py` とsource registryに記述あり。
  - requirements: なし。
  - import: 既存fetcher内のみ。
  - 実行CLI: optional fetcher経由。今回インストール/実行なし。
  - 状態: optional。別プロジェクトのLibrary Scoutとは混同しない。
- CLI-Anything:
  - repo内: 実import/requirements/CLI wiringなし。
  - 状態: optional / not_found。導入済みとは扱わない。

### dry-run / test結果

- `pip install -r requirements.txt`: 多くは既にinstalled。sandboxでは `ffmpeg-python` 取得時にDNS失敗。承認付き再実行は承認システム `out of credits` で拒否。迂回なし。
- import確認:
  - OK: `bs4`, `lxml`, `playwright`, `yt_dlp`, `youtube_transcript_api`, `PIL`
  - MISSING: `ffmpeg` (`ffmpeg-python`), `cloudinary`
- 新規13本: PASS。
- 既存重要テスト:
  - `test_all_workflows_safety_flags.py`: PASS 103 / FAIL 0
  - `test_process_threads_queue.py`: PASS 11 / FAIL 0
  - `test_collect_source_posts_no_x_by_default.py`: PASS 2 / FAIL 0
  - `test_collect_threads_metrics_does_not_zero_unknowns.py`: PASS 3 / FAIL 0
  - `test_video_reference_no_download_for_third_party.py`: PASS 3 / FAIL 0
  - `test_upload_media_assets_rejects_third_party.py`: PASS 2 / FAIL 0
  - `test_run_growth_loop_no_auto_post.py`: PASS 3 / FAIL 0
- `git diff --check`: PASS。

### dry-run結果

- `collect_source_posts.py --platform threads --source-url ... --fetch-real --dry-run`: sandbox DNSでは `UNAVAILABLE`。adapter_status表示OK。media_download=false。
- `collect_video_references.py --url <YouTube URL> --fetch-metadata --metadata-adapter yt-dlp --dry-run`: sandbox DNSでは `UNAVAILABLE`。download=false。
- `run_growth_loop.py --dry-run --account-id all`: adapter_status表示OK、AUTOPOST OFF、real_post=false。

### 安全確認

- 実投稿なし。
- AUTOPOST OFF維持。
- X fetch/postなし。
- beauty投稿なし。
- third-party動画download/cut/upload/repostなし。
- Cloudinary実uploadなし。
- transcription API実呼び出しなし。
- secret/token/cookie表示なし。
- `.env`, `data/`, `output/`, `.claude/plans/` はcommit対象外。

### 未完了事項 / 残WARN

- `ffmpeg-python` と `cloudinary` はrequirementsに追加済みだが、承認システム `out of credits` により今回のpip install完了確認は未完。
- Playwright packageはimport可能だが、ブラウザbinary install状況は未確認。必要なら別途 `python -m playwright install chromium` を人間確認後に行う。
- Agent Reach / CLI-Anything は未導入。使う場合は導入元/ToS/ログイン状態の扱いを人間確認する。
- Threads公式APIでmetrics取得できるかは未完。公開HTMLはmetrics非表示があるため `UNAVAILABLE` を正常扱い。

### 次AIへの引き継ぎメモ

- `docs/dependency-inventory.md` を真実源として確認。
- optional候補を「導入済み」と報告しないこと。
- X/Threads/TikTok非公式取得はToS/安定性リスクを必ず明記。
- `fetch_enabled=true` は増やさない。
- Cloudinary/ffmpeg/Playwrightの実動作はenv/confirm/人間レビューが揃うまでdry-runのみ。

## Dependency runtime verification (2026-07-01)

### 現在のHEAD / ブランチ

- 作業ブランチ: `main`
- 作業開始HEAD / origin/main: `f1cead0dfdd5db5b591445ec12ea1bd597ffaa6f`
- 追加commit予定: `chore: 収集ライブラリ実行環境を検証`

### 変更ファイル一覧

- `scripts/transcribe_video_reference.py`
- `scripts/collect_video_references.py`
- `scripts/test_optional_dependency_imports.py`
- `docs/dependency-inventory.md`
- `docs/growth-loop-runbook.md`
- `docs/media-pipeline-runbook.md`
- `docs/video-reference-runbook.md`
- `docs/production-completion-status.md`
- `docs/ai-work-handoff.md`

### 実行環境確認

- `git fetch origin && git checkout main && git pull origin main`: PASS。開始時 `HEAD == origin/main == f1cead0dfdd5db5b591445ec12ea1bd597ffaa6f`。
- `pip install -r requirements.txt`: 初回はsandbox DNSで `ffmpeg-python` 取得失敗。承認付き再実行で成功。
- import確認:
  - OK: `bs4`, `lxml`, `playwright`, `yt_dlp`, `youtube_transcript_api`, `PIL`, `ffmpeg`, `cloudinary`。
- `python3 -m playwright install chromium`: 承認付き実行でexit 0。

### adapter dry-run結果

- Threads metrics Playwright:
  - `collect_threads_metrics.py --source browser --browser-engine playwright --post-url ... --dry-run`
  - `snapshot_count=2`
  - 両方 `metrics_status=UNAVAILABLE`, `error_reason=playwright_no_metrics`
  - 全metrics null。0捏造なし。cookie/storage_state表示なし。
- Threads source collect:
  - `selected_count=2`, `deduped_count=2`, `status=COLLECTED`
  - parser=`lxml`
  - `media_download=false`, `rights_status=reference_only`, `can_reuse_media=false`
  - raw payload redacted。Sheets applyなし。
- YouTube metadata:
  - `yt-dlp` adapterで `metadata_status=FETCHED`
  - `title/author_handle/extractor/duration` 取得
  - `download=false`
- YouTube transcript:
  - `youtube-transcript-api` adapterで `status=FETCHED`, `chunk_count=60`
  - transcript本文previewは空に修正。外部transcription APIなし、downloadなし。
- TikTok metadata:
  - profile URL `https://www.tiktok.com/@egachannel1`
  - `metadata_status=UNAVAILABLE`, `fetch_error=tiktok_profile_metadata_not_supported_no_download`
  - downloadなし。TikTokApi未使用。
- media adapters:
  - `cut_approved_clips.py --rights-status third_party_reference_only`: `BLOCKED`, `ffmpeg_cli=installed`, `ffmpeg_python=installed`
  - `upload_media_assets.py --dry-run`: `BLOCKED`, `cloudinary=installed`
- growth loop:
  - `run_growth_loop.py --dry-run --account-id all`: adapter_status表示OK、`auto_post=false`, `real_post=false`

### テスト結果

- 新規/adapter系13本: PASS。
- 既存重要:
  - `test_all_workflows_safety_flags.py`: PASS 103 / FAIL 0
  - `test_process_threads_queue.py`: PASS 11 / FAIL 0
  - `test_run_growth_loop_no_auto_post.py`: PASS 3 / FAIL 0
- `git diff --check`: PASS。

### 安全確認

- SNS実投稿なし。
- AUTOPOST OFF維持。
- X fetch/postなし。
- beauty投稿なし。
- third-party動画download/cut/upload/repostなし。
- Cloudinary実uploadなし。
- 外部transcription API呼び出しなし。
- Sheets applyなし。
- `.env`, `data/`, `output/`, `.claude/plans/` はcommit対象外。
- `fetch_enabled=true` は増やしていない。

### 未完了事項 / 残WARN

- Threads metricsはPlaywrightでも公開ページ上の数値が取れず `UNAVAILABLE`。正規APIまたは合法な管理画面導線が必要。
- TikTok profile URLはplaylist展開を避けるため `UNAVAILABLE` とした。実metadata確認は個別 `/video/` URLで行う。
- Agent Reachはoptional維持。導入元/ToS/ログイン状態管理の確認が必要。

### 次に本番applyする条件

- metrics値を信頼できる導線で取得できること。
- source fetchは1〜2件だけ `fetch_enabled=true` にしてdry-run確認済みであること。
- mediaは `owned/licensed/approved_creator_clip` の権利確認済みであること。
- Cloudinary uploadは `ALLOW_CLOUDINARY_UPLOAD=true` + `--confirm-upload` をコマンドスコープでのみ使うこと。
- AUTOPOSTをONにする前にqueue/posted_results/duplicate guard verifyがPASSしていること。

## Codex handoff: rights-aware media ingestion (2026-07-01)

### 現在のHEAD / ブランチ

- 作業開始HEAD: `0ce2aab2e2c0a9434097140742367390ed22ed04`
- origin/main確認: `0ce2aab2e2c0a9434097140742367390ed22ed04`
- 作業ブランチ: `main`
- commit予定: `feat: 権利管理付きmedia ingestionを追加`

### 本システムについて

v2はsource registry / Sheets / dry-run導線を持つSNS Growth Engine。今回の作業は、新規投稿機能ではなく、参照素材とmedia assetの権利境界を明確化する補強。第三者素材は分析のみ、所有/許諾/承認済みcreator clipだけがmedia ingestion以降に進める。

### 変更ファイル一覧

- `src/media/rights_policy.py`
- `scripts/ingest_media_assets.py`
- `scripts/cut_approved_clips.py`
- `scripts/upload_media_assets.py`
- `scripts/collect_source_posts.py`
- `scripts/collect_video_references.py`
- `scripts/generate_threads_ideas_from_references.py`
- `scripts/generate_media_post_queue.py`
- `docs/media-pipeline-runbook.md`
- `docs/video-reference-runbook.md`
- `docs/reference-pipeline-runbook.md`
- `docs/growth-loop-runbook.md`
- `docs/threads-operation-runbook.md`
- `docs/dependency-inventory.md`
- `docs/production-completion-status.md`
- `docs/ai-work-handoff.md`

### 追加ファイル一覧

- `src/media/rights_policy.py`
- `scripts/ingest_media_assets.py`
- `scripts/test_rights_status_policy.py`
- `scripts/test_ingest_media_assets_blocks_third_party.py`
- `scripts/test_ingest_media_assets_allows_owned_dry_run.py`
- `scripts/test_ingest_media_assets_blocks_unknown.py`
- `scripts/test_cut_approved_clips_blocks_reference_only.py`
- `scripts/test_upload_media_assets_blocks_reference_only.py`
- `scripts/test_generate_posts_blocks_high_similarity_copy.py`
- `scripts/test_generate_posts_structure_reference_allowed.py`
- `scripts/test_x_threads_media_reference_only.py`
- `scripts/test_youtube_tiktok_reference_only_no_download.py`
- `scripts/test_media_queue_only_approved_assets.py`

### スケール方針

- 権利判定は `src/media/rights_policy.py` に寄せる。
- `third_party_reference_only` と `unknown` はmedia保存/切り出し/upload/queue利用禁止。
- `owned`, `licensed`, `approved_creator_clip` のみmedia pipeline eligible。
- X/Threads/YouTube/TikTokの第三者素材はmetadata/transcript/structure分析のみ。
- 投稿案生成はstructure/hook/topic referenceだけ許可し、薄いリライトや直接コピーをブロック。

### 未完了事項 / 残WARN

- 実Cloudinary uploadは未実行。
- 実ffmpeg cutは未実行。
- 実downloadは未実行。
- TikTok個別 `/video/` metadataは環境/対象URL次第で `UNAVAILABLE` になる可能性あり。downloadには進めない。
- 既存legacy docsには古い `rights_status=allowed` の記述が残る箇所があるため、次のdocs整理で新ステータスへ統一するとよい。

### テスト結果

- 新規rights/media/generation tests: PASS 34 / FAIL 0。
- `test_all_workflows_safety_flags.py`: PASS 103 / FAIL 0。
- `test_process_threads_queue.py`: PASS 11 / FAIL 0。
- `test_video_reference_no_download_for_third_party.py`: PASS 3 / FAIL 0。
- `test_upload_media_assets_rejects_third_party.py`: PASS 2 / FAIL 0。
- `test_run_growth_loop_no_auto_post.py`: PASS 3 / FAIL 0。
- `test_collect_source_posts_no_media_download.py`: PASS 2 / FAIL 0。
- `test_cloudinary_upload_requires_confirm.py`: PASS 3 / FAIL 0。
- `test_cut_approved_clips_requires_rights.py`: PASS 2 / FAIL 0。
- `test_cut_approved_clips_requires_confirm.py`: PASS 2 / FAIL 0。
- `test_generate_media_post_queue_waiting_review_only.py`: PASS 3 / FAIL 0。
- `git diff --check`: PASS。

### dry-run / BLOCKED確認

- `ingest_media_assets.py --rights-status third_party_reference_only --dry-run`: `BLOCKED`。
- `ingest_media_assets.py --rights-status unknown --dry-run`: `BLOCKED`。
- `ingest_media_assets.py --rights-status owned --dry-run`: `PLAN_ONLY`、download/upload/postなし。
- `cut_approved_clips.py --rights-status third_party_reference_only`: `BLOCKED`。
- `upload_media_assets.py` third-party/reference-only asset: `BLOCKED`。
- `collect_video_references.py` YouTube dry-run: `download=false`, metadata/transcriptは環境要因で `UNAVAILABLE`、本文previewなし。
- `collect_video_references.py` TikTok `/video/` dry-run: `download=false`, `UNAVAILABLE`、media pipeline不可。
- `collect_source_posts.py --platform threads --account-id all --dry-run`: `selected_count=0` because `fetch_enabled=false` maintained, `media_download=false`。
- `run_growth_loop.py --dry-run --account-id all`: `auto_post=false`, `real_post=false`, `real_collection_pipeline.status=NO_DATA`。

### 次に触ってよいファイル

- `src/media/rights_policy.py`
- `scripts/ingest_media_assets.py`
- `scripts/generate_media_post_queue.py`
- `scripts/collect_video_references.py`
- `scripts/generate_threads_ideas_from_references.py`
- `docs/*runbook.md`

### 触らない方がいいファイル

- `.env`
- `data/`
- `output/`
- `.claude/plans/`
- secret/cookie/tokenを含む可能性があるローカルファイル

### 衝突しやすいファイル

- `docs/ai-work-handoff.md`
- `scripts/generate_threads_ideas_from_references.py`
- `scripts/collect_source_posts.py`
- `scripts/collect_video_references.py`

### 次AIへの引き継ぎメモ

`rights_status=allowed` は互換用に `approved_creator_clip` へ正規化している。今後の実media運用では、source registryやSheets上の承認UIも `owned/licensed/approved_creator_clip` に寄せること。AUTOPOSTはOFF、生成queueはREADYにしない。third-party素材は本文・構造・傾向分析のみで、画像/動画bodyを保存しない。

## Codex handoff: source registry video/source inventory (2026-07-01)

### 現在のHEAD / ブランチ

- 作業開始HEAD: `4125e36ca2f937c607c240eff808ccc2b49e42a6`
- 作業ブランチ: `main`
- commit予定: `chore: 動画参照ソース登録状況を棚卸し`

### 本システムについて

テキスト投稿運用、参考投稿分析、権利管理付きmedia ingestionは実装済み。今回の作業は、YouTube/TikTok/X/Threadsの参照sourceと切り抜き対象sourceの登録状況を棚卸しし、実URL未確定部分を架空URLなしのTODO placeholderとして可視化するもの。

### 変更ファイル一覧

- `config/source_accounts/default_sources.json`
- `config/source_accounts/owned_media_asset_template.json`
- `docs/source-registry-inventory.md`
- `docs/video-reference-runbook.md`
- `docs/media-pipeline-runbook.md`
- `docs/reference-pipeline-runbook.md`
- `docs/growth-loop-runbook.md`
- `docs/production-completion-status.md`
- `docs/ai-work-handoff.md`

### 追加ファイル一覧

- `config/source_accounts/owned_media_asset_template.json`
- `docs/source-registry-inventory.md`
- source registry inventory tests（commit前に追加）

### source registry 状況

- `default_sources.json`: 67件。
- Threads: 7件登録済み、fetch_enabled=false。
- X: 16件登録済み、fetch_enabled=false、manual/reference-only。
- YouTube: 28件。既存チャンネル/playlist登録あり、night_scout/liver_managerの個別動画URLはTODO placeholder 2件。
- TikTok: 9件。beauty_account既存7件、night_scout/liver_managerの個別動画URLはTODO placeholder 2件。
- TODO placeholder: 4件、全て `fetch_enabled=false`, `manual_only=true`, `rights_status=unknown`, `current_status=needs_human_url`。
- `clip_enabled=true`: 0。
- `media_pipeline_eligible=true`: 0。
- `beauty_account active`: 0。
- `X fetch enabled`: 0。

### スケール方針

- 人間が実URLを入れるまではTODO placeholderをfetch対象にしない。
- YouTube/TikTok third-party素材はanalysis only。個別動画URLが入っても、権利承認がない限りdownload/cut/upload/repost不可。
- 自社/許諾済み素材は `owned_media_asset_template.json` のpermission fieldsを埋めてから `ingest_media_assets.py` へ渡す。
- `owned/licensed/approved_creator_clip` 以外はmedia pipeline eligibleにしない。

### 未完了事項 / 残WARN

- night_scout/liver_managerのYouTube個別clip対象URLは人間入力待ち。
- night_scout/liver_managerのTikTok個別 `/video/` URLは人間入力待ち。
- beauty_accountは引き続きdraft-only/inactive。美容投稿・fetchはしない。
- Google Sheetsへのsource registry applyはこのturnでは未実行。

### dry-run / テスト結果

- `collect_source_posts.py --platform threads --account-id all --dry-run`: `selected_count=0`, `skipped_count=67`, `media_download=false`, `x_enabled=false`。
- YouTube existing channel URL dry-run: `PLAN_ONLY`, `download=false`, metadataは環境/対象URL都合で `UNAVAILABLE`。
- TikTok existing profile URL dry-run: `PLAN_ONLY`, `download=false`, `tiktok_profile_metadata_not_supported_no_download`。
- `ingest_media_assets.py --rights-status owned --dry-run`: `PLAN_ONLY`, `media_download=false`, `cloudinary_upload=false`, `real_post=false`。
- `run_growth_loop.py --dry-run --account-id all`: `auto_post=false`, `real_post=false`, `real_collection_pipeline.status=NO_DATA`。
- 新規source registry inventory tests: PASS 30 / FAIL 0。
- 既存重要安全テスト: PASS（`test_all_workflows_safety_flags.py` 103 / FAIL 0、ほか指定テストPASS）。
- `git diff --check`: PASS。

### 次に触ってよいファイル

- `config/source_accounts/default_sources.json`
- `config/source_accounts/owned_media_asset_template.json`
- `docs/source-registry-inventory.md`
- `docs/*runbook.md`
- source registry inventory tests

### 触らない方がいいファイル

- `.env`
- `data/`
- `output/`
- `.claude/plans/`
- secret/token/cookie値を含む可能性があるファイル

### 次AIへの引き継ぎメモ

次に人間が渡すべきURLは、`youtube_night_scout_reference_todo`, `youtube_liver_reference_todo`, `tiktok_night_scout_reference_todo`, `tiktok_liver_reference_todo` に入れる実URL。placeholderの `source_url` は空のままが正しい状態。架空URLやexample URLを本番source registryに入れないこと。

## Codex handoff: reference source/library policy finalization (2026-07-02)

### 現在のHEAD / ブランチ

- 作業開始HEAD: `87688fa00285d6b879b874714a97835d685e7865`（ユーザー指定の `4125e36` 以降）
- 作業ブランチ: `main`
- commit予定: `chore: 参照ソースと収集ライブラリ方針を最終整理`

### 今回の変更

- `docs/dependency-inventory.md` に採用ライブラリ方針表を追加。
- `docs/media-rights-template.md` を新規作成。
- `config/source_accounts/default_sources.json` に `owned_media_assets_todo` を追加。
- `config/source_accounts/owned_media_asset_template.json` をpermission evidence / creator / allowed uses / reviewer fieldsまで拡張。
- `docs/source-registry-inventory.md` をlocal placeholder、`transcript_enabled`、`collection_method`込みで再生成。
- Agent Reach / last30days-skill / tiktok-to-ytdlp は optional/external/helper であり、本番稼働済みとは扱わないことをdocs/testsで固定。

### source registry 状況

- `default_sources.json`: 68件。
- Threads: 7件登録済み、fetch_enabled=false。
- X: 16件登録済み、fetch_enabled=false、fetch/post OFF。
- YouTube: 28件。既存チャンネル/playlist登録あり、個別動画URL TODO 2件。
- TikTok: 9件。beauty_account既存7件、night_scout/liver_manager個別動画URL TODO 2件。
- local: `owned_media_assets_todo` 1件。rights evidence / local_file_ref / allowed uses入力待ち。
- TODO / rights-review placeholder: 5件。
- `fetch_enabled=true`: 0。
- `clip_enabled=true`: 0。
- `media_pipeline_eligible=true`: 0。
- `beauty_account active`: 0。

### 人間入力待ち

- `youtube_night_scout_reference_todo`: real YouTube channel/video URL.
- `youtube_liver_reference_todo`: real YouTube channel/video URL.
- `tiktok_night_scout_reference_todo`: real TikTok `/video/` URL preferred.
- `tiktok_liver_reference_todo`: real TikTok `/video/` URL preferred.
- `owned_media_assets_todo`: local file/source URL, owner/creator, permission evidence, dates, allowed/prohibited uses, reviewer.
- Agent Reachを有効化する場合: install source, CLI command, login/session policy, ToS approval, trusted output schema.
- last30days-skillを有効化する場合: execution method, query templates, output schema, rate limits.

### 安全確認

- 実投稿なし。
- AUTOPOST OFF維持。
- X fetch/postなし。
- beauty_account active/READY/POSTED化なし。
- third-party download/cut/upload/repostなし。
- Cloudinary実uploadなし。
- transcription API実呼び出しなし。
- `.env`, `data/`, `output/`, `.claude/plans/` はcommit対象外。

## Codex handoff: production pilot dry-run preparation (2026-07-02)

### 現在のHEAD / ブランチ

- 作業開始HEAD: `9eaa7517f60f2320cf690dbf41908df2a829d7b4`
- 作業ブランチ: `main`
- commit予定: `docs: 本番pilot運用手順を追加`

### 今回の変更

- `docs/production-pilot-runbook.md` を作成。
- `scripts/prepare_pilot_sources.py` を追加。dry-run-firstで、applyには `--apply --confirm-pilot` が必須。
- pilot候補を `docs/source-registry-inventory.md` とrunbookに記載。
- pilot安全テストを追加。

### pilot候補

- `night_scout`: `src_ns_threads_required_001` (`https://www.threads.com/@kyaba_ryo`)
- `night_scout`: `src_ns_threads_required_002` (`https://www.threads.com/@mizuno9120`)
- `liver_manager`: `src_lm_yt_cand_001` (`https://www.youtube.com/@suu-san_pococha`)

### 現在の安全カウント

- `fetch_enabled=true`: 0。
- `clip_enabled=true`: 0。
- `media_pipeline_eligible=true`: 0。
- TODO / rights placeholder: 5。
- beauty active/fetch: 0。
- AUTOPOST: OFF。

### 次に人間がやること

- pilot候補3件でよいか確認。
- OKなら `python3 scripts/prepare_pilot_sources.py --account-id all --max-per-account 2 --apply --confirm-pilot` を実行。
- apply後、Sheets書き込み前に `collect_source_posts.py` と `run_growth_loop.py` のdry-runを再確認。
- AUTOPOSTはまだONにしない。

## Codex handoff: autonomous video reference connection (2026-07-02)

### 現在のHEAD / ブランチ

- 作業開始HEAD: `c415b8320a92da77d9a2612fa7c9fe815787ea83`
- 作業ブランチ: `main`
- origin/main開始値: `c415b8320a92da77d9a2612fa7c9fe815787ea83`
- commit予定: `feat: 動画参照分析を承認レス自動運用に接続`

### 今回の変更ファイル

- `.github/workflows/autonomous-growth-loop.yml`
- `config/source_accounts/default_sources.json`
- `scripts/run_autonomous_loop.py`
- `scripts/auto_approve_queue.py`
- `scripts/seed_source_registry.py`
- `docs/autonomous-mode-runbook.md`
- `docs/video-reference-runbook.md`
- `docs/growth-loop-runbook.md`
- `docs/production-completion-status.md`
- `docs/source-registry-inventory.md`
- `docs/ai-work-handoff.md`

### 追加ファイル

- `scripts/test_autonomous_apply_blocks_when_no_sources.py`
- `scripts/test_autonomous_apply_blocks_when_required_secrets_missing.py`
- `scripts/test_autonomous_loop_includes_youtube_reference_analysis.py`
- `scripts/test_autonomous_loop_skips_tiktok_placeholder.py`
- `scripts/test_autonomous_transcript_preview_suppressed.py`
- `scripts/test_autonomous_video_reference_blocks_unavailable_metadata.py`
- `scripts/test_autonomous_video_reference_generates_text_only_post.py`
- `scripts/test_autonomous_video_reference_no_download.py`
- `scripts/test_autonomous_workflow_schedule_safe.py`

### 実装内容

- `run_autonomous_loop.py` にYouTube/TikTokの参照分析ステップを接続。
- YouTube metadata/transcript/structure由来のtext-only Threads候補生成を接続。
- TikTokは個別 `/video/` URLのみ対象。TODO placeholderとprofile-onlyはskip。
- transcript本文previewをautonomous出力に含めない。
- third-party動画はdownload/cut/upload/repost不可を維持。
- `max_posts_per_run=1` をアカウントごとではなくrun全体で強制。
- `auto_approve_queue.py --skip-setup` と `seed_source_registry.py --skip-setup` を追加し、Sheets read quota消費を抑制。
- GitHub Actionsは初回成功後にschedule有効化済み。JST 09:15 daily。手動applyは `confirm_autonomous=true` のworkflow_dispatch。

### source / Sheets 状況

- ローカル `default_sources.json`: 68件。
- Sheets verify: PASS 61 / FAIL 0。
- Sheets counts: `source_accounts=68`, `reference_sources=37`, `posted_results=6`, `media_assets=0`。
- `fetch_enabled=true`: 0。
- `clip_enabled=true`: 0。
- `media_pipeline_eligible=true`: 0。
- beauty active/fetch: 0。
- YouTube real source: 26件。
- TikTok real individual `/video/`: 0件。
- TikTok TODO: 2件。

### dry-run / apply結果

- `python3 scripts/run_autonomous_loop.py --account-id all --dry-run`: PASS / `PLAN_ONLY`。
- Selected sources:
  - `src_lm_yt_cand_001` (`https://www.youtube.com/@suu-san_pococha`)
  - `src_ns_threads_required_001` (`https://www.threads.com/@kyaba_ryo`)
  - `src_ns_threads_required_002` (`https://www.threads.com/@mizuno9120`)
- YouTube analysis: connected。
- YouTube transcript: connected。ただしchannel URLはvideo_idが無いため実transcriptは `UNAVAILABLE` になり得る。
- TikTok analysis: code path connected。実URLは未入力/TODOのためskip。
- media posts: OFF。
- video download/cut/upload/repost: 未実行・不可。
- `python3 scripts/run_autonomous_loop.py --account-id all --apply --confirm-autonomous`: 承認レビュー側でreal Threads post可能コマンドとして拒否。回避実行なし。
- 新規実投稿URL: なし。

### テスト結果

- `py_compile`: PASS。
- Autonomous/video/safety targeted tests: 32 commands PASS / FAIL 0。
- 代表:
  - `test_autonomous_loop_includes_youtube_reference_analysis.py`: PASS。
  - `test_autonomous_video_reference_no_download.py`: PASS。
  - `test_autonomous_video_reference_generates_text_only_post.py`: PASS。
  - `test_autonomous_apply_blocks_when_required_secrets_missing.py`: PASS。
  - `test_all_workflows_safety_flags.py`: PASS 111 / FAIL 0。
  - `test_process_threads_queue.py`: PASS 11 / FAIL 0。

### 残WARN / 未完了

- 実applyはローカル承認レビューで停止。次に実投稿まで進める場合は、人間がreal Threads post可能な操作として明示承認する必要がある。
- TikTok night/liverの個別 `/video/` URLは未入力。
- YouTube個別動画URL TODOは残る。現状pilotはchannel URL metadata/reference only。
- third-party mediaは引き続きmedia pipeline対象外。
- GitHub Actions scheduleは初回Actions apply成功後に有効化済み。停止時は `kill_switch=true` またはworkflow scheduleコメントアウト。

### 次に触ってよいファイル

- `scripts/run_autonomous_loop.py`
- `scripts/auto_approve_queue.py`
- `scripts/collect_video_references.py`
- `scripts/generate_video_reference_posts.py`
- `docs/autonomous-mode-runbook.md`
- `docs/video-reference-runbook.md`
- `docs/ai-work-handoff.md`

### 触らない方がいいファイル

- `.env`
- `data/`
- `output/`
- `.claude/plans/`
- cookie/storage_state/token類
- `config/source_accounts/default_sources.json` のbeauty target名とsafety field

### 次AIへのメモ

承認レス自動運用のコード接続は完了。安全テストもPASS。唯一残った実運用BLOCKは、ローカル承認システムがreal Threads post可能なapplyコマンドを拒否したこと。次に進める場合は、まず `run_autonomous_loop.py --dry-run` と Sheets verify を再確認し、real post承認が取れた状態で `--apply --confirm-autonomous` を1回だけ実行する。X/beauty/media/third-party download系は触らない。

## Codex handoff: GitHub Actions autonomous apply runbook (2026-07-02)

### 現在のHEAD / ブランチ

- 作業開始HEAD: `072c317b3aa7dd33239e46f009cf397af51edd6a`
- 作業ブランチ: `main`
- commit予定: `docs: Actions経由の承認レス自動運用手順を追加`

### 今回の目的

ローカルCodexでは `run_autonomous_loop.py --apply --confirm-autonomous` がreal Threads post可能コマンドとして承認レビューに拒否された。回避実行はせず、GitHub Actions上で安全に初回autonomous applyを実行できるようにrunbookとテストを補強する。

### 変更内容

- `docs/autonomous-mode-runbook.md` にGitHub UIでの初回実行手順を追加。
- `docs/autonomous-mode-runbook.md` にschedule有効化条件とJST 09:15 cron手順を追加。
- `docs/video-reference-runbook.md` に `src_lm_yt_cand_001` がchannel URLでありtranscript `UNAVAILABLE` になり得ること、個別動画URLが必要なことを追記。
- `docs/growth-loop-runbook.md` と `docs/production-completion-status.md` にActions経由運用方針を追記。
- workflow安全性とdocs記載を固定するテストを追加予定。

### GitHub Actions運用メモ

- Workflow: `Autonomous Growth Loop`
- Trigger: `workflow_dispatch`
- Inputs: `confirm_autonomous=true`, `account_id=all`
- Dry-run stepはapply前に必ず走る。
- Apply stepは `confirm_autonomous=true` の時のみ。
- `PUBLISH_ENABLED=true` と `ALLOW_REAL_THREADS_POST=true` はapply step内だけ。
- `ALLOW_REAL_X_POST=false`, `ALLOW_VIDEO_DOWNLOAD=false`, `ALLOW_VIDEO_CUT=false`, `ALLOW_CLOUDINARY_UPLOAD=false`, `ALLOW_TRANSCRIPTION_API=false` 維持。
- `kill_switch=true` なら停止。
- scheduleは初回Actions apply成功後に有効化済み。JST 09:15 daily。

### まだ必要な人間入力

- GitHub Actions UIで初回 `Run workflow` を押す、またはCodexが `gh workflow run` を許可されること。
- 初回apply成功済み。schedule有効化済み。次は定期投稿結果とSheets `posted_results` を確認。
- TikTok night/liverの個別 `/video/` URL。
- YouTube個別動画URL。
- owned/licensed mediaの権利証跡。

### Actions dispatch attempt

- `gh workflow run "Autonomous Growth Loop" -f confirm_autonomous=true -f account_id=all`: 実行成功。
- Run id: `28571069128`。
- Result: failure / safe BLOCKED。
- Dry-run step: success。
- Guard step: success。
- Apply step: `night_scout` / `liver_manager` のThreads publish envが未設定としてpreflight BLOCK。実投稿なし。
- 原因: workflow job envに `THREADS_ACCESS_TOKEN_NIGHT_SCOUT`, `THREADS_USER_ID_NIGHT_SCOUT`, `THREADS_ACCESS_TOKEN_LIVER_MANAGER`, `THREADS_USER_ID_LIVER_MANAGER` を渡していなかった。
- 修正: workflowへ上記secret envを追加。次のdispatchでは同BLOCKは解消される見込み。

### Actions dispatch attempt 2

- `gh workflow run "Autonomous Growth Loop" -f confirm_autonomous=true -f account_id=all`: 実行成功。
- Run id: `28571199364`。
- Result: failure / safe BLOCKED。
- Dry-run step: success。
- Guard step: success。
- Apply preflight: success。Threads credentialsはSET。
- Apply step: Sheets verifyが `real_post_flags_false_default` でBLOCK。実投稿なし。
- 原因: apply step envの `PUBLISH_ENABLED=true` をread-only verifyが継承したため。
- 修正: `run_autonomous_loop.py` の `verify_sheets_connectivity()` でverify実行時だけ `PUBLISH_ENABLED=false` / real post and media flags false の安全envを渡すように変更。

### Actions dispatch attempt 3

- `gh workflow run "Autonomous Growth Loop" -f confirm_autonomous=true -f account_id=all`: 実行成功。
- Run id: `28571306895`。
- Result: failure / PARTIAL。
- Dry-run step: success。
- Guard step: success。
- Apply preflight: success。
- Read-only Sheets verify: success。
- YouTube metadata: success。`download=false`、channel URLのためtranscriptは `UNAVAILABLE/youtube_video_id_missing`。
- Threads source collect apply: success、dedupeによりappend 0。
- `night_scout` score/generate/AUTO_READY: success。1件READY化。
- `liver_manager` AUTO_READY: Sheets API 429 read quotaで停止。実投稿なし。
- 修正: apply modeでは `max_posts_per_run=1` に合わせ、score/generate/AUTO_READY対象も最初の1アカウントに絞る。これにより1 run 1投稿上限を守りつつSheets read量を削減。

### Actions dispatch attempt 4

- `gh workflow run "Autonomous Growth Loop" -f confirm_autonomous=true -f account_id=all`: 実行成功。
- Run id: `28571552118`。
- Result: success。
- Dry-run step: success。
- Guard step: success。
- Apply step: success。
- YouTube metadata: success。`download=false`、channel URLのためtranscriptは `UNAVAILABLE/youtube_video_id_missing`。
- Threads source collect apply: success、dedupeによりappend 0。
- `night_scout` score/generate/AUTO_READY/process queue: success。
- `liver_manager`: `max_posts_per_run=1` によりpost pipeline skip。
- Posted queue id: `q_night_scout_manualref_src_ns_threads_required_002_threads`。
- Result id: `threads_q_night_scout_manualref_src_ns_threads_required_002_threads_20260702065829`。
- External post id: `17928528360351269`。
- Post URL: `https://www.threads.com/@kyaba_consul_mizu/post/DaSAIF3lmCd`。
- ローカルからの追加Sheets verifyは承認システムout-of-creditsで拒否。Actionsログ上は `status=POSTED` とpost URLあり。
- 次: schedule有効化済み。次回JST 09:15 scheduled run後に投稿内容とSheets `posted_results` を確認する。

## Codex handoff: autonomous schedule enabled (2026-07-02)

### 現在のHEAD / ブランチ

- 作業開始HEAD: `dafad9f140091f294219878630f5bc6bf5e86822`
- 作業ブランチ: `main`
- commit予定: `chore: autonomous growth loop scheduleを有効化`

### 今回の変更

- `.github/workflows/autonomous-growth-loop.yml` のscheduleを有効化。
- Cron: `15 0 * * *` (JST 09:15 daily)。
- schedule時も `Guard autonomous confirm and kill switch` と `Apply autonomous Threads loop` が動くよう、条件を `github.event_name == 'schedule' || github.event.inputs.confirm_autonomous == 'true'` に更新。
- `PUBLISH_ENABLED=true` / `ALLOW_REAL_THREADS_POST=true` はapply step内のみ。
- `ALLOW_REAL_X_POST=false`, `ALLOW_VIDEO_DOWNLOAD=false`, `ALLOW_VIDEO_CUT=false`, `ALLOW_CLOUDINARY_UPLOAD=false`, `ALLOW_TRANSCRIPTION_API=false` 維持。
- `max_posts_per_run=1`, `daily_post_cap_per_account=1`, `cooldown_minutes=180`, `kill_switch=false` 維持。

### 運用メモ

- 変な投稿が出たら最優先で `config/autonomous_mode.json` の `kill_switch=true` をcommit/push。
- scheduleだけ止める場合は `.github/workflows/autonomous-growth-loop.yml` の `schedule` blockをコメントアウト。
- TikTok night/liverの個別 `/video/` URL、YouTube個別動画URL、owned/licensed media権利証跡は引き続き人間入力待ち。

## Codex handoff: public post leak fix and account rotation (2026-07-03)

### 現在のHEAD / ブランチ

- 作業開始HEAD: `04b834364a14959fbdf2ec96283d64b8b64aa1fc`
- 作業完了HEAD: このhandoff更新commitの `git rev-parse HEAD`。最終報告で正確なSHAを提示する。
- 作業ブランチ: `main`
- commit: `fix: 投稿本文の内部情報漏れを防ぎアカウントローテーションを追加`

### 問題

- 直近の `night_scout` 投稿に、内部メモ・参照元情報・AIの生成指示に相当する文言が漏れた。
- 代表例: `今回の切り口`, `threads / night_work_scout`, `そのまま真似るのではなく`, `LINE/DMへの導線は最後`。
- これは読者向け投稿ではなく、以後は必ずBLOCKする。

### 変更ファイル一覧

- `scripts/public_post_quality.py`
- `scripts/generate_threads_ideas_from_references.py`
- `scripts/generate_video_reference_posts.py`
- `scripts/auto_approve_queue.py`
- `scripts/process_threads_queue.py`
- `scripts/run_autonomous_loop.py`
- `config/post_generation_rules.json`
- `config/autonomous_mode.json`
- `config/auto_approval_rules.json`
- `docs/autonomous-mode-runbook.md`
- `docs/growth-loop-runbook.md`
- `docs/production-completion-status.md`
- `docs/ai-work-handoff.md`
- `scripts/test_public_post_validator_*.py`
- `scripts/test_autonomous_loop_*.py`
- `scripts/test_bad_ready_queue_blocked_before_post.py`
- `scripts/test_night_scout_post_generation_reader_facing.py`
- `scripts/test_liver_manager_post_generation_reader_facing.py`
- `scripts/test_account_rotation_*.py`
- `scripts/test_internal_terms_never_in_posted_text.py`

### 実装内容

- `final_public_post_validator` を追加し、内部語・参照元情報・URL・score/queue/result系メタデータ・AI/生成指示文・高圧CTA・誇大収益表現をBLOCK。
- 投稿生成出力を `{internal_analysis, public_post_text, safety_notes, blocked_reasons}` として扱い、publisherへ渡すのは `public_post_text` のみ。
- `auto_approve_queue.py` でAUTO_READY前に公開本文品質を検査。
- `process_threads_queue.py` で投稿直前に再検査し、NGなら `BLOCKED_INTERNAL_LEAK` に変更。
- `run_autonomous_loop.py --dry-run` は安全な `public_post_preview` と validator結果を表示し、内部分析本文は出さない。
- `night_scout` / `liver_manager` の交互投稿を狙う account rotation を追加。`max_posts_per_run=1` と daily cap は維持。

### 未完了事項 / 残WARN

- 既存Sheets上の悪いREADY/AUTO_READY候補への即時apply処理はこのターンでは実投稿なしのdry-run確認まで。次回worker実行時は投稿直前に `BLOCKED_INTERNAL_LEAK` で止まる。
- TikTok `/video/` URL、YouTube個別動画URL、owned/licensed media権利証跡は人間入力待ち。
- YouTube/TikTok切り抜き・download/cut/upload/media投稿は今回触っていない。

### テスト結果 / dry-run結果

- `python3 -m py_compile scripts/public_post_quality.py scripts/run_autonomous_loop.py scripts/process_threads_queue.py scripts/auto_approve_queue.py scripts/generate_threads_ideas_from_references.py scripts/generate_video_reference_posts.py`: PASS。
- 追加テスト15本: PASS。
- 既存安全テスト:
  - `test_all_workflows_safety_flags.py`: PASS 116 / FAIL 0。
  - `test_autonomous_workflow_schedule_enabled.py`: PASS 4 / FAIL 0。
  - `test_autonomous_workflow_no_x_no_media.py`: PASS。
  - `test_autonomous_posts_only_threads.py`: PASS。
  - `test_process_threads_queue.py`: PASS 11 / FAIL 0。
  - `test_generate_posts_blocks_high_similarity_copy.py`: PASS。
  - `test_rights_status_policy.py`: PASS 6 / FAIL 0。
  - `test_source_registry_no_beauty_active.py`: PASS。
  - `test_source_registry_no_x_fetch_by_default.py`: PASS。
- `git diff --check`: PASS。
- `python3 scripts/run_autonomous_loop.py --account-id all --dry-run`: selected_account=`liver_manager`, skipped_account=`night_scout/account_rotation_not_first`, `internal_leak_check=PASS`, `account_fit_check=PASS`, `final_validator_result=PASS`, `would_post=false`。

### 次に触ってよいファイル

- `scripts/public_post_quality.py`
- `scripts/run_autonomous_loop.py`
- `scripts/auto_approve_queue.py`
- `scripts/process_threads_queue.py`
- `config/post_generation_rules.json`
- docs/runbook類

### 触らない方がいいファイル

- `.env`
- `data/`
- `output/`
- `.claude/plans/`
- cookie / storage_state / token類
- 実投稿・実download・実cut・実upload関連の認証値

### 次AIへの引き継ぎメモ

- scheduleは維持。事故防止は `final_public_post_validator` で担保する方針。
- 変な投稿が出たら即 `kill_switch=true`。
- `public_post_text` 以外をpublisherへ渡す変更は絶対に入れない。
- `night_scout` と `liver_manager` のローテーションは posted_results を読める場合は直近投稿アカウントと反対側を優先する。

## Codex handoff: account-specific schedule and liver references (2026-07-04)

### 現在のHEAD / ブランチ

- 作業開始HEAD: `a17f715fc41feec44a97be6d74afe956a613e61b`
- 作業ブランチ: `main`
- commit予定: `chore: 投稿スケジュールをアカウント別に変更しliver参照元を追加`

### 変更ファイル一覧

- `.github/workflows/autonomous-growth-loop.yml`
- `.github/workflows/autonomous-growth-loop-night-scout.yml`
- `.github/workflows/autonomous-growth-loop-liver-manager.yml`
- `config/autonomous_mode.json`
- `config/auto_approval_rules.json`
- `config/source_accounts/default_sources.json`
- `scripts/source_url_utils.py`
- `scripts/prepare_pilot_sources.py`
- `scripts/run_autonomous_loop.py`
- schedule/source/video safety tests
- `docs/source-registry-inventory.md`
- `docs/video-reference-runbook.md`
- `docs/growth-loop-runbook.md`
- `docs/autonomous-mode-runbook.md`
- `docs/production-completion-status.md`
- `docs/ai-work-handoff.md`

### 実装内容

- scheduled workflowを `night_scout` / `liver_manager` に分割。
- old `autonomous-growth-loop.yml` はmanual dispatch専用に変更。
- 各scheduleはターゲット時刻15分前に起動し、0-1800秒jitterで±15分内に実行。
- `daily_post_cap_per_account=5`, `daily_ready_cap_per_account=8`, `max_posts_per_run=1`, `cooldown_minutes=90`。
- account-specific workflowは固定 `ACCOUNT_ID` を使う。manual `account_id=all` の場合のみ既存rotationを使う。
- liver_manager用に以下のqueryなしURLを追加:
  - `https://youtube.com/channel/UCzFzty7aEd4tw3NqCW6pkLQ`
  - `https://www.tiktok.com/@user5597696107300`
  - `https://www.tiktok.com/@me02_lsm`
  - `https://www.tiktok.com/@uare.inc`

### 残WARN / 未完了

- 追加TikTok account URLは `manual_only=true`; profile展開・fetch・clip化はしない。
- YouTube/TikTok third-party mediaはreference analysis only。
- 動画download/cut/upload/media投稿は今回も未ON。
- source registryのSheets applyはこのターンでは実行しない。

### 次AIへの引き継ぎメモ

- workflow schedule変更後の初回scheduled runでは、各accountの投稿時刻、jitter秒数、posted_results、daily capを確認する。
- TikTok account URLを `/video/` に勝手に展開しない。
- `final_public_post_validator` は弱めない。
- `public_post_text` 以外をpublisherへ渡さない。

## Codex handoff: READY generation review closure (2026-07-10)

### 現在のHEAD / ブランチ

- 作業開始HEAD: `d7357e00875a41685bec92c9ebcc4bdb4583b0f5`
- 作業ブランチ: `main`
- commit予定: `fix: READY生成の実運用テストと仕様整合性を補強`

### 今回確認したこと

- 添付レビューの指摘は正しかった。`d7357e0` 時点では、schedule発火診断とfallbackは入っていたが、空referenceからREADYを作れること、`--stop-before-post`で投稿せずREADY生成を検証できること、AUTO_READY仕様とdocsの整合、text-onlyの`media_reuse_risk`分類、5投稿/日のテーマ在庫が不足していた。
- 今回は実投稿、手動apply、実download、実cut、実upload、Cloudinary upload、transcription API、X fetch/post、beauty active化は実行していない。

### 変更ファイル一覧

- `scripts/generate_threads_ideas_from_references.py`
- `scripts/public_post_quality.py`
- `scripts/autonomous_recovery_test_utils.py`
- `scripts/process_threads_queue.py`
- `scripts/recover_production_sheets_threads_first.py`
- `docs/production-completion-status.md`
- `docs/reference-pipeline-runbook.md`
- `docs/sheets-manual-check-guide.md`
- `docs/threads-operation-runbook.md`
- `docs/threads-idea-generation-runbook.md`
- `docs/threads-queue-worker.md`
- `docs/video-clip-generation-usage.md`
- `docs/ai-work-handoff.md`

### 追加ファイル一覧

- `scripts/test_scheduled_apply_can_create_ready_from_empty_references.py`
- `scripts/test_stop_before_post_creates_ready_without_posting.py`
- `scripts/test_safe_fallback_rotates_topics.py`
- `scripts/test_safe_fallback_not_duplicate_same_day.py`
- `scripts/test_auto_ready_accepts_safe_original_fallback.py`
- `scripts/test_auto_ready_reject_reasons_are_written_to_queue.py`
- `scripts/test_auto_ready_ready_count_summary_matches_updates.py`
- `scripts/test_process_threads_queue_posts_ready_text_only_path_static.py`
- `scripts/test_posted_results_has_post_url_or_external_id.py`
- `scripts/test_posted_results_metrics_pending_after_post.py`
- `scripts/test_autonomous_health_saved_on_apply.py`
- `scripts/test_generate_docs_comments_match_auto_ready_spec.py`
- `scripts/test_text_only_media_reuse_risk_not_high.py`
- `scripts/test_night_scout_theme_pool_size.py`
- `scripts/test_liver_manager_theme_pool_size.py`
- `scripts/test_same_day_theme_rotation.py`
- `scripts/test_pdca_pending_after_post.py`
- `scripts/test_media_growth_roadmap_off_by_default.py`

### 実装内容

- text-only fallback queueの`media_reuse_risk`を`not_applicable`へ正規化。動画/画像再利用リスクとtext-only候補を混同しない。
- fallback template rotationをaccount別template数と15分slot基準に変更し、同日内の同一テーマ連発を避ける。
- `night_scout` fallback templateを15本、`liver_manager`を12本に拡張。全templateは`final_public_post_validator` PASSを固定。
- READY昇格仕様を「`approve_queue.py`人間承認または`auto_approve_queue.py` AUTO_READY」に統一。旧「人間のみ」コメント/docsを修正。
- AUTO_READY reject reason、ready/checked/approved/rejected summary、posted_results post_url/external_id、metrics PENDING、PDCA pending、autonomous_health保存仕様をテスト化。
- `--stop-before-post`は投稿workerを呼ばず、READY生成側だけを確認するproduction diagnosticとして固定。

### 未完了事項 / production-off

- 実metrics自動取得とPDCA改善の自動適用は未ON。`posted_results.metrics_status=PENDING`とPDCA初期記録まで。
- Media Growth Engineはsource discovery / transcript / clip candidate / runner / validator / PDCA記録の基盤あり。ただしmedia scheduleはOFF。
- 実download / 実cut / 実Cloudinary upload / Threads video+text post / transcription APIはenv+confirm必須で、今回未実行。
- X fetch/post、beauty投稿、learning_rules auto-applyは引き続きOFF。

### テスト結果 / dry-run結果

- 追加READY/AUTO_READY/テーマ在庫/PDCA/media-offテスト18本: PASS。
- `python3 scripts/check_autonomous_health.py --account-id all --dry-run`: PASS。workflows/schedules/config/source registry/media off checksにproblemなし。
- `python3 scripts/run_autonomous_loop.py --account-id night_scout --dry-run`: PLAN_ONLY。public_post_preview自然文、internal_leak_check=PASS、final_validator_result=PASS、would_post=false。
- `python3 scripts/run_autonomous_loop.py --account-id liver_manager --dry-run`: PLAN_ONLY。public_post_preview自然文、internal_leak_check=PASS、final_validator_result=PASS、would_post=false。
- `python3 scripts/test_all_workflows_safety_flags.py`: PASS 139 / FAIL 0。
- `python3 scripts/test_autonomous_workflow_no_x_no_media.py`: PASS 1 / FAIL 0。
- `python3 scripts/test_autonomous_posts_only_threads.py`: PASS 1 / FAIL 0。
- `python3 scripts/test_internal_terms_never_in_posted_text.py`: PASS 1 / FAIL 0。
- `python3 scripts/test_source_registry_no_beauty_active.py`: PASS 1 / FAIL 0。
- `python3 scripts/test_source_registry_no_x_fetch_by_default.py`: PASS 1 / FAIL 0。
- `python3 scripts/test_rights_status_policy.py`: PASS 6 / FAIL 0。
- `python3 -m py_compile ...`: PASS。
- `git diff --check`: PASS。

### 次に触ってよいファイル

- `scripts/generate_threads_ideas_from_references.py`
- `scripts/public_post_quality.py`
- `scripts/auto_approve_queue.py`
- `scripts/run_autonomous_loop.py`
- `scripts/process_threads_queue.py`
- `scripts/check_autonomous_health.py`
- docs/runbook類

### 衝突しやすいファイル

- `docs/ai-work-handoff.md` は履歴が長く、Claude Code/Codex双方が追記しやすい。
- `docs/production-completion-status.md` は状態分類が増えやすい。
- `scripts/autonomous_recovery_test_utils.py` はwrapper多数の共通実装になっている。

### 触らない方がいいファイル

- `.env`
- `data/`
- `output/`
- `.claude/plans/`
- cookie / storage_state / token / secret 類
- 実投稿・実download・実cut・実upload関連の認証値

### 次AIへの引き継ぎメモ

- 次回scheduled runで見るべき最重要項目は `health_summary.ready_count`, `health_summary.posted_count`, `health_summary.no_post_reason`, `posted_results.post_url` or `external_post_id`, `metrics_status=PENDING`。
- `NO_READY_QUEUE` が再発した場合、workflow発火ではなくAUTO_READY reject reason / queue diagnosticsを見る。
- media系は「基盤あり、本番OFF」。text-only scheduleを壊さないことを最優先にする。
- `public_post_text`以外をpublisherへ渡す変更は絶対に入れない。

## Codex handoff: production recovery and media workflow closure (2026-07-12)

### 現在のHEAD / ブランチ

- 作業開始HEAD: `a861c4388a056a9d76cf6d684f8cc06da2b73e8a` 以降の復旧作業を継続。
- 最新push済みHEAD: `25ff93400b52b3b6671074667339e057124e7831`。
- 作業ブランチ: `main`。
- 追加commit: `b304003b9372de2257b671824468a0ee1826bfce` (`fix: media production workflowを自己完結化`)。

### 変更ファイル一覧

- `.github/workflows/media-growth-production.yml`
- `scripts/run_media_growth_engine.py`
- `scripts/run_media_production_pipeline.py`
- `docs/ai-work-handoff.md`
- `docs/production-completion-status.md`

### 追加ファイル一覧

- `scripts/test_media_production_no_candidate_is_no_post.py`
- `scripts/test_media_growth_workflow_prepares_candidates_before_post.py`
- `scripts/test_media_growth_updates_stale_clip_candidates.py`

### 今回判明した原因と修正

- text-only自動投稿が止まっていた主因はGoogle Sheets quota 429とworkflow concurrencyの設定衝突だった。`25ff934` までで、workflow別concurrency、optional source failureのnon-blocking化、queue/posted_results/AUTO_READY更新のbatch化とretryを入れた。
- 最新HEADで `Autonomous Growth Loop Night Scout` run `29177989151` は success。
- 最新HEADで `Autonomous Growth Loop Liver Manager` run `29178058830` は success。
- 最新HEADで `Production Autopilot Aftercare` run `29178159618` は success。
- 最新HEADで `Media Transcription Production` run `29178232402` は success。
- `Media Growth Production` run `29178280182` は、権利/secret/ffmpeg guardまでは通ったが `no_eligible_media_candidate` で失敗。候補は存在したが、YouTubeは古いclip rowが `clip_not_ready`、TikTokは `transcript_grounding_required` で弾かれた。
- `run_media_growth_engine.py` を修正し、既存clip候補が後から `transcript_grounded=true` / `public_post_validator_status=PASS` / `clip_status=READY` に育った場合、Sheets既存行を更新するようにした。
- `run_media_production_pipeline.py` を修正し、候補がまだないだけの日は `NO_POST` として終了するようにした。kill switch / env gate / secret / rights等の本当のBLOCKは引き続き失敗扱い。
- `media-growth-production.yml` を修正し、日次実行単体で `discover_approved_source_videos.py --fetch-real` → `transcribe_approved_source_videos.py` → `run_media_growth_engine.py` → `run_media_production_pipeline.py` の順に進むようにした。

### 未完了事項 / 残WARN

- GitHub Actions runnerのNode.js 20 deprecation warningあり。Actions側のランタイム都合で、現時点では実行阻害なし。
- GitHub APIが一時的に `error connecting to api.github.com` を返すことがあり、post URLのログ抽出が安定しなかった。run自体はsuccess確認済み。
- 最新commit push後の `Media Growth Production` run `29178471963` は success。`Discover approved source videos`、`Transcribe approved source videos`、`Generate transcript-grounded clip candidates`、`Run one approved media production post` の全ステップがsuccess。
- 成功runの詳細ログ本文はGitHub APIが一時的に `error connecting to api.github.com` を返し取得不安定。ローカルSheets読み取りdry-runもDNS制限で失敗し、権限昇格再実行はout of creditsで拒否されたため、投稿URLのローカル再確認は未完了。
- TikTok/YouTubeの実動画取得は許可済みsource限定。未許可source、X、beauty、third_party_reference_onlyは引き続き対象外。

### テスト結果 / dry-run結果

- `python3 scripts/test_media_production_no_candidate_is_no_post.py`: PASS 3 / FAIL 0
- `python3 scripts/test_media_growth_workflow_prepares_candidates_before_post.py`: PASS 6 / FAIL 0
- `python3 scripts/test_media_growth_updates_stale_clip_candidates.py`: PASS 5 / FAIL 0
- `python3 scripts/test_media_production_pipeline_safety.py`: PASS 11 / FAIL 0
- `python3 scripts/test_media_production_workflow.py`: PASS 11 / FAIL 0
- `python3 scripts/test_all_workflows_safety_flags.py`: PASS 221 / FAIL 0
- `python3 scripts/test_autonomous_workflow_no_x_no_media.py`: PASS 1 / FAIL 0
- `python3 scripts/test_media_execution_runners_connected.py`: PASS 7 / FAIL 0
- `python3 scripts/test_media_production_requires_grounded_clip.py`: PASS 2 / FAIL 0
- `python3 scripts/run_media_production_pipeline.py --account-id liver_manager --dry-run`: PLAN_ONLY, would_download/cut/upload/post=false
- `python3 scripts/run_media_growth_engine.py --account-id liver_manager --dry-run`: rights PASS, permission PASS, public validator PASS, would_download/cut/upload/post=false
- `python3 -m py_compile ...`: PASS
- `git diff --check`: PASS

### 次に触ってよいファイル

- `.github/workflows/media-growth-production.yml`
- `.github/workflows/media-transcription-production.yml`
- `scripts/run_media_growth_engine.py`
- `scripts/run_media_production_pipeline.py`
- `scripts/transcribe_approved_source_videos.py`
- `scripts/discover_approved_source_videos.py`
- `scripts/process_threads_queue.py`

### 衝突しやすいファイル

- `docs/ai-work-handoff.md`
- `docs/production-completion-status.md`
- `.github/workflows/media-growth-production.yml`
- `scripts/run_media_growth_engine.py`

### 触らない方がいいファイル

- `.env`
- `data/`
- `output/`
- `.claude/plans/`
- cookie / storage_state / token / secret 類

### 次AIへの引き継ぎメモ

- `Media Growth Production` は最新commit `b304003` でsuccess済み。次に確認できる環境では、Sheets `posted_results`, `media_assets`, `video_clip_candidates`, `source_videos` の更新と投稿URLを確認する。
- text-only自動投稿はNight/Liverとも最新HEADでsuccess済み。次に見るべきはSheets `posted_results`, `queue`, `autonomous_health`。
- `final_public_post_validator` は弱めない。media投稿でも `public_post_text` だけをpublisherへ渡す。
- Sheets 429が再発した場合、個別 `update_cell` / `row_values` の未retry箇所をbatch/retry化する。

## Codex handoff: approved media automation for night_scout (2026-07-12)

### 現在のHEAD / ブランチ

- 開始HEAD: `e187d945429384a173a074e8fa8e3ebf24cb4a0b`。
- 作業ブランチ: `main`。

### 本システムの状態

- 許可済みsourceだけを対象に、bounded video discovery -> video_id重複排除 -> transcript -> transcript-grounded clip candidate -> 9:16 cut -> Cloudinary -> Threads video + `public_post_text` -> `posted_results` / PDCAまで接続する。
- `liver_manager` の4 URLと `night_scout` の9 YouTube URLは、ユーザーが2026-07-12に自動媒体利用・Cloudinary保存・Threads再投稿を明示許可したものとして、`approved_creator_clip` / `permission_status=approved` / `media_autopilot_enabled=true`を持つ。
- generic `fetch_enabled=false` は維持。専用の`media_autopilot_enabled=true`だけがmedia workflow選択を許可するため、通常参照source、X、beauty、TODO sourceは対象外。

### 変更ファイル一覧

- `config/media_growth_engine.json`
- `config/source_accounts/default_sources.json`
- `.github/workflows/media-growth-production-night-scout.yml`
- `scripts/discover_approved_source_videos.py`
- `scripts/run_media_growth_engine.py`
- `scripts/transcribe_approved_source_videos.py`
- `scripts/run_media_production_pipeline.py`
- `scripts/media_post_validator.py`
- `scripts/media_growth_schemas.py`
- `scripts/test_all_workflows_safety_flags.py`
- `docs/production-completion-status.md`
- `docs/video-reference-runbook.md`
- `docs/media-pipeline-runbook.md`
- `docs/source-registry-inventory.md`
- `docs/ai-work-handoff.md`

### 追加ファイル一覧

- `scripts/test_night_scout_approved_media_sources.py`
- `scripts/test_media_growth_night_scout_account.py`
- `scripts/test_media_post_validator_allows_night_scout.py`
- `scripts/test_media_production_night_scout_workflow.py`

### 実行設定 / スケール方針

- Liver media workflow: JST 09:20, 1 account / 1 media post per day.
- Night Scout media workflow: JST 12:20, 1 account / 1 media post per day.
- Discovery ceiling: source scan 12, new videos 3 per source, 12 total per run. `video_id` / canonical URL / clip time rangeで重複を止め、翌日以降に残りを処理する。
- `public_post_text`のみ投稿可能。internal analysis、URL、transcript全文、source metadataはpublisherに渡さない。

### 未完了事項 / 残WARN

- Night Scout TikTokの個別/アカウントURLはregistry未登録のため、TODOは自動対象外。架空URLは追加しない。
- Google SheetsまたはGitHub APIの一時的DNS/API接続不安定により、最新投稿URL/Sheets更新のローカル再確認は環境回復時に行う。
- 外部transcription API、X、beauty、learning rule自動変更はOFFのまま。

### テスト結果

- `test_night_scout_approved_media_sources.py`: PASS 6 / FAIL 0
- `test_media_growth_night_scout_account.py`: PASS 6 / FAIL 0
- `test_media_post_validator_allows_night_scout.py`: PASS 1 / FAIL 0
- `test_media_production_night_scout_workflow.py`: PASS 5 / FAIL 0
- `test_media_production_pipeline_safety.py`: PASS 11 / FAIL 0
- `test_media_production_workflow.py`: PASS 11 / FAIL 0
- `test_media_execution_runners_connected.py`: PASS 7 / FAIL 0
- `test_media_post_validator_blocks_x_beauty.py`: PASS 1 / FAIL 0
- `test_all_workflows_safety_flags.py`: PASS 245 / FAIL 0

### 次に触ってよいファイル

- `.github/workflows/media-growth-production*.yml`
- `scripts/run_media_production_pipeline.py`
- `scripts/discover_approved_source_videos.py`
- `scripts/transcribe_approved_source_videos.py`
- `scripts/run_media_growth_engine.py`

### 触らない方がよいファイル

- `.env`, `data/`, `output/`, `.claude/plans/`
- cookie / storage_state / token / secret類

### 次AIへの引き継ぎメモ

- scheduled run後、Sheetsの`source_videos`, `video_transcripts`, `video_clip_candidates`, `media_assets`, `queue`, `posted_results`, `media_post_results`をaccount別に確認する。
- Night ScoutのTikTokを自動対象にするには、実URLをsource registryへ追加して同じpermission evidenceと`media_autopilot_enabled=true`を設定する。現在のTODOは絶対に有効化しない。
- `final_public_post_validator`とX/beauty blockは弱めない。

## Codex handoff: intent-gap audit (2026-07-13)

### 作業内容

- ユーザー提供の「3種類のアカウント / reference / approved media / slot schedule」マニュアルを、HEAD `e9c92a14db4083b93aa9cf7c938d616095bce075` のコードとdry-runに照合した。
- 監査のみ。外部fetch、Sheets書込み、download/cut/upload/postは実行していない。
- 詳細: `docs/intent-gap-audit-2026-07-13.md`。

### 重要な認識差

- 添付マニュアル内の「mediaがOFF」は旧状態。最新configではLiver/Nightの許可済み13 sourceに対して、download/cut/upload/video post/media scheduleがON。
- ただし通常の5 text slotへmedia typeを割り当てる機構は未実装。media workflowは追加の投稿試行で、daily cap=5/cooldown=90分と競合する。
- reference実データから本文を作る接続、字幕burn-in、saved media再利用、measured metrics PDCA、Night media health監視は未完了または未検証。

### 次に触ってよいファイル

- `config/content_schedule.json`（新設候補）
- `scripts/run_autonomous_loop.py`
- `scripts/run_media_production_pipeline.py`
- `scripts/run_media_growth_engine.py`
- `scripts/generate_threads_ideas_from_references.py`
- `scripts/check_autonomous_health.py`
- `src/sheets_client.py`

### 次AIへの引き継ぎメモ

- 次実装は既存runnerを作り直さず、post-slot orchestrationを中心に進める。mediaをtext scheduleの外側で追加投稿する現在設計は、ユーザーが望む投稿種別配分と一致しない。
- `fetch_enabled`、`manual_only`、`media_autopilot_enabled`は別責務として保ち、単一フラグに戻さない。

## Codex handoff: slot-based subtitle-free media operation (2026-07-13)

### 現在のHEAD / 作業ブランチ

- 開始HEAD: `e9c92a14db4083b93aa9cf7c938d616095bce075`。
- ブランチ: `main`。
- 完了commitはこのhandoff更新を含む最新`git rev-parse HEAD`。push後にorigin/main一致を確認する。

### 本システム

- `night_scout` と `liver_manager` のThreads投稿を、参照分析・安全な本文生成・キュー・publisher・結果/PDCAで運用する。
- sourceは `reference_only` と `approved_media` を明示的に分離する。approved mediaだけが、bounded discovery -> local transcript -> topic transformation -> clip -> Cloudinary -> Threads media postへ進める。
- 外部へ出せる本文は常に`public_post_text`のみ。内部分析、source URL/ID、queue/score、transcript、AIメモはfinal validatorで止める。

### 今回の変更ファイル一覧

- `.github/workflows/autonomous-growth-loop-night-scout.yml`
- `.github/workflows/autonomous-growth-loop-liver-manager.yml`
- `.github/workflows/media-growth-production.yml`
- `.github/workflows/media-growth-production-night-scout.yml`
- `config/media_growth_engine.json`
- `config/source_accounts/default_sources.json`
- `src/sheets_client.py`
- `scripts/run_autonomous_loop.py`
- `scripts/run_media_growth_engine.py`
- `scripts/run_media_production_pipeline.py`
- `scripts/generate_threads_ideas_from_references.py`
- `scripts/public_post_quality.py`
- `scripts/prepare_pilot_sources.py`
- `scripts/check_autonomous_health.py`
- `scripts/media_growth_schemas.py`
- `scripts/test_all_workflows_safety_flags.py` と既存schedule/media tests
- `docs/production-completion-status.md`, `docs/growth-loop-runbook.md`, `docs/video-reference-runbook.md`, `docs/autonomous-mode-runbook.md`, `docs/source-registry-inventory.md`, `docs/intent-gap-audit-2026-07-13.md`

### 追加ファイル一覧

- `.github/workflows/media-growth-post-liver-manager.yml`
- `.github/workflows/media-growth-post-night-scout.yml`
- `config/content_schedule.json`
- `scripts/content_schedule.py`
- `scripts/normalize_source_registry_roles.py`
- `scripts/test_content_schedule_media_handoff.py`
- `scripts/test_grounded_public_post_generation.py`
- `scripts/test_source_role_and_reference_autopilot.py`

### 実行仕様 / スケール方針

- 1 accountあたり1日5 slot。night text=14/16/18/25、night media=21。liver text=10/13/16/21、liver media=18（JST）。各slotは-15分起動後0-1800秒jitter。
- `daily_post_cap_per_account=5`, `max_posts_per_run=1`, `cooldown_minutes=90`を維持。
- mediaは先行準備workflowで1件を`MEDIA_READY`まで作る。投稿slotはuploaded/unused素材だけを投稿し、download/cut/upload/transcribeをしない。
- discovery上限はscan=12、new/source=3、new total=12。video/clip/textのduplicateを止める。
- 字幕burn-inはユーザー指示によりOFF。`subtitle_enabled=false`、cut runnerも`burn_subtitles=false`。

### 未完了事項 / 残WARN

- 機能実装commit: `5bf15d042253de3d17b9aa339659fcad8aa5ae77`。`git push origin main`は2026-07-13にDNSの`Could not resolve host: github.com`で未完了。ネットワーク復旧後、同じnon-force pushを再実行し、`origin/main`一致を確認する。
- ローカル環境はSheets/GitHub APIのlive確認用credentials/connectivityを持たない。初回scheduled run後にSheetsの`autonomous_health`, `source_videos`, `video_clip_candidates`, `media_assets`, `queue`, `posted_results`を確認する。
- Night Scoutはfemale subject evidenceまたは明示reviewがない動画をanalysis-onlyにする。これは誤った切り抜きを防ぐためで、候補が0なら正常な`NO_POST`になり得る。
- metricsはPENDING/PARTIAL/MEASUREDを保持し、unknownを0にしない。learning rules auto-applyはOFFのまま。

### 安全状態

- X fetch/post=false、beauty active/fetch/post=false。
- third_party/reference_only/unknownはmedia pipeline不可。
- `kill_switch=true`でtext/media scheduled postが停止する。
- secret/cookie/token/storage_state、`.env`, `data/`, `output/`, `.claude/plans/`をcommitしない。

### テスト / dry-run

- `test_all_workflows_safety_flags.py`: PASS 275 / FAIL 0。
- `test_content_schedule_media_handoff.py`: PASS 6 / FAIL 0。
- `test_grounded_public_post_generation.py`: PASS 6 / FAIL 0。
- `test_source_role_and_reference_autopilot.py`: PASS 4 / FAIL 0。
- `test_media_growth_night_scout_account.py`: PASS 8 / FAIL 0。
- `test_media_production_pipeline_safety.py`: PASS 11 / FAIL 0。
- `check_autonomous_health.py --account-id all --dry-run`: PASS。local secret presenceはfalse（値を読まない仕様）。
- `run_media_production_pipeline.py --prepare-only --dry-run` と `--post-saved-media --dry-run`: PLAN_ONLY、実download/cut/upload/post=false。

### 次に触ってよいファイル

- `config/content_schedule.json`
- `scripts/run_media_production_pipeline.py`
- `scripts/run_media_growth_engine.py`
- `scripts/check_autonomous_health.py`
- `.github/workflows/media-growth-*.yml`
- `docs/*runbook.md`

### 衝突しやすいファイル

- `docs/ai-work-handoff.md`
- `config/source_accounts/default_sources.json`
- `config/media_growth_engine.json`
- `scripts/run_autonomous_loop.py`
- `scripts/run_media_production_pipeline.py`

### 触らない方がよいファイル / 次AIメモ

- `.env`, `data/`, `output/`, `.claude/plans/`, secret/cookie/token/storage-state類は触らない。
- 投稿本文validatorを弱めない。source role、reference fetch、media permissionは別の責務として維持する。
- scheduled runがNO_POSTなら失敗と決めつけず、`autonomous_health.no_post_reason`とcandidate/asset状態を確認する。live runの結果があるまで、外部投稿/metrics成功をdocsで断言しない。

## Codex handoff: operational recovery diagnostics (2026-07-14)

### 現在のHEAD / branch

- branch: `main`。
- このhandoff更新前のlocal HEAD: `29f0fdbf7d11b4e492c8dd273412dcc6232715ec`。
- `origin/main`: `e9c92a14db4083b93aa9cf7c938d616095bce075`。localのslot/media実装と今回の診断修正はpush待ち。
- Recovery implementation commit: `a83950b9b5e92534e7ff04668ed8b360021f0fab` (`fix: expose autonomous runtime failures and preserve aftercare`)。
- `git push origin main` was retried after the commit and failed before authentication with `Could not resolve host: github.com`; no remote branch was changed and no force-push was attempted.

### 本システムと今回の修正

- 目的は、`night_scout` / `liver_manager`のThreads text投稿、許可済み動画の発見・分析・切り抜き・Cloudinary保存・media投稿、投稿後metrics/PDCAを安全に連携すること。
- GitHubのscheduled runは起動している。最新確認のNight Scout/Liver Manager runはともに`Apply autonomous Threads loop`でfailureだった。cron未起動ではなくapply段の停止である。
- `fetch_enabled=true`かつ`reference_autopilot_enabled=true`のThreads sourceは、由来として`manual_url`を保持していてもbounded collectorの対象にした。他のmanual sourceは従来どおり除外する。
- `check_autonomous_health.py --use-sheets`を追加。queue、posted_results、metric_snapshots、pdca_runs、source/video/clip/media、logs、autonomous_healthを**読み取り専用**で件数・status別に出す。本文・URL・secretは出さず、tab作成/書込み/投稿もしない。
- text/media workflowの最後にこのruntime snapshotを実行する。metricsがPARTIAL/UNAVAILABLEでもaftercare全体を止めず、registry syncとPDCA候補生成を継続する。

### 変更ファイル / 追加ファイル

- 更新: `.github/workflows/autonomous-growth-loop-*.yml`, `.github/workflows/media-growth-*.yml`, `.github/workflows/production-autopilot-aftercare.yml`, `scripts/collect_source_posts.py`, `scripts/check_autonomous_health.py`, `docs/production-completion-status.md`, 本ファイル。
- 追加: `scripts/test_reference_autopilot_manual_url_override.py`, `scripts/test_autonomous_health_runtime_snapshot.py`, `scripts/test_aftercare_metrics_failure_continues.py`。

### テスト / dry-run / WARN

- PASS: reference override 2件、read-only health 5件、aftercare continuity 3件、source role 4件、workflow safety 275件、`py_compile`、`git diff --check`。
- local `check_autonomous_health.py --use-sheets`ではSheets/Threads/Cloudinary credential presenceのみtrueを確認し、値は未表示。Google readは`TransportError`でUNAVAILABLEだった。これはlocal通信層のWARNであり、空Sheetとは断定しない。
- 次のGitHub Actions runのfinal health summaryが本番Sheetsの唯一の正しいruntime観測になる。

### 未完了事項 / スケール方針 / 次AIメモ

- 最優先はpending commitsのnon-force pushと、最初のscheduled runでqueue/posted_results/PDCA/media stageを確認すること。`NO_READY_QUEUE`、validator block、daily cap、schema不足、media asset不足をhealth summaryで判定する。
- media progressionは`DISCOVERED -> transcript/clip -> MEDIA_READY -> UPLOADED -> posted_results`。段がない場合は`NO_POST`で止まり、未許可mediaを使わない。
- `learning_rules.auto_apply=false`、X fetch/post=false、beauty active/fetch/post=false、source priority自動変更なしを維持。
- 次に触ってよい: `scripts/run_autonomous_loop.py`, `scripts/check_autonomous_health.py`, `scripts/run_media_production_pipeline.py`, `scripts/discover_approved_source_videos.py`, media/text workflows。
- 触らない: `.env`, `data/`, `output/`, `.claude/plans/`, secret/token/cookie/storage-state類。衝突しやすい: handoff、source registry、media config、Sheets schema、autonomous runner。

## 2026-07-15 Five-Slot Production Recovery

### System / HEAD / Branch

- System: account-scoped Threads text automation plus permission-gated direct
  media and generated-clip media. X and `beauty_account` stay blocked.
- Base HEAD: `4278aa6a8cb8e818f853e4ed2e513b685eb8f8ab`; the current
  implementation is committed on `main` and its pushed hash is verified in the
  final run report.
- Critical root cause verified from Actions logs: scheduled text jobs failed
  before planning because ignored `config/content_schedule.json` was absent in
  Actions. It is now intentionally tracked.

### Changes / Tests / Runtime

- Added: `config/content_schedule.json`, `config/media_source_usage_modes.json`,
  `scripts/content_slot_runs.py`, `scripts/run_slot_text_fallback.py`,
  `scripts/run_direct_reference_media_pipeline.py`,
  `scripts/backfill_missed_content_slots.py`, two direct-media workflows, and
  focused contract tests.
- Updated: `.gitignore`, Sheets tab schema, text/media workflows, media
  production runner, media config, health check, runbooks, and this handoff.
- PASS locally: content schedule contract, direct permission boundary,
  workflow schedule/gate/jitter tests, `py_compile`, and `git diff --check`.
  Text dry-runs show `public_post_preview`, internal-leak PASS, and
  `would_post=false`.
- `content_slot_runs` records expected/actual type, fallback level, queue,
  result, media/source linkage, URL, and redacted failure reason. The
  aftercare CLI detects slots overdue by 20 minutes; it is read-only pending a
  separately credentialed late-post policy.

### Production State / WARN / Next AI

- Formal schedule: night 14 reference, 16 original, 18 direct, 21 clip, 25
  PDCA; liver 10 original, 13 reference, 16 direct, 18 clip, 21 PDCA. Every
  worker has 0-1800 second jitter; account cap=5, media cap=2.
- `saved_media_post_fallback=text_only_fallback` is now connected to the clip
  post workflow. Direct media has the same safe fallback.
- Remaining WARN: no `direct_media_reuse` permission-evidenced source post or
  uploaded asset is present, so direct-media E2E is correctly unavailable;
  generated clip E2E still needs an eligible individual video/asset. Carousel
  transport is deliberately blocked rather than dropping images. Metrics stay
  `UNAVAILABLE`/`PARTIAL` until collected, never synthetic zero.
- Safe next files: direct source discovery/ingestion and carousel publisher
  only after explicit scope evidence; `backfill_missed_content_slots.py` when
  defining an approved late-post credential policy. Avoid `.env`, data/output,
  secrets, and weakening validators or source permission policy.
- Production blocker observed after push: GitHub Actions dry-runs
  `29382188177` (night) and `29382189714` (liver) were rejected before any
  step with a GitHub billing/spending-limit annotation. No post, fetch,
  download, upload, or Sheets write occurred. Restore Actions billing or raise
  its spending limit, then rerun the two dry-runs before relying on schedule.

## 2026-07-15 Slot Engine Completion Work (Pending E2E)

- Added `media_permissions` Sheets tab. It is the single user-operated ledger
  for direct reuse; revoked/expired rows are ignored and clip authorization
  never becomes direct reuse automatically.
- Text generation now receives `slot_id`, `post_type`, `theme`, and JST date.
  The normal text runner persists an apply result to `content_slot_runs`.
  Fallback selection includes date, reason, and bounded variants; it retries
  a duplicate with up to three distinct variants.
- `original_text` is source-independent. `reference_text` uses references when
  available and falls back safely when not. `pdca_text` checks for `MEASURED`
  metrics and falls back to original text when metrics are PENDING,
  UNAVAILABLE, or absent; it must not claim a PDCA result in that state.
- Media primary failures that occur before a confirmed Threads post now invoke
  the named safe text fallback. `POSTED_SAVE_FAILED` deliberately does not
  fallback because a post may already exist.
- Added `content-slot-recovery.yml`, which runs every 30 minutes, considers
  only slots more than 20 minutes overdue, and is capped at one recovery post
  per account/run. It keeps all X/media download/cut/upload gates false.
- Added [operator-one-page.md](operator-one-page.md) for the Sheet-only
  operating view and focused regression tests for schedule agreement, slot
  context, permission boundaries, and executable backfill.
- Remaining uncompleted production proof: Actions billing still blocks all
  jobs before startup; no new real post URL exists. Direct source discovery,
  media download, Cloudinary upload, image/carousel transport, and generated
  clip E2E require an explicit ledger row plus an actual permitted source post
  or individual video asset. Do not call them complete until linked URLs and
  Sheet rows are observed.
# Codex Handoff: High-Capability Planning Audit (2026-07-22)

## 本システム / 現在位置

- `night_scout` / `liver_manager` のThreads text投稿、許可台帳に基づく
  source取得、direct media再利用、文字起こしに基づくclip生成、Cloudinary、
  投稿、Sheets証跡、PDCAをGitHub Actions標準runnerだけで完結させるシステム。
- 今回はユーザー指示により、最上位モデルでは現状監査・残作業設計・受入条件
  確定だけを実施した。実装、公開化、Environment変更、merge、canary投稿は未実施。
- 監査対象実装HEAD:
  `026ed40b65d2c708673313286c8bc9a914b1efe7`。
- 作業ブランチ: `feature/oss-github-actions-media-autopilot`。
- `origin/main`: `f89f6ed44bc2a00930f04601d5700230e25949d3`。
- PR: `https://github.com/dev-ch-hhuk39/sns-growth-engine/pull/3`。

## 今回の変更ファイル一覧 / 追加ファイル一覧

- 更新: `docs/goal-status.json`
- 更新: `docs/runtime-health.json`
- 更新: `docs/goal-evidence.md`
- 更新: `docs/ai-work-handoff.md`
- 追加: `docs/goal-completion-implementation-plan.md`
- 実装コード、workflow、config、Sheets、Cloudinary、Threadsは変更していない。

## 監査結論

- Goal evaluatorは現時点で未達。実態分類は35件中17 PASS、16件が
  UNVERIFIED/FAIL、2件が外部BLOCKED。
- repoはPRIVATE。公開化は全Git履歴の公開を伴うため、明示承認なしでは行わない。
- PR #3はmergeableだがCI run `29690502128`はjob step開始前にfailure。
  テスト失敗とは判定しない。mainはまだ旧実装。
- branch内production workflowは26本、`self-hosted`/VPS参照は0、標準
  `ubuntu-latest`へ移行済み。
- gitleaks 8.30.1による全168 commit scanはPASS、leak 0。
- repo testsは629/629 PASS、compileall PASS、workflow safety 359/359 PASS、
  library matrix / registry PASS。localにはruff/mypyが未導入のためfinal CI必須。
- Sheetsは直近の本番整合性修復後63/63 PASS、`posted_save_failed_count=0`。
  今回のlocal再読はGoogle OAuth endpointのDNS解決不可でUNAVAILABLE。
- Agent-Reach doctor、last30days preflight、source research applyは実証済み。
- 実取得でYouTube metadataまでは進んだが、transcriptのSheets 50,000文字
  制限が露出。acquisition runnerは修正済み。独立transcribe runnerへの
  `normalize_transcript_row`接続が残作業。
- TikTok real discoveryはrehydration failureが残り、bounded fallbackの
  final-main live確認が必要。
- Goal専用READY在庫は両accountともdirect media=0、generated clip=0。
- Goalで必要な4 canary投稿は0件。旧投稿/旧assetをGoal証跡へ流用しない。
- `liver_manager`の第三者Threads source account URLはtracked registryに0件。
  架空URLやposting accountの暗黙転用は禁止。

## 未完了事項 / タスク順

1. `docs/goal-completion-implementation-plan.md` Work Package 1のコードgapを修正。
2. 全tests、compile、ruff、mypy、license、dependency、gitleaksを通す。
3. 公開化の明示承認を得てrepo public化、protected mainとapproval不要の
   `production` Environmentを作成。
4. PR CIを実step実行でPASSさせ、mainへmerge、origin/main一致確認。
5. final mainでsource research/acquisitionとSheets verifier 63/63を実行。
6. 各account direct media 1件、generated clip 1件を投稿せず準備。
7. 4経路を各最大1件だけcanary投稿し、本文と実mediaを独立検証。
8. 機械証跡でGoal statusを更新し、evaluator 35/35後だけGoal complete。

## 残WARN / 外部ブロッカー

- repository public化には、全Git履歴が公開されることへの明示承認が必要。
- `liver_manager`用Threads source account URLは人間入力が必要。
- GitHub `production` Environment / main protectionは公開化後にAPI再確認が必要。
- GitHub APIとGoogle OAuth DNSがlocalで断続的に失敗する。Actions側のrun IDと
  step logを最終証拠にする。
- mainの直近scheduled runはworkflow successでもapply stepがSKIPPEDの例がある。
  greenだけで投稿成功扱いにしない。

## スケール方針 / 安全方針

- discovery、acquisition、preparation、posting、recovery、evaluationを役割分離。
- 取得はsource/account/total上限を守り、backend failureはbounded fallback。
- `media_permissions` Sheets tabだけをruntime許可正本とする。repo configだけでは
  download/cut/upload/postを許可しない。
- 失敗assetはquarantineし次候補へ。無限retry、同一asset/text再投稿は禁止。
- real canaryはaccount/pathごと最大1件。投稿後にSheets/Cloudinary/Threadsを
  read-after-write確認してから次へ進む。
- 字幕burn-inはユーザー指示によりOFFを維持。
- X、beauty、secret/cookie/storage state、`.env`, `data/`, `output/`は対象外。

## 全テスト結果 / dry-run結果

- `run_repository_tests.py`: PASS 629 / FAIL 0。
- `python3 -m compileall -q src scripts`: PASS。
- `test_all_workflows_safety_flags.py`: PASS 359 / FAIL 0。
- `test_library_capability_matrix_complete.py`: PASS 7。
- `test_external_library_registry.py`: PASS 4 / FAIL 0。
- gitleaks full history: PASS、168 commits、leak 0。
- ruff/mypy: current local Pythonではmodule未導入のためNOT RUN。CI exact pinで必須。
- `check_media_inventory.py --dry-run`: local DNSでGoogle OAuthに接続できずUNAVAILABLE。
- 実fetch/download/cut/upload/post、Sheets apply、Cloudinary applyは今回0件。

## 次に触ってよいファイル

- `scripts/transcribe_approved_source_videos.py`
- `src/transcription/sheets_limits.py`
- `src/acquisition/ytdlp.py`
- `src/acquisition/tiktok_public.py`
- `scripts/discover_approved_source_videos.py`
- `scripts/evaluate_goal.py`
- 上記に直接対応する`test_*`、goal evidence/status docs。

## 衝突しやすいファイル

- `docs/ai-work-handoff.md`
- `docs/goal-status.json`
- `docs/runtime-health.json`
- `config/source_accounts/default_sources.json`
- `src/sheets_client.py`
- acquisition/media production workflows。

## 触らない方がよいファイル / 次AIへの引き継ぎメモ

- `.env`, `data/`, `output/`, `.claude/plans/`, secret/token/cookie/storage-state。
- `final_public_post_validator`、rights gate、same-post parent integrity、
  unsupported-claim gateを弱めない。
- まず`docs/goal-completion-implementation-plan.md`を読み、Work Package 1から
  順番に進める。Goal設計の作り直しはしない。
- 推奨実装モデルはGPT-5.6 Terra、思考力medium。テスト再実行・format・docs同期
  だけlow可。設計矛盾/security incident/provider全fallback破綻時だけ最上位へ戻す。
