# Phase 3-C: Publisher 実装準備

---

## Phase 3-C の目的

X / Threads 本番投稿 API を安全に実装するための土台を整える。
**本番投稿は行わない。** `PUBLISH_ENABLED=false` を維持する。

---

## Phase 3-C でやったこと

| 実装 | ファイル |
|---|---|
| 環境変数設計 | `.env.template` |
| 設定読み込み関数追加 | `src/config_loader.py` |
| 認証情報チェック CLI | `scripts/check_publisher_credentials.py` |
| XPublisher スタブ | `src/publishers/x_publisher.py` |
| ThreadsPublisher スタブ | `src/publishers/threads_publisher.py` |
| factory.py 安全強化 | `src/publishers/factory.py` |
| publish_queue.py 安全強化 | `scripts/publish_queue.py` |
| phase3_safety_check.py 更新 | `scripts/phase3_safety_check.py` |
| テスト | `scripts/test_phase3c.py` |

---

## まだ本番投稿しない

| 禁止事項 | 理由 |
|---|---|
| X API への POST | `PUBLISH_ENABLED=false` / `ALLOW_REAL_X_POST=false` |
| Threads API への POST | `PUBLISH_ENABLED=false` / `ALLOW_REAL_THREADS_POST=false` |
| `queue.status = POSTED` | Phase 3-D/E まで変更しない |
| `posted_results` への書き込み | Phase 3-D/E まで書かない |
| factory.py が本番Publisher返却 | コメントアウト維持 |

---

## 追加した安全ガード

```
PUBLISH_ENABLED=false          SNS投稿全体ガード
ALLOW_REAL_X_POST=false        X 投稿専用ガード（Phase 3-D 手動テスト時のみ true）
ALLOW_REAL_THREADS_POST=false  Threads 投稿専用ガード（Phase 3-E 手動テスト時のみ true）
```

**3重ガード構造:**

1. `PUBLISH_ENABLED=false` → publish_queue.py が即時停止
2. `ALLOW_REAL_X_POST=false` → XPublisher が SAFETY_STOP を返す
3. factory.py が `_SafetyStopPublisher` を返す（本番Publisher を返さない）

---

## Phase 3-D に進む条件

→ 詳細: [phase3-go-no-go.md](./phase3-go-no-go.md)

1. Phase 3-C の全テスト通過
2. X API Developer Account 取得済み（Essential 以上）
3. `check_publisher_credentials.py --platform x` → `READY_FOR_CREDENTIAL_TEST`
4. `x_publisher.py` に tweepy / requests-oauthlib 実装
5. `phase3_safety_check.py` 全 PASS
6. `publish_queue.py --status READY --dry-run` で全アイテムが `[DRY/OK]`

---

## Phase 3-E に進む条件

1. Phase 3-D（X 手動投稿テスト）成功
2. Threads API アクセストークン取得済み
3. `check_publisher_credentials.py --platform threads` → `READY_FOR_CREDENTIAL_TEST`
4. `threads_publisher.py` に Threads API v1.0 実装

---

## 参照

- [x-publisher-setup.md](./x-publisher-setup.md) - X Publisher 実装手順
- [threads-publisher-setup.md](./threads-publisher-setup.md) - Threads Publisher 実装手順
- [publisher-credentials.md](./publisher-credentials.md) - 認証情報設計
- [phase3-go-no-go.md](./phase3-go-no-go.md) - Go/No-Go 条件
