# 新規 SNS マスターシート セットアップ手順

## 概要

- 作成日: 2026-06-20
- 目的: sns-growth-engine v2 で使用する Google スプレッドシートを新規作成し、タブを初期化する

---

## 前提条件

| 条件 | 確認方法 |
|---|---|
| Google アカウント | 新規シート作成権限があること |
| Service Account | GCP Console で作成済みであること |
| SA 権限 | 新規シートへの「編集者」共有が完了していること |

---

## Step 1: Google スプレッドシートを新規作成

1. Google Drive（https://drive.google.com）にアクセス
2. 「新規」→「Google スプレッドシート」→「空白のスプレッドシート」
3. シート名を設定（例: `SNS投稿管理 2026`）
4. URL から スプレッドシート ID を取得する

```
URL 例: https://docs.google.com/spreadsheets/d/1ABCDEFGhijklMNOPQRstuvWXYZ/edit
                                              ↑ここが SHEET_ID
スプレッドシート ID: 1ABCDEFGhijklMNOPQRstuvWXYZ
```

---

## Step 2: Service Account の JSON キーを取得・エンコード

### 2-1: GCP Console で SA JSON をダウンロード

```
GCP Console → IAM と管理 → サービス アカウント
→ 対象 SA を選択 → 「キー」タブ → 「鍵を追加」→「JSON」
→ ダウンロード（例: sns-growth-engine-sa-xxxxxx.json）
```

**重要:** JSON ファイルは `.gitignore` 対象ディレクトリに保管し、コミットしないこと。

### 2-2: Base64 エンコード

```bash
# macOS / Linux
base64 -i sns-growth-engine-sa-xxxxxx.json | tr -d '\n'
```

出力された文字列を `.env` の `SA_JSON_BASE64` に設定する（値は表示しない）。

---

## Step 3: Service Account をスプレッドシートに共有

1. Google スプレッドシートを開く
2. 右上「共有」ボタン → メールアドレスを入力
3. SA のメールアドレス（例: `my-sa@my-project.iam.gserviceaccount.com`）を入力
4. 権限: **「編集者」**
5. 「送信」をクリック

---

## Step 4: .env に設定

```bash
cp .env.template .env
# エディタで以下を設定（値は空のまま公開してはいけない）:
#   SNS_MASTER_SHEET_ID=<Step 1 で取得した SHEET_ID>
#   SA_JSON_BASE64=<Step 2-2 で取得した base64 文字列>
```

---

## Step 5: 認証情報 readiness チェック

```bash
python3 scripts/check_credentials_readiness.py
```

以下のように `[Google Sheets]` セクションが全て `✓ SET` になることを確認する。

```
[Google Sheets]
  ✓ SET     SNS_MASTER_SHEET_ID
  ✓ SET     SA_JSON_BASE64 (or GCP_SA_JSON)
```

---

## Step 6: タブ作成 dry-run

タブ作成前に、どのタブが作成されるかを確認する。

```bash
python3 scripts/setup_sheets.py --use-japanese-tabs --dry-run
```

期待される出力例（29 タブ）:

```
=== Sheets セットアップ dry-run ===
SNS_MASTER_SHEET_ID: SET
日本語タブ名モード: ON

作成予定タブ一覧 (29 件):
   1. [accounts]                       → タブ名: 'アカウント管理'  (列数: ...)
   2. [reference_posts]                → タブ名: '参考投稿'  (列数: ...)
  ...
  29. [transcription_runs]             → タブ名: '文字起こし実行履歴'  (列数: ...)

[DRY_RUN] 実際の作成は行いません。
```

---

## Step 7: タブ作成（実行）

dry-run で確認後、実際にタブを作成する。

```bash
python3 scripts/setup_sheets.py --use-japanese-tabs --confirm-setup
```

完了後、以下のように表示されれば成功:

```
完了: 作成 29 / スキップ 0 / 合計 29 タブ
```

---

## Step 8: 既存シートの日本語タブ名移行（既存シートがある場合のみ）

既に英語名タブが存在するシートを移行する場合は migration スクリプトを使用する。

```bash
# dry-run: リネーム対象を確認
python3 scripts/migrate_sheet_tabs_to_japanese.py --dry-run

# 実行
python3 scripts/migrate_sheet_tabs_to_japanese.py --confirm-sheets-migration
```

migration スクリプトは以下の動作をする:
- 英語名タブ → 対応する日本語名にリネーム
- 既に日本語名のタブ → スキップ
- `TAB_DISPLAY_NAMES` にない英語タブ → NOT_FOUND として報告

---

## タブ一覧（29 タブ）

| 論理名（英語）| 表示名（日本語）|
|---|---|
| accounts | アカウント管理 |
| reference_posts | 参考投稿 |
| content_categories | 投稿カテゴリ |
| drafts | 投稿下書き |
| social_derivatives | SNS投稿文 |
| posted_results | 投稿結果 |
| category_scores | カテゴリ成績 |
| distribution_rules | 配信ルール |
| learning_rules | 学習ルール |
| prompt_templates | プロンプト管理 |
| queue | 投稿キュー |
| logs | 実行ログ |
| media_assets | メディア資産 |
| reference_post_scores | 参考投稿スコア |
| reference_sources | 動画収集元 |
| video_transcripts | 動画文字起こし |
| video_clip_candidates | 動画クリップ候補 |
| transcription_runs | 文字起こし実行履歴 |
| generation_jobs | 生成ジョブ |
| prompt_improvement_suggestions | 改善提案 |
| thread_series | スレッド構成 |
| thread_series_posts | スレッド投稿 |
| content_mix_plans | 投稿配分計画 |
| source_accounts | 収集元アカウント |
| source_account_posts | 収集済み投稿 |
| source_collection_plans | 収集計画 |
| media_ingestion_runs | メディア取込履歴 |
| end_to_end_preflight_runs | 投稿前チェック履歴 |
| pdca_runs | PDCA実行履歴 |

---

## ロールバック手順（タブ作成後に問題が発生した場合）

タブが意図せず作成された場合:

1. Google スプレッドシートを開く
2. 問題のあるタブを右クリック → 「シートを削除」
3. `setup_sheets.py --dry-run` で状態を確認
4. 必要であれば再度 `--confirm-setup` で作成し直す

---

## よくある問題

| 症状 | 原因 | 対処 |
|---|---|---|
| `PERMISSION_DENIED` | SA がシートへの編集権限を持っていない | Step 3 で SA を「編集者」共有 |
| `SA_JSON_BASE64 が未設定` | .env に設定されていない | Step 4 を再実行 |
| `SNS_MASTER_SHEET_ID が未設定` | .env に設定されていない | Step 4 を再実行 |
| タブが重複 | 既に同名タブが存在 | スクリプトが自動スキップする（skip カウントが増える）|
| `WorksheetNotFound` | タブ名が英語のまま | `migrate_sheet_tabs_to_japanese.py` を実行 |

---

## 関連ドキュメント

- `docs/credential-migration-plan.md`: 認証情報移行の全体手順
- `docs/sheets-schema.md`: タブのスキーマ定義
- `src/sheets_client.py`: `TAB_DISPLAY_NAMES` と `_ws()` の実装
- `scripts/setup_sheets.py`: タブ作成スクリプト
- `scripts/migrate_sheet_tabs_to_japanese.py`: タブ名移行スクリプト
