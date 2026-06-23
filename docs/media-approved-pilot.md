# Media Approved Pilot — 操作手順

- 作成日: 2026-06-24
- 担当: Claude Code (Sonnet 4.6)

## 概要

YouTube / TikTok のダウンロード・切り抜き・Cloudinary upload を  
**3段階の安全モード**で管理するパイロット workflow。

**実ファイル**: `.github/workflows/media-approved-pilot.yml`

## 実行モード

| mode | 内容 | 実 API 呼び出し | confirm=yes 必要 |
|---|---|---|---|
| `plan_only` | media plan 生成のみ。download/upload なし | No | No |
| `approved_media_dry_run` | pipeline ドライラン。実 download/upload なし | No | No |
| `approved_media_real` | 実 download + Cloudinary upload | Yes | **Yes** |

## 安全フラグ (デフォルト値)

```yaml
PUBLISH_ENABLED: "false"
ALLOW_REAL_X_POST: "false"
ALLOW_REAL_THREADS_POST: "false"
ALLOW_CLOUDINARY_UPLOAD: "false"
ALLOW_TRANSCRIPTION_API: "false"
```

`approved_media_real` + `confirm=yes` の時だけ `ALLOW_CLOUDINARY_UPLOAD: "true"` / `ALLOW_TRANSCRIPTION_API: "true"` が有効化される。

## 絶対ガード

- `account_id = beauty_account` は実行不可（workflow 全体に `if:` ガード）
- `confirm` が `yes` でない場合は `SAFETY_STOP` で停止
- `run:` ブロック内に `${{ github.event.inputs.* }}` を直接展開しない（コマンドインジェクション対策）

## 手動実行手順

### Step 1: GitHub Actions > media-approved-pilot > Run workflow

```
source_id: src_ns_yt_cand_001
account_id: night_scout
mode: plan_only
confirm: (空欄)
```

### Step 2: plan 確認後 dry_run

```
mode: approved_media_dry_run
```

### Step 3: 実行（ユーザー承認後のみ）

```
mode: approved_media_real
confirm: yes
```

## 対象 source の条件

実行前に以下を満たしていることを確認:

- `rights_policy = approved_media`（reference_only では実 download 不可）
- `active = true`
- `allow_download = true`
- `allow_upload = true`
- `review_status = APPROVED_MEDIA` 相当

## 現在承認済み source（参考のみ）

| source_id | platform | rights_policy | active |
|---|---|---|---|
| src_ns_yt_cand_001 | youtube | reference_only | true |
| src_lm_yt_cand_001 | youtube | reference_only | true |

※ 現時点では `reference_only` = download 禁止。`approved_media` への昇格は別途承認フロー必要。

## 関連ファイル

- `.github/workflows/media-approved-pilot.yml` — workflow 本体
- `scripts/test_media_approved_pilot_workflow.py` — workflow 安全性テスト
- `scripts/test_cloudinary_upload_guard.py` — Cloudinary upload guard テスト
- `docs/cloudinary-upload-runbook.md` — Cloudinary 詳細手順
- `config/source_accounts/default_sources.json` — source registry
