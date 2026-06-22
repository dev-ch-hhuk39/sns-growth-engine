# Source Intake Template

新しい参照元アカウント/URLを登録する際のテンプレートと手順書。

---

## 現在の Source Registry ステータス（2026-06-22）

| source_id | platform | handle | target | rights_policy | media_policy | 状態 |
|---|---|---|---|---|---|---|
| src_ns_x_cand_001 | x | @takashimaanna | night_scout | reference_only | do_not_download | READY_FOR_REFERENCE_FETCH |
| src_ns_yt_cand_001 | youtube | UCh7IsMrygg8X4hEJe8mUcQw | night_scout | unknown | — | WAITING_RIGHTS_REVIEW |
| src_ns_query_001 | query | (未登録) | night_scout | reference_only | do_not_download | WAITING_URL_INPUT |
| src_lm_yt_cand_001 | youtube | @suu-san_pococha | liver_manager | unknown | — | WAITING_RIGHTS_REVIEW |
| src_lm_note_cand_001 | note | @mitsuakisusa | liver_manager | reference_only | do_not_download | READY_FOR_REFERENCE_FETCH |
| src_ba_yt_cand_001 | youtube | @CosmeWotaSara | beauty_account | unknown | — | BLOCKED_BEAUTY_ACCOUNT |
| src_ba_tt_cand_001 | tiktok | @egachannel1 | beauty_account | unknown | — | BLOCKED_BEAUTY_ACCOUNT |
| src_ba_x_cand_001 | x | @saraparin | beauty_account | reference_only | do_not_download | BLOCKED_BEAUTY_ACCOUNT |

### 状態定義

| 状態 | 意味 |
|---|---|
| `READY_FOR_REFERENCE_FETCH` | テキスト参照取得は可能（download不可）。active化待ち |
| `WAITING_RIGHTS_REVIEW` | rights_policy=unknown。人間によるレビュー後に policy 設定が必要 |
| `WAITING_URL_INPUT` | source_url が空。アカウントURL/チャンネルIDの入力待ち |
| `DO_NOT_DOWNLOAD` | media_policy=do_not_download。テキスト参照のみ |
| `APPROVED_MEDIA` | media_policy=approved_media_only。切り抜き/upload許可 |
| `BLOCKED_BEAUTY_ACCOUNT` | beauty_account向けソース。active化禁止 |

---

## 新規ソース登録手順

### Step 1: 対象アカウントの権利ポリシーを確認

以下を確認してから `rights_policy` を設定する:

| 確認項目 | NG例 | rights_policy |
|---|---|---|
| 商用利用禁止の明示 | 「転載・無断使用禁止」 | `do_not_use` |
| 参照・要約のみ可 | 利用規約で参照OK | `reference_only` |
| 切り抜き許可済み | 公式切り抜き権付与 | `approved_media` |
| 独自制作コンテンツ | 自社/自分の動画 | `own_media` |
| 不明 | 確認できない | `unknown` → WAITING_RIGHTS_REVIEW |

### Step 2: media_policy を設定

| rights_policy | media_policy の推奨値 |
|---|---|
| `reference_only` | `do_not_download` |
| `approved_media` | `approved_media_only` |
| `own_media` | `approved_media_only` |
| `unknown` | `do_not_download`（確認後に変更） |
| `do_not_use` | `do_not_download` |

### Step 3: config/source_accounts/default_sources.json に追記

```json
{
  "source_id": "src_<account>_<platform>_<type>_<seq>",
  "source_name": "<人間が読める名前>",
  "source_platform": "<x | youtube | tiktok | note | threads | instagram>",
  "source_handle": "@<handle> または channel_id",
  "source_url": "https://<url>",
  "target_account_ids": ["<account_id>"],
  "collection_method": "agent_reach",
  "fallback": ["browser_export", "manual_json"],
  "candidate_status": "candidate",
  "active": false,
  "fetch_enabled": false,
  "allow_network_fetch": false,
  "allow_download": false,
  "allow_cut": false,
  "allow_upload": false,
  "requires_local_login": false,
  "rights_policy": "<reference_only | approved_media | own_media | unknown | do_not_use>",
  "reuse_policy": "<reference_only | approved_media | own_media>",
  "media_policy": "<do_not_download | approved_media_only>",
  "pdca_enabled": false,
  "source_category": "<text_reference | video_clip | image>",
  "source_categories": ["<text_reference | video_clip | image>"],
  "use_cases": ["structure_reference", "hook_reference", "trend_research"],
  "target_generation_modes": ["reference_based"],
  "target_platforms": ["x", "threads"],
  "subject_policy": {
    "require_transform": true,
    "no_aggressive_recruiting": true,
    "no_suspicious_income_claims": true,
    "rules": ["require_transform", "no_aggressive_recruiting", "no_suspicious_income_claims"]
  },
  "default_queue_status": "DRAFT",
  "review_status": "WAITING_REVIEW",
  "max_items_per_run": 10,
  "language": "ja",
  "region": "JP",
  "concept_match_score": 0.0,
  "priority": 99,
  "auto_priority_change_allowed": false,
  "created_at": "<ISO8601>",
  "updated_at": "<ISO8601>",
  "review_notes": "<登録理由・確認内容のメモ>"
}
```

### Step 4: 登録後の確認コマンド

```bash
# registry 確認
python3 scripts/manage_source_accounts.py --list

# schema 検証テスト
python3 scripts/test_source_intake_schema.py
```

---

## 未登録ソースの入力待ちテンプレート

以下のソースはアカウントURL/チャンネルIDが未登録。確認後に `source_url` を更新する。

### src_ns_query_001 (night_scout / query)

```
source_handle: (未登録)
source_url: (未登録)
確認担当: ユーザー
確認方法: 検索キーワードまたはURLを直接入力
入力後のアクション: default_sources.json を更新し、test_source_intake_schema.py を再実行
```

---

## 安全ルール

- `beauty_account` のソースを active 化しない
- `allow_download=true` にする前に rights_policy が `approved_media` または `own_media` であることを確認
- `allow_cut=true` / `allow_upload=true` にする前に rights_policy と media_policy を両方確認
- `auto_priority_change_allowed=false` — source priority はシステムが自動変更しない
- Cloudinary upload は `ALLOW_CLOUDINARY_UPLOAD=true` 環境変数 + approved_media 必須
