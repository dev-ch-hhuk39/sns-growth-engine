# Source Account / Video Source Registry

Phase 8で追加された外部参考アカウント・動画ソース管理の仕組み。

## 目的

どの外部アカウント・動画ソースから投稿/動画を取得し、どの自社アカウントの生成に使うかを管理する。

- X / Threads / TikTok / YouTube / YouTube Shorts などの参考元を管理
- sourceごとに target_account_ids で自社アカウントとの紐付けを管理
- sourceごとの rights / reuse / media policy を管理
- PDCA結果から source priority の改善提案を出す

## 禁止事項

- 実API取得 / scraping / 外部download は禁止
- source priority の自動変更は禁止（改善提案はWAITING_REVIEW）
- beauty_account向け source は医療広告/薬機法リスクに注意

## 設定ファイル

`config/source_accounts/default_sources.json`

## source要件

| フィールド | 説明 |
|---|---|
| source_id | 一意のID |
| source_platform | x / threads / tiktok / youtube / youtube_shorts / instagram_reels |
| source_handle | @ハンドル名またはチャンネルID |
| source_url | 参考元URL |
| target_account_ids | night_scout / liver_manager / beauty_account |
| collection_method | manual_json / manual_csv / manual_url / api_future / scrape_disallowed |
| rights_policy | reference_only / owned / licensed / unknown |
| reuse_policy | reference_only / transform_required / no_reuse |
| media_policy | do_not_download / plan_only / allow_download_with_confirmation |

## 安全ルール

- `rights_policy=unknown` → WAITING_REVIEW必須、参考のみ
- `reuse_policy=no_reuse` → media利用不可
- `media_policy=do_not_download` → download禁止
- `media_policy=plan_only` → planのみ、Cloudinary upload不可
- `blocked=true` → 収集不可
- `active=false` → 収集対象外
- `collection_method=scrape_disallowed` → scraping禁止

## CLI

```bash
# source一覧表示
python3 scripts/manage_source_accounts.py --list --dry-run

# アカウント別絞り込み
python3 scripts/manage_source_accounts.py --account-id night_scout --active-only --validate --dry-run

# 収集計画作成
python3 scripts/plan_source_collection.py --account-id night_scout --source-platform x --top-n 5 --dry-run --mock
```

## 既存機能との接続

```
source_account_registry
  → source_account_collector  (collect_from_source_registry)
  → media_ingestion_pipeline  (create_ingestion_plan_from_source)
  → end_to_end_preflight      (check_source_rights)
  → pdca_orchestrator         (analyze_by_source)
  → content_mix_planner       (source_ids参照)
```

## 過去共有sourceの回収・seed (2026-06-29)

ユーザーは過去にソースアカウントURL/選定ルールを共有済み。既存 repo / `production_sources.example.json` から
回収し `default_sources.json` へ dedup マージ済み(17→59件)。Threads 3件 + X/TikTok/YouTube/note の個人発信者中心。
seed CLI は `scripts/seed_source_registry.py`(dry-run/apply/--target-account/--platform/--source-file)。
詳細とポリシー・貼り付け形式・次手順は [source-recovery-and-seed.md](source-recovery-and-seed.md)。

beauty は posting account `beauty_account` を維持(安全機構が block するため改名しない)し、
将来用ラベルは `future_track="beauty_future"` / `source_track="beauty_future"` /
`usage_scope="future_reference_only"` フィールドで表現。`active=false` / `fetch_enabled=false` /
`can_reuse_media=false` / `use_policy=REFERENCE_ONLY` 固定。

## ユーザー明示 required source URL (2026-06-29)

ユーザーが明示した必須URLは `config/source_accounts/required_source_urls.json` に固定し、
`scripts/test_required_source_urls_present.py` ほか required source tests で検証する。

- Threads / night_scout: 6件すべて `default_sources.json` に存在。うち不足4件を追加。
- X / night_scout: 7件すべて存在。`minatoku789` の status URL は `post_url` / `canonical_url` / `status_url` として保持し、author handle も保持。
- X は `manual_only=true` / `active=false` / `fetch_enabled=false` / `source_track=x_manual_reference`。X API・X投稿・queue へ接続しない。
- required source 追加後の default registry は 63件、`fetch_enabled=true` は0件。
- YouTube/TikTok は repo/docs/seed を再探索し、production example の33件がすべて default に存在することを確認。追加で live registry 化すべき未登録の実アカウントURLはなし。

今後ユーザーから追加URLが来た場合は `required_source_urls.json` に追加し、required source tests を通すこと。
