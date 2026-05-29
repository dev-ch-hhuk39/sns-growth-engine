# queue ステータスライフサイクル

queue タブの `status` カラムの定義と遷移を管理する。

---

## ステータス定義

| status | 意味 |
|---|---|
| `WAITING_REVIEW` | 人間確認待ち（auto_publish=FALSE 時のデフォルト） |
| `READY` | 自動投稿可能候補（auto_publish=TRUE かつスコア閾値通過） |
| `PROCESSING` | 投稿処理中（Phase 3-B 実装時に使用） |
| `POSTED` | 投稿済み（Phase 3-B 以降） |
| `FAILED` | 投稿失敗（Phase 3-B 以降） |
| `REJECTED` | 投稿しない（人間が却下） |
| `SKIPPED` | スキップ（重複・期限切れ等） |

---

## Phase 別の取り扱い

### Phase 2（現在: データ生成）

```
queue_builder.py が build_queue() を実行
  ↓
social_derivative.status=READY を確認
  ↓
accounts.auto_publish を確認
  ↓
FALSE → queue.status = WAITING_REVIEW で追加
TRUE + スコア通過 → queue.status = READY で追加
```

**queue.status は変更しない。**

---

### Phase 3-A（現在: dry-run 検証）

```
publish_queue.py --dry-run を実行
  ↓
queue.status = WAITING_REVIEW / READY を読み取る
  ↓
DryRunPublisher で検証（テキスト長・フォーマット）
  ↓
publish_queue.py → logs にチェック結果を記録
  ↓
queue.status は変更しない
  posted_results には書かない
```

**queue.status は変更しない。**
**posted_results には書かない。**

---

### Phase 3-B（現在: 承認フロー）

```
approve_queue.py --approve を実行
  ↓
queue.status: WAITING_REVIEW → READY
logs に queue_approved ログを記録

approve_queue.py --reject を実行
  ↓
queue.status: WAITING_REVIEW → REJECTED
logs に queue_rejected ログを記録

publish_queue.py --status READY --dry-run
  ↓
READY なアイテムを DryRunPublisher で検証
queue.status は変更しない
posted_results には書かない
```

**posted_results には書かない。queue.status を POSTED にしない。**

---

### Phase 3-C 以降（未実装: 本番投稿）

```
本番 Publisher 実行（X API / Threads API）
  ↓
成功 → READY → POSTED + posted_results に記録
失敗 → READY → FAILED + logs にエラー記録
```

---

## 状態遷移図

```
[build_queue]
              ┌────────────────────┐
              │  WAITING_REVIEW    │ ← auto_publish=FALSE
              └────────┬───────────┘
                       │ human approve（Phase 3-B）
              ┌────────▼───────────┐
              │      READY         │ ← auto_publish=TRUE
              └────────┬───────────┘
                       │ publish（Phase 3-B）
              ┌────────▼───────────┬─────────────────┐
              │     POSTED         │     FAILED       │
              └────────────────────┴─────────────────┘

人間によって却下:
  WAITING_REVIEW → REJECTED
  READY → REJECTED
```

---

## Phase 3-A での安全保証

`publish_queue.py` は以下を保証する:

1. `--dry-run` フラグが必須（なしで実行すると即終了）
2. `PUBLISH_ENABLED=false` の確認
3. `DryRunPublisher` は `posted_url=None`、`external_post_id=None` を返す
4. `queue.status` を変更しない
5. `posted_results` に書き込まない
6. `logs` に dry-run チェックログのみ記録する

---

## 関連スクリプト

| スクリプト | 役割 |
|---|---|
| `queue_builder.py` | queue にアイテムを追加する |
| `review_queue.py` | queue を確認する（読み取り専用） |
| `publish_queue.py` | Phase 3-A dry-run 検証 / Phase 3-B 本番投稿 |
| `check_pipeline_integrity.py` | WAITING_REVIEW 件数・status 整合性チェック |
