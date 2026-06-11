# アカウント拡張ガイド（Phase 6.0）

## 概要

`config/accounts/{account_id}.json` を作成するだけで新しいアカウントを追加できます。
`if account_id == "xxx"` の分岐は書きません。

---

## 1. 新規アカウントの追加手順

### Step 1: テンプレートをコピー

```bash
cp config/account_templates/base_account.json config/accounts/new_account.json
```

### Step 2: JSON を編集

必須フィールド:
- `account_id`: ファイル名（.json除く）と一致させる
- `display_name`: 表示名
- `status`: `draft_only`（まず設計検証から始める）
- `platforms`: `["x", "threads"]`
- `forbidden_keywords`: 禁止キーワードのリスト
- `forbidden_themes`: 禁止テーマのリスト
- `safety_policy.allow_real_post`: 必ず `false`

### Step 3: seeds.py に追加

`src/seeds.py` の `ACCOUNT_SEEDS_V2` に追加:

```python
{
    "account_id": "new_account",
    "account_name": "新規アカウント名",
    "active": "FALSE",  # draft_only は FALSE
    "auto_publish": "FALSE",
    ...
}
```

また `ACCOUNT_FORBIDDEN_KEYWORDS` と `ACCOUNT_FORBIDDEN_THEMES` にも追加する。

### Step 4: テスト実行

```bash
python scripts/test_account_config_loader.py
python scripts/test_account_extension_design.py
```

---

## 2. account_config の status 管理

| status | 意味 | 実投稿 | Sheets反映 |
|--------|------|--------|------------|
| `draft_only` | 設計検証中 | 禁止 | なし |
| `active` | 運用中 | safety_policy に従う | あり |
| `inactive` | 停止中 | 禁止 | なし |

**beauty_account は `draft_only` のまま運用する。READY化・POSTED化禁止。**

---

## 3. account_config の使い方（コード例）

```python
from accounts.account_config import load_account_config, is_draft_only

cfg = load_account_config("night_scout")

# プラットフォーム別文字数制限
limits = cfg.get_char_limits("x")  # {"soft": 120, "hard": 140}

# draft_only チェック
if cfg.is_draft_only():
    # READY 化禁止。WAITING_REVIEW のみ。
    pass

# 禁止キーワード（seeds.py とマージ済み）
forbidden = cfg.forbidden_keywords
```

---

## 4. thread_series_policy の設定

```json
{
  "thread_series_policy": {
    "enabled": true,
    "max_posts_per_series": 8,
    "default_post_count": 4,
    "roles": ["hook", "context", "reason", "example", "checklist", "objection_handling", "proof", "cta"]
  }
}
```

---

## 5. 安全ポリシーの設定

```json
{
  "safety_policy": {
    "requires_human_review_before_post": true,
    "allow_real_post": false,
    "min_publish_score": 65,
    "brand_risk_threshold": 25,
    "draft_only_enforcement": "STRICT"
  }
}
```

`draft_only_enforcement: "STRICT"` を設定すると、thread_series 生成時の generation_notes に draft_only の注記が追加される。

---

## 6. seeds.py との関係

`account_config.py` は以下の優先度でデータをマージする:

1. `config/accounts/{account_id}.json` の値（優先）
2. `seeds.py` の `ACCOUNT_FORBIDDEN_KEYWORDS` / `ACCOUNT_FORBIDDEN_THEMES`（補完）

seeds.py に存在するキーワードは JSON にない場合でも自動的にマージされる。

---

## 更新履歴

- Phase 6.0: 初期作成（2026-06-11）
