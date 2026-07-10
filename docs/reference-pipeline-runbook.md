# Reference Pipeline Runbook

Date: 2026-06-27

ネタ収集・参考素材収集・動画文字起こし・切り抜き候補・投稿案生成の標準 CLI 運用手順。

## 方針: 既存流用 + 薄い入口

ユーザーから見える標準 CLI 名は下表に統一する。各 CLI は薄いエントリーポイントで、
内部では既存スクリプトのロジックを再利用する（重複実装はしない）。
`score_reference_posts` のみ genuinely-new な質的ルーブリックを追加実装している。

| 標準 CLI | 内部委譲（既存） | 役割 |
|---|---|---|
| `collect_reference_posts.py` | `collect_source_account_posts.py` | 参考投稿のメタ収集（参考のみ） |
| `import_reference_urls.py` | `add_source_candidate.py` | 参考 URL を source registry に登録 |
| `score_reference_posts.py` | （新規ルーブリック）+ `analyze_references.py` 補完 | 質的採点（内容適合） |
| `prepare_video_reference.py` | `plan_video_reference_posts.py` | 動画メタ + 切り抜き候補プラン |
| `transcribe_video_reference.py` | `transcribe_videos.py` | 文字起こし |
| `generate_clip_candidates.py` | `analyze_video_clips.py` | 切り抜き候補生成 |
| `generate_threads_ideas_from_references.py` | `generate_from_references.py` / `generate_from_video_clips.py` | Threads 投稿案生成 |

## 共通の安全設計

- 全 CLI は既定でドライラン（`PLAN_ONLY`）。委譲先の実処理は `--apply` かつ各 `--confirm-*` の二重指定が必要。
- `build_plan()` は純粋関数で、委譲コマンド（delegate_script / delegate_argv）と安全フラグ（safety）を返す。
  テストは委譲先を実行せずに `build_plan()` の出力だけを検証する。
- `beauty_account` は全 CLI で対象外（draft_only）。
- 投稿先は `threads` のみ。X は将来対応のみで本パイプラインからは生成・投稿しない。
- 第三者メディアは参考分析・メタ・文字起こし・切り抜き候補化まで。download / ffmpeg cut / Cloudinary upload はしない。
- 生成投稿案は `WAITING_REVIEW`（metrics 由来は `DRAFT`）で書き込まれる。worker の `ELIGIBLE_STATUSES`={READY} には含まれないため、**生成しただけでは worker の投稿対象にならない**。投稿対象になるのは `approve_queue.py` で人間承認された行、または `auto_approve_queue.py` でAUTO_READY条件を通過した行のみ。多層防御:
  1. 生成 CLI も委譲先も投稿処理を一切呼ばない（生成専用）。生成系は `READY` を直接書かない。
  2. worker は `READY` のみ拾う。`WAITING_REVIEW` / `DRAFT` / `PLANNED` は投稿対象外（項目ごとのREADY昇格ゲート）。
  3. READY昇格は人間承認の `approve_queue.py` または安全条件付きの `auto_approve_queue.py` のみ。
  4. 実投稿は別経路 worker の三重ゲート（`--confirm-real-post` かつ `PUBLISH_ENABLED=true` かつ `ALLOW_REAL_THREADS_POST=true`）が必要。scheduled applyではworkflow apply step内だけ true になり、dry-run/通常ローカルでは false。
  5. `beauty_account` / X は本パイプラインで BLOCKED。
- 承認モデル: Threads worker は `READY` 必須。READYゲートは `approve_queue.py`（人間）と `auto_approve_queue.py`（AUTO_READY）の2系統。状態遷移: `WAITING_REVIEW → READY → PROCESSING → POSTED`。AUTO_READYで落ちた場合は `rejected_reason` / `health_summary.no_post_reason` / `autonomous_health` を確認する。

## 1. 参考投稿の収集

```bash
# 計画のみ（既定・書き込みなし）
python3 scripts/collect_reference_posts.py --account-id night_scout --source-platform threads --source-handle <handle>
# 本番収集（Sheets 書き込み）
python3 scripts/collect_reference_posts.py --account-id night_scout --source-platform threads --source-handle <handle> --apply --confirm-collect
```

- 収集対象は参考メタのみ（`use_status=REFERENCE_ONLY`）。実 X API は起動しない。
- 書き込み先タブ: `source_account_posts`（`post_url` で重複検知 / `rights_status` / `can_reuse_media`）。

### Threads public source collection (v2 real adapter)

`scripts/collect_source_posts.py` は、Threads公開投稿URLからOG metadataを取得して `source_account_posts` 形式の行を計画できる。

```bash
python3 scripts/collect_source_posts.py --platform threads --account-id all --dry-run \
  --source-url "https://www.threads.com/@ran.liver_pro/post/DaMbCLQiXLs" \
  --source-url "https://www.threads.com/@kyaba_consul_mizu/post/DaNToTqgQ7i" \
  --fetch-real
```

- 本番source registryでは `fetch_enabled=true` が0件のため、標準dry-runは `selected_count=0` が正常。
- 小さく試す場合は `--source-url` か、レビュー済みsourceを1〜2件だけ `fetch_enabled=true` にする。大量ONは禁止。
- Xは既定OFF。`manual_only=true` のX sourceはこの工程ではfetchしない。
- raw payloadはtoken/cookie/secret系キーをredactしたうえでplanに含める。第三者media本体はdownloadしない。
- 保存先は `source_account_posts`。`post_url` 重複はdry-run/applyともskipする。

### Dependency adapters (2026-06-30)

- `beautifulsoup4` / `lxml`: `collect_source_posts.py` のOG metadata parserへ接続済み。未インストール時はregex fallback。
- `requests`: 既存HTTPクライアントで利用済み。
- `tweepy`: requirementsにはあるが、source collectionではX fetch skeletonのみ。X fetchは既定OFF。
- Agent Reach / CLI-Anything / last30days-skill: optional external signal扱い。SNS本文生成には使わない。
- Threads Scraper系 / twikit / snscrape / TikTokApi: 非公式/安定性/ToSリスクのため、このphaseでは未導入。

詳細な installed/imported/wired/tested 状態は [dependency-inventory.md](dependency-inventory.md) を参照。

## 2. 参考 URL の登録

```bash
python3 scripts/import_reference_urls.py --source-id <id> --platform youtube --url <url> --target-account liver_manager
# 本番登録
python3 scripts/import_reference_urls.py --source-id <id> --platform youtube --url <url> --target-account liver_manager --apply --confirm-import
```

- 登録のみ。download / scraping はしない。`rights_status` 既定 unknown → 許諾未確認は WAITING_REVIEW。

## 3. 質的採点（genuinely new）

```bash
# オフライン採点（テスト/検証用）
python3 scripts/score_reference_posts.py --account-id night_scout --input-json sample.json
# 本番採点（source_account_posts を読んで reference_post_scores に書き込み）
python3 scripts/score_reference_posts.py --account-id night_scout --apply --confirm-score
```

ルーブリック（各 0〜5）:

- `hook_score` 冒頭フックの強さ / `insight_score` 悩み解決・気づきの深さ / `cta_score` LINE・DM 導線の自然さ
- `originality_score` 独自性 / `reuse_risk_score` 流用リスク（高いほど危険）
- `total_score` 加重合算（reuse_risk は減点）
- `recommended_use`: 流用リスク高 / 権利未確認 / 流用不可 は必ず `REFERENCE_ONLY`、それ以外は `IDEA_SEED`

アカウント別の刺さる文脈・CTA 語彙は `RUBRICS`（night_scout / liver_manager）で定義。

## 4. 動画参考の準備

```bash
python3 scripts/prepare_video_reference.py --account-id liver_manager --platform threads --source-platform youtube --video-url <url>
```

- 既定はメタ + 切り抜き候補プランのみ。download は `--allow-download` かつ `--confirm-download` の二重ゲート（既定 false）。

## 5. 文字起こし

```bash
python3 scripts/transcribe_video_reference.py --account-id liver_manager --limit 5
# 実 API 文字起こし（env と CLI の二重ゲート）
ALLOW_TRANSCRIPTION_API=true python3 scripts/transcribe_video_reference.py --account-id liver_manager --apply --confirm-transcribe --allow-real-transcription
```

- 実 API は `ALLOW_TRANSCRIPTION_API=true`（env）かつ `--allow-real-transcription` の両方が必要。既定はモック。

## 6. 切り抜き候補生成

```bash
python3 scripts/generate_clip_candidates.py --account-id liver_manager --limit 5 --n-candidates 6
# 本番候補書き込み
python3 scripts/generate_clip_candidates.py --account-id liver_manager --apply --confirm-generate
```

- 候補化のみ。`--cut` は本 CLI では BLOCKED（ffmpeg 実切り抜きはしない）。

## 7. Threads 投稿案生成

```bash
# 参考投稿から
python3 scripts/generate_threads_ideas_from_references.py --account-id night_scout --platform threads --source references
# 切り抜きから
python3 scripts/generate_threads_ideas_from_references.py --account-id night_scout --platform threads --source clips
# 本番生成
python3 scripts/generate_threads_ideas_from_references.py --account-id night_scout --source references --apply --confirm-generate
```

- 投稿案は `WAITING_REVIEW` で書き込まれる（本 CLI は生成専用で投稿しない）。worker は `READY` のみ拾うため `WAITING_REVIEW` のままでは投稿対象外。READY昇格は `approve_queue.py` の人間承認、または `auto_approve_queue.py` のAUTO_READYで行う。詳細は「共通の安全設計」を参照。

## GitHub Actions（dry-run）

- `content-daily-dry-run.yml`: collect / score / ideas の PLAN_ONLY サニティを毎日実行。
- `video-reference-dry-run.yml`（新規）: prepare / transcribe / clip / ideas(clips) の PLAN_ONLY サニティを週次実行。
- `source-fetch-dry-run.yml`: source registry 取得の dry-run（既存）。
- いずれも実投稿系フラグは `false` 既定。
- 全ワークフロー横断の安全回帰は `test_all_workflows_safety_flags.py` が固定する:
  workflow/job スコープ env のフラグは必ず `false`、`true` 化と `--confirm-real-post`
  等の実アクションは step の confirm ゲート（`if:` か bash `$CONFIRM_*`）必須、
  `schedule` 実行のワークフローは実アクションを一切持たない、を全 8 本に対して検査する。

## 生成姿勢マトリクス（既知の論点・誤検知防止のため明記）

「生成された投稿候補は自動投稿対象にしない」という不変条件は、**worker の `READY` 必須化（第一防御）＋ 多層防御**で担保している。
worker の `ELIGIBLE_STATUSES`={READY} のため、いずれの生成経路も書込み直後は worker の投稿対象にならない。
各生成経路が候補をどの status / generation_mode で書くかは設計上意図的に異なる。

| 経路 | スクリプト | 書込先 | status | generation_mode | worker eligible | verify |
|---|---|---|---|---|---|---|
| metrics | `generate_next_queue_from_metrics.py` | queue | `DRAFT` | `metrics_driven_candidate` | いいえ（READY のみ eligible） | `metrics_candidates_not_postable` が DRAFT 以外を検知 |
| refill | `scripts/refill_threads_queue.py` | queue | `WAITING_REVIEW` | `refill_seed` | いいえ（READY のみ eligible） | `generated_candidates_not_ready_by_default`（承認証跡なし READY を検知） |
| clip | `generate_from_video_clips.py` | queue | `WAITING_REVIEW` | `video_clip_reference` | いいえ（READY のみ eligible） | 同上 |
| seed/recovery | `recover_production_sheets_threads_first.py` | queue | `WAITING_REVIEW` | `manual_seed` / `threads_first_manual_seed` | いいえ（READY のみ eligible） | 同上 |
| reference | `scripts/generate_from_references.py` | JSON `--output` のみ | —（queue 非汚染） | `reference_based_text` 他 | — | 対象外（queue に書かない） |

- 第一防御は worker の `READY` 必須化。生成系は `READY` を直接書かず、`approve_queue.py` の人間承認、または `auto_approve_queue.py` のAUTO_READY条件通過で昇格した行だけが投稿対象になる。
- 加えて、実投稿は worker の三重ゲート（`--confirm-real-post` かつ
  `PUBLISH_ENABLED=true` かつ `ALLOW_REAL_THREADS_POST=true`・現状全禁止）が必要。
- verify は「metrics 由来候補は DRAFT に留まる」（`metrics_candidates_not_postable`）に加え、
  「生成候補が承認証跡なしに `READY` になっていない」（`generated_candidates_not_ready_by_default`・logs の `queue_approved` 証跡で承認済みを除外）を検査する。
  この境界は `test_recover_verify_media_metrics_checks.py` と `test_recover_verify_ready_checks.py` で回帰固定している。

### 承認モデル（X / Threads 対称）

- Threads worker の `ELIGIBLE_STATUSES`={READY}。`WAITING_REVIEW` は直接拾わない。
  `approve_queue.py`（人間承認）と `auto_approve_queue.py`（AUTO_READY）が「項目ごとの READY 昇格ゲート」を担う。
- X 側の `publish_queue.py` も `--status READY` 必須。X と Threads の承認モデルは対称（旧「非対称の潜在課題」は解消済み）。
- 状態遷移: `WAITING_REVIEW → READY → PROCESSING → POSTED`。

## verify（recover_production_sheets_threads_first.py）

`verify_state` に参考パイプラインの安全不変条件を追加:

- `reference_posts_use_status_safe`: 参考投稿に投稿可ステータスを持たせない
- `reference_posts_reuse_rights_safe`: 流用可は許諾明示時のみ
- `reference_scores_high_risk_reference_only`: 流用リスク高は REFERENCE_ONLY 推奨
- `reference_scores_not_postable`: 採点行は投稿可ステータスを持たない
- `metrics_candidates_not_postable`: metrics 由来候補（`metrics_driven_candidate`）は DRAFT に留まり worker 非対象
  （refill / clip / seed の WAITING_REVIEW は誤検知しない・上記姿勢マトリクス参照）

READY 承認モデルの安全チェック（worker eligible=READY を回帰固定）:

- `waiting_review_not_postable`: `WAITING_REVIEW` は投稿対象に含めない
- `ready_is_only_postable_status`: 投稿対象は `READY` のみ
- `planned_not_postable_or_documented`: `PLANNED` は投稿対象外
- `generated_candidates_not_ready_by_default`: 生成候補は承認証跡（logs `queue_approved`）なしに `READY` にならない
- `approve_queue_required_for_ready`: `READY` 昇格は `approve_queue.py` または `auto_approve_queue.py` 経由のみ
- `no_ready_for_x_or_beauty`: `platform=x` / `beauty_account` の `READY` を作らない
- `no_media_required_without_media_url` / `no_unapproved_media_ready` / `no_reference_only_media_ready`: `READY` の media 権利・承認チェック（`media_url` / `media_asset_id` 双方で連携）
- `real_post_flags_false_default`: 実投稿フラグは既定 false

## テスト

```bash
python3 scripts/test_score_reference_posts.py
python3 scripts/test_collect_reference_posts.py
python3 scripts/test_import_reference_urls.py
python3 scripts/test_prepare_video_reference.py
python3 scripts/test_transcribe_video_reference.py
python3 scripts/test_generate_clip_candidates.py
python3 scripts/test_generate_threads_ideas_from_references.py
python3 scripts/test_recover_verify_media_metrics_checks.py
python3 scripts/test_all_workflows_safety_flags.py
```

## 2026-06-30 初回reference loop

本番Sheets上で、外部fetchなしの manual reference loop が通っている。

1. Source registryから `source_account_posts` へ `manualref_` 10件をseed。
2. `score_reference_posts.py` で `reference_post_scores` 10件を作成。
3. `generate_threads_ideas_from_references.py` で `WAITING_REVIEW` のThreads候補を6件作成。
4. `process_threads_queue.py --dry-run --max-posts 2` は `candidates=0`。`WAITING_REVIEW` はworker非対象。
5. `approve_queue.py --dry-run --use-sheets` で1件だけREADYにする計画を確認。実READY昇格はしていない。

追加テスト:

```bash
python3 scripts/test_seed_reference_posts_from_sources.py
python3 scripts/test_reference_posts_generated_without_fetch.py
python3 scripts/test_reference_post_scores_generated.py
python3 scripts/test_threads_ideas_waiting_review_only.py
python3 scripts/test_waiting_review_not_worker_selectable.py
python3 scripts/test_ready_only_worker_after_source_loop.py
python3 scripts/test_pdca_dry_run_safe_without_posted_results.py
python3 scripts/test_no_real_fetch_in_production_loop.py
python3 scripts/test_no_beauty_active_in_production_loop.py
python3 scripts/test_no_fetch_enabled_added.py
```

## AUTO_READY接続 (2026-06-30)

Reference pipelineで生成された `WAITING_REVIEW` は、条件を満たす場合だけ `auto_approve_queue.py` が `READY` に昇格できる。

```bash
python3 scripts/auto_approve_queue.py --dry-run --account-id all --max-ready 2 --use-sheets
python3 scripts/auto_approve_queue.py --apply --confirm-auto-ready --account-id all --max-ready 2 --use-sheets
```

AUTO_READY条件:

- account: `night_scout` / `liver_manager`
- platform: `threads`
- status: `WAITING_REVIEW`
- mediaなし、third-party素材なし
- `quality_score >= 75`, `safety_score >= 90`, `risk_score <= 10`
- duplicate / near_duplicate ではない
- `daily_ready_cap=2`, `cooldown_minutes=180`, `max_posts_per_run=1`
- `kill_switch=false`

AUTO_READY後も実投稿はしない。workerは `READY` のみをdry-run/実投稿対象として検出する。

## Post-first-run metrics and PDCA path (2026-06-30)

初回Threads実投稿後のreference pipeline状態:

- `posted_results` に `liver_manager` の本番Threads投稿1件を保存済み。
- result_id: `threads_q_liver_manager_manualref_src_lm_note_cand_001_threads_20260630025810`
- metricsは未測定のため `metrics_status=PENDING`。

安全なmetrics dry-run:

```bash
python3 scripts/import_threads_metrics_manual.py \
  --result-id threads_q_liver_manager_manualref_src_lm_note_cand_001_threads_20260630025810 \
  --views 0 \
  --likes 0 \
  --comments 0 \
  --follows 0 \
  --profile-clicks 0 \
  --line-adds 0 \
  --memo "first post metrics dry-run template" \
  --dry-run
```

安全なPDCA dry-run:

```bash
python3 scripts/generate_next_queue_from_metrics.py --dry-run --account-id liver_manager
```

現在はMEASURED metricsがないため `candidate_count=0`。PDCA候補生成をapplyするのは、実測値を人間が確認し、metricsを保存してから。

Media / video pilot:

- `plan_media_mix.py --dry-run --account-id all --use-sheets`: `media_candidate_count=0`
- `generate_video_reference_posts.py --dry-run --account-id all`: 6件の `WAITING_REVIEW` planのみ
- video referenceは構成参考だけ。download/cut/upload/transcription/repostなし。

## Metrics-driven PDCA candidate behavior (2026-06-30)

metrics import後のPDCAは、`metrics_status=MEASURED` の `posted_results` のみを根拠にする。

- `PENDING` metricsは候補生成に使わない。
- 値なしmetrics dry-runでは `MEASURED` にしない。
- 本番値が取れない場合、0を入れるなら「人間が0または不明を0扱いと明示判断した」場合だけ。
- offline test/sample MEASUREDでは `candidate_count=1` を確認済み。
- 本番applyで生成するqueueは `DRAFT`。`READY` にはせず、AUTO_READYまたは人間reviewを別工程にする。

本番Sheets apply例:

```bash
python3 scripts/generate_next_queue_from_metrics.py \
  --account-id liver_manager \
  --dry-run \
  --use-sheets

python3 scripts/generate_next_queue_from_metrics.py \
  --account-id liver_manager \
  --apply \
  --confirm-generate \
  --use-sheets
```

このturnではSheets承認が拒否されたため、本番PDCA applyは未実行。

## Production PDCA status after second account post (2026-06-30)

`night_scout` 投稿後も、metricsがまだ `PENDING` のため本番PDCA applyは未実行。

- `liver_manager` metrics: `PENDING`
- `night_scout` metrics: `PENDING`
- `generate_next_queue_from_metrics.py --account-id liver_manager --dry-run --use-sheets`: `measured_count=0`, `candidate_count=0`
- `run_autopilot_loop.py --dry-run --account-id all --auto-ready --skip-real-post --use-sheets`: `auto_post_gate.allowed=false`

本番PDCAを進める条件:

- Threads Insights等で実測値を取得。
- `import_threads_metrics_manual.py --apply --confirm-metrics` でMEASURED化。
- `generate_next_queue_from_metrics.py --dry-run --use-sheets` で `candidate_count>0` を確認。
- applyしても生成queueは `DRAFT` のまま。READY昇格は別工程。

## v2 Source Collection

`collect_source_posts.py` plans reference collection across Threads/X/YouTube/TikTok.

```bash
python3 scripts/collect_source_posts.py --platform all --account-id all --dry-run
```

Rules:

- Only `fetch_enabled=true` sources are eligible.
- `manual_only=true` and manual collection methods are skipped.
- X is disabled unless explicitly requested with `--include-x`.
- Third-party media is not downloaded.
- Raw JSON must be sanitized before archive; no cookies/tokens/secrets.

## Rights and Rewrite Guard (2026-07-01)

- X/Threads media discovered during source collection is stored as URL/thumbnail metadata only.
- Collected X/Threads media rows are `rights_status=third_party_reference_only`, `can_reuse_media=false`, `media_download=false`, and `media_body_saved=false`.
- Reference posts can influence structure, hook, and topic. They must not be lightly rewritten into a post.
- `generate_threads_ideas_from_references.py` includes a similarity/direct-copy guard. High-similarity drafts are `BLOCKED`; valid transformed drafts remain `WAITING_REVIEW`, never `READY`.

## Source Registry Inventory (2026-07-01)

- Threads references: registered in `default_sources.json`; `fetch_enabled=false` until a small reviewed dry-run set is enabled.
- X references: registered, manual/reference-only, and X fetch remains disabled by default.
- YouTube references: channel/account sources are registered; individual clip target URLs for `night_scout` and `liver_manager` are placeholders until a human provides real URLs.
- TikTok references: `beauty_account` account references exist but beauty remains inactive/draft-only; `night_scout` and `liver_manager` TikTok video references are placeholders.
- See `docs/source-registry-inventory.md` for per-source status and TODO rows.

## External Signal Tools

- Agent Reach: optional external signal/source discovery/shortlist enrichment. Not production runtime enabled, and not used to generate post body text directly.
- last30days-skill: optional trend/source discovery signal. External skill runtime, query schema, and rate limits need human approval before use.
- tiktok-to-ytdlp: optional TikTok URL helper. Individual TikTok `/video/` URLs are preferred for first dry-runs.
- `yt-dlp` and `youtube-transcript-api` are the current wired video metadata/transcript paths, with third-party download prohibited.
