# Source Collection Runbook

Date: 2026-06-28

参考投稿・参考 URL を安全に収集／登録するための標準 CLI 入口。
詳細な設計・スキーマは既存 doc を参照する（本 doc は薄い入口）。

## 標準 CLI

| CLI | 役割 | 既定 |
|---|---|---|
| `collect_reference_posts.py` | 参考投稿のメタ収集（参考のみ） | PLAN_ONLY |
| `import_reference_urls.py` | 参考 URL を source registry に登録 | PLAN_ONLY |

両 CLI とも `build_plan()` を持つ薄いエントリーポイント。既定はドライラン。
実書き込みは `--apply` かつ各 `--confirm-*` の二重指定が必要。

## 1. 参考投稿の収集

```bash
# 計画のみ（既定・書き込みなし）
python3 scripts/collect_reference_posts.py --account-id night_scout --source-platform threads --source-handle <handle>
# 本番収集（Sheets 書き込み）
python3 scripts/collect_reference_posts.py --account-id night_scout --source-platform threads --source-handle <handle> --apply --confirm-collect
```

- 主要フラグ: `--account-id`{night_scout,liver_manager,beauty_account} / `--source-platform`（既定 threads） / `--source-handle` / `--input-json` / `--top-n`（既定 10）。
- 収集対象は参考メタのみ（`use_status=REFERENCE_ONLY`）。実 X/Threads API は起動しない。
- 書き込み先タブ: `source_account_posts`（`post_url` で重複検知 / `rights_status` / `can_reuse_media`）。

## 2. 参考 URL の登録

```bash
python3 scripts/import_reference_urls.py --source-id <id> --platform youtube --url <url> --target-account liver_manager
# 本番登録
python3 scripts/import_reference_urls.py --source-id <id> --platform youtube --url <url> --target-account liver_manager --apply --confirm-import
```

- 主要フラグ: `--source-id`（必須） / `--platform`（必須） / `--url`（必須） / `--target-account`（必須） / `--handle` / `--collection-method`（既定 manual_url） / `--source-file`（既定 `config/source_accounts/default_sources.json`）。
- 登録のみ。download / scraping はしない。`rights_status` 既定 unknown → 許諾未確認は WAITING_REVIEW。

## 動画ソースの扱い（重要）

動画ソースは専用タブを持たず、`source_accounts` / `reference_sources` で config 駆動管理する
（`src/collectors/video_source_manager.py`）。`video_sources` という名前のタブは存在しない。
動画の参考準備は [video-reference-runbook.md](video-reference-runbook.md) を参照。

## 安全方針

- `beauty_account` は対象外（draft_only）。
- `media_policy=do_not_download` は download 禁止、`plan_only` は Cloudinary upload 不可、`reuse_policy=no_reuse` は media 利用不可。

## 関連 doc

- [source-account-registry.md](source-account-registry.md) — source registry 設計・権利フィールド
- [reference-collection-usage.md](reference-collection-usage.md) — 収集の詳細手順
- [source-to-post-pipeline.md](source-to-post-pipeline.md) — source → 投稿案までの全体像
- [reference-pipeline-runbook.md](reference-pipeline-runbook.md) — 全 CLI 横断の安全設計
- [source-recovery-and-seed.md](source-recovery-and-seed.md) — **過去共有sourceの回収・seed**。ユーザーは過去にURL/選定ルールを共有済みで、既存 repo/example から回収して `default_sources.json` に dedup マージ済み(17→59件)。`seed_source_registry.py` で dry-run/apply。X=reference保持(manual_only)、TikTok/YouTube=reference_only、beautyは`target_account_ids=["beauty_account"]`維持でinactive、`beauty_future`はtrack labelのみ、公式メディア=低優先、URL未入力=WAITING_URL_INPUT。
