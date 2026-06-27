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
- 生成投稿案は `DRAFT`（worker の `ELIGIBLE_STATUSES`={WAITING_REVIEW, PLANNED} に含めない）。自動投稿されない。

## 1. 参考投稿の収集

```bash
# 計画のみ（既定・書き込みなし）
python3 scripts/collect_reference_posts.py --account-id night_scout --source-platform threads --source-handle <handle>
# 本番収集（Sheets 書き込み）
python3 scripts/collect_reference_posts.py --account-id night_scout --source-platform threads --source-handle <handle> --apply --confirm-collect
```

- 収集対象は参考メタのみ（`use_status=REFERENCE_ONLY`）。実 X API は起動しない。
- 書き込み先タブ: `source_account_posts`（`post_url` で重複検知 / `rights_status` / `can_reuse_media`）。

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

- 投稿案は `DRAFT` / `WAITING_REVIEW` で停止。worker は拾わない（自動投稿されない）。

## GitHub Actions（dry-run）

- `content-daily-dry-run.yml`: collect / score / ideas の PLAN_ONLY サニティを毎日実行。
- `video-reference-dry-run.yml`（新規）: prepare / transcribe / clip / ideas(clips) の PLAN_ONLY サニティを週次実行。
- `source-fetch-dry-run.yml`: source registry 取得の dry-run（既存）。
- いずれも実投稿系フラグは `false` 既定。

## verify（recover_production_sheets_threads_first.py）

`verify_state` に参考パイプラインの安全不変条件を追加:

- `reference_posts_use_status_safe`: 参考投稿に投稿可ステータスを持たせない
- `reference_posts_reuse_rights_safe`: 流用可は許諾明示時のみ
- `reference_scores_high_risk_reference_only`: 流用リスク高は REFERENCE_ONLY 推奨
- `reference_scores_not_postable`: 採点行は投稿可ステータスを持たない

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
```
