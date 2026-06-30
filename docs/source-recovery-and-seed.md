# 過去共有ソースの回収と source registry seed

最終更新: 2026-06-29

## 概要(重要)

ユーザーは **過去にソースアカウントURLと選定ルールを共有済み** である。
本作業では「これからURLを入れてください」ではなく、既存 repo / docs / 既存seed から
共有済み・分類済みのソースURLを **回収して live registry 化** した。

回収元と統合先:

| ファイル | 役割 |
|---|---|
| `config/source_accounts/default_sources.json` | **真実源**。システム(`src/reference/source_registry.py`)が実際にロードし、`source_rows()` 経由で Sheets へ seed される。今回ここへ統合した。 |
| `config/source_accounts/production_sources.example.json` | 分類済みの **在庫superset(example)**。非query実URLを default へ dedup マージ。直接は変更しない。 |
| `config/source_accounts/recovered_shared_sources.json` | 既知の共有Threads 3件(回収メモ)。default へマージ済み。 |

## 回収・反映の結果

- 共有済み・分類済みURLを `default_sources.json` に dedup マージ(17件 → 59件)
- Threads 3件(`@kyaba_oohata` / `@kyaba_rui_scout` / `@chiikawan400`)を含む
- 重複(source_id / source_url正規化 / handle)は skip

## ユーザー明示 required source URL 反映 (2026-06-29)

追加の明示必須URLを authoritative required sources として扱い、`config/source_accounts/required_source_urls.json`
に固定した。今後 required URL が追加された場合もこのファイルへ追記し、required source tests の対象にする。

- required Threads / night_scout: 6件すべて照合。既存2件、追加4件。
- required X / night_scout: 7件すべて照合。6件はURL一致済み、`minatoku789` status URLは既存author sourceに `post_url` / `canonical_url` / `status_url` として追加。
- `default_sources.json`: 59件 → 63件。
- `fetch_enabled=true`: 0件のまま。
- Threads required source: `platform=threads` / `target_account_ids=["night_scout"]` / `active=true` / `manual_only=true` / `source_track=night_scout_reference`。
- X required source: `platform=x` / `target_account_ids=["night_scout"]` / `active=false` / `fetch_enabled=false` / `manual_only=true` / `source_track=x_manual_reference`。
- YouTube/TikTok再探索: production example の video source 33件はすべて default に存在。repo内の追加候補は個別動画/タグ/fixture/templateであり、source accountとして追加しない。

## 現フェーズ安全方針(`source_rows()` が強制)

- **全 source**: `fetch_enabled=false`、`allow_download/cut/upload=false`、`auto_priority_change_allowed=false`
- **X**: 今は投稿/開発対象外。**reference source として保持**し `active=false` / `fetch_enabled=false` / manual_only
- **TikTok / YouTube**: 動画参考・文字起こし・切り抜き候補化の対象だが `reuse_policy=reference_only` / `media_policy=do_not_download`(`can_reuse_media=false`)
- **beauty(`future_track=beauty_future`)**: 将来の美容IP/美女IP/TikTok Shop用の **参考source**。`active=false` / BLOCKED維持。
  - 注: 安全機構(orchestrator / pipeline_store / publish_threads_post 等)は posting account_id `beauty_account` をキーに block する。よって `target_account_ids` は `beauty_account` を維持し、将来用ラベルは `future_track="beauty_future"` フィールドで表現する(改名は安全機構を無効化するため行わない)。
- **公式/メディア系**: 除外せず priority を下げ、notes に `low_priority_media_official`
- **個人発信者 / ノウハウ発信者 / 伸びている配信者** を高優先
- **third-party 素材**: 勝手に download / cut / upload / repost しない。参考分析・要約・文字起こし・切り抜き候補化・自社投稿案化まで。
- **URL未入力カテゴリ**: `status=WAITING_URL_INPUT` / fetch 不可

## platform 優先度

TikTok > Threads / X > YouTube(`src/reference/source_scoring.py` の `platform_priority_score`)。
scoring は並び替え・候補提示用であり、priority の自動変更や実投稿判定には使わない。

## seed CLI

```bash
# dry-run(差分のみ、Sheets書き込みなし)
python3 scripts/seed_source_registry.py --dry-run --target-account all --platform all
python3 scripts/test_required_source_urls_present.py
python3 scripts/seed_source_registry.py --dry-run --target-account night_scout --platform threads --json
python3 scripts/seed_source_registry.py --dry-run --target-account beauty_account --platform youtube --json
python3 scripts/seed_source_registry.py --dry-run --target-account beauty_future --platform all --json
python3 scripts/seed_source_registry.py --dry-run --target-account all --platform query --json

# apply(Sheetsへ反映。--confirm-seed 必須。secret非表示・実fetch/postなし)
python3 scripts/seed_source_registry.py --apply --confirm-seed --target-account all --platform all
```

オプション: `--target-account {night_scout|liver_manager|beauty_account|beauty_future|all}`、
`--platform {threads|x|tiktok|youtube|instagram|note|manual_url|query|all}`、`--source-file <path>`。
dedup により source_id / source_url / handle 重複は skip。429 は backoff。

## verify

```bash
python3 scripts/recover_production_sheets_threads_first.py --verify-only --json
```

追加 checks: `source_registry_has_required_categories` / `source_urls_are_deduped` /
`x_sources_manual_only_current_phase` / `tiktok_youtube_reference_only` / `beauty_future_inactive` /
`beauty_target_account_id_preserved` / `beauty_reference_only_safety` /
`waiting_url_input_not_fetchable` / `third_party_media_not_reusable_by_default` / `source_priority_valid_range`。

注: registry を増やした直後は `source_registry_reflected` / `video_sources_reflected` が
「Sheets 未seed」を示して fail することがある。これは想定挙動で、seed apply 後に解消する。

## 今後ユーザーが追加URLを渡す場合の貼り付け形式

1行1URL、または以下のいずれか。回収側で platform/handle を自動判定し、target/category を付与する。

```
# <target_account: night_scout|liver_manager|beauty_account> / <category>
https://www.tiktok.com/@example
https://www.threads.com/@example
https://x.com/example   # X は reference 保持(現フェーズ投稿なし)
```

カテゴリ未確定でも可。未入力カテゴリは `WAITING_URL_INPUT` として残す。
beauty 将来用途は `target_account_ids=["beauty_account"]` のまま、`future_track="beauty_future"` / `usage_scope="future_reference_only"` で表現する。

## 次に収集→採点→投稿案生成を回す手順

1. `seed_source_registry.py --dry-run` で差分確認 → `--apply --confirm-seed` で Sheets 反映
2. `scripts/collect_source_account_posts.py` / `scripts/collect_references.py`(reference収集、実fetchは安全範囲)
3. `scripts/score_reference_posts.py`(採点)
4. `scripts/generate_threads_ideas_from_references.py`(Threads投稿案: night_scout / liver_manager)
5. 動画は `scripts/prepare_video_reference.py` → `transcribe_video_reference.py` → `plan_video_reference_posts.py`(参考・文字起こし・切り抜き候補化のみ)

## 2026-06-30 production loop seed完了

source registry の Sheets apply 後、実fetchなしで初回運用ループ用の手動reference seedを作成済み。

```bash
python3 scripts/seed_reference_posts_from_sources.py --account-id all --limit 5 --apply --confirm-seed
python3 scripts/score_reference_posts.py --account-id night_scout --limit 5 --apply --confirm-score
python3 scripts/score_reference_posts.py --account-id liver_manager --limit 5 --apply --confirm-score
python3 scripts/generate_threads_ideas_from_references.py --account-id night_scout --top-n 3 --apply --confirm-generate
python3 scripts/generate_threads_ideas_from_references.py --account-id liver_manager --top-n 3 --apply --confirm-generate
```

結果:

- `source_account_posts`: 10件（`manualref_`、REFERENCE_ONLY、media reuse不可）
- `reference_post_scores`: 10件（`qscore_`、採点行は投稿可statusなし）
- `queue`: `reference_score_to_threads` 6件（night_scout 3 / liver_manager 3）、すべて `WAITING_REVIEW`
- `READY`: 0件。人間承認までworkerは拾わない。
- 実fetch / X fetch / video download / transcription / Cloudinary upload / 実投稿は未実行。
