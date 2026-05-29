# Phase 3 Go / No-Go 判断基準

このドキュメントは Phase 3（本番 SNS 投稿）に進んでよいかを判断するための基準を定める。
**すべての Go 条件が満たされるまで Phase 3 を開始しない。**

---

## 自動診断

```bash
python scripts/preflight_check.py
```

判定 `READY_FOR_TEST_WRITE` が出れば自動診断は通過。

---

## Go 条件（必須）

### テスト通過

- [ ] `python scripts/test_phase2.py` → **31 PASS / 0 FAIL**
- [ ] `python scripts/test_gemini_real.py` → **PASS または SKIP**
- [ ] `python scripts/test_sheets_connection.py --dry-run` → **PASS または SKIP**
- [ ] `python scripts/preflight_check.py` → **READY_FOR_TEST_WRITE**

### Sheets セットアップ完了

- [ ] 12タブすべて存在
- [ ] accounts: night_scout / liver_manager 両方とも active=TRUE
- [ ] content_categories: 16件以上（各アカウント8件）
- [ ] prompt_templates: 5件以上

### パイプライン動作確認

- [ ] Mode C (`--dry-run --use-sheets`) でパイプラインが正常終了
- [ ] Mode D (`--use-sheets --test-write`) で Sheets への書き込みが確認できた
- [ ] `queue` タブに `status=WAITING_REVIEW` の行が追加されていることを目視確認

### API 準備

- [ ] **X API**: X Developer Account (Essential 以上) 取得済み
  - Bearer Token
  - API Key / API Secret
  - Access Token / Access Token Secret
  - Rate Limit 確認: v2 Free は月500投稿

- [ ] **Threads API**: Meta Developer App 作成済み
  - Threads API アクセストークン取得済み
  - または Playwright 環境整備済み（フォールバック用）

### スプレッドシート確認

- [ ] `accounts.auto_publish` を手動で `TRUE` に変更済み
- [ ] `accounts.line_url` に正しい LINE URL を設定済み
- [ ] `accounts.x_handle` / `accounts.threads_handle` を設定済み
- [ ] `queue` タブを目視確認し、投稿対象行に問題がない

---

## No-Go 条件（以下のいずれかに該当したら進めない）

- `python scripts/test_phase2.py` に FAIL がある
- `preflight_check.py` の判定が `BLOCKED_BY_ENV` または `NOT_READY`
- `PUBLISH_ENABLED=true` にしたが投稿関数が未実装
- X API または Threads API の認証情報が未設定
- `accounts.auto_publish` が FALSE のまま
- `queue` タブに不審な行がある

---

## Phase 3 移行手順

1. 上記 Go 条件をすべて満たしたことを確認
2. X API / Threads API の実装を行う
   - `src/x_publisher.py` を作成
   - `src/threads_publisher.py` を作成
3. `queue_builder.py` の `_assert_publish_enabled()` を通過するよう投稿関数を実装
4. `.env` で `PUBLISH_ENABLED=true` に変更
5. 最初の投稿は **1件のみ** で試験
6. 投稿結果を確認してから量産

---

## 実装優先順位（Phase 3）

1. X 投稿（最小構成）
2. 投稿後インサイト取得
3. Threads 投稿
4. category_scores 自動集計
5. learning_rules 自動生成
6. GitHub Actions 自動実行

→ 詳細: [next-phase-plan.md](./next-phase-plan.md)

---

## Phase 3-D Go 条件（X 本番投稿 1件手動テスト）

### テスト通過（Phase 3-C 追加分）

- [ ] `python scripts/test_phase3c.py` → **全 PASS**
- [ ] `python scripts/check_publisher_credentials.py --platform x` → `READY_FOR_CREDENTIAL_TEST`
- [ ] `python scripts/phase3_safety_check.py` → 全 PASS

### Publisher 実装確認

- [ ] `x_publisher.py` に tweepy / requests-oauthlib による実投稿実装済み
- [ ] factory.py の XPublisher コメントアウトを外した
- [ ] `PUBLISH_ENABLED=true` かつ `ALLOW_REAL_X_POST=true` を `.env` に設定
- [ ] X API Developer Account（Essential 以上）取得済み
- [ ] OAuth 1.0a の 4項目（API Key/Secret + Access Token/Secret）設定済み

### Phase 3-D 手動投稿テスト手順

```bash
# 1. 安全確認
python scripts/phase3_safety_check.py
python scripts/check_publisher_credentials.py --platform x

# 2. READY キューを確認
python scripts/review_queue.py --account-id night_scout --status READY

# 3. 1件だけ本番投稿（実際にXに投稿される）
python scripts/publish_queue.py \
  --account-id night_scout --platform x --status READY --limit 1

# 4. 投稿結果確認
python scripts/review_queue.py --account-id night_scout --status POSTED
```

---

## Phase 3-E Go 条件（Threads 本番投稿 1件手動テスト）

- [ ] Phase 3-D（X 投稿テスト）成功
- [ ] `python scripts/check_publisher_credentials.py --platform threads` → `READY_FOR_CREDENTIAL_TEST`
- [ ] `threads_publisher.py` に Threads API v1.0 実装済み
- [ ] factory.py の ThreadsPublisher コメントアウトを外した
- [ ] `ALLOW_REAL_THREADS_POST=true` を `.env` に設定

---

## Phase 3-C 整備（Phase 3-D 前に必須）

### テスト通過（Phase 3-C 追加分）

- [ ] `python scripts/test_phase3c.py` → **全 PASS**
- [ ] `python scripts/check_publisher_credentials.py` → 安全に動作（exit 0）
- [ ] `python scripts/phase3_safety_check.py` → 全 PASS
- [ ] XPublisher / ThreadsPublisher スタブが dry_run=False で安全停止する

### スタブ安全確認

- [ ] XPublisher dry_run=True → success=True（94字テキスト）
- [ ] XPublisher dry_run=False → SAFETY_STOP
- [ ] factory.py dry_run=False → _SafetyStopPublisher
- [ ] ALLOW_REAL_X_POST=false 維持
- [ ] ALLOW_REAL_THREADS_POST=false 維持

---

## Phase 3-B 整備（Phase 3-C 前に必須）

### テスト通過（Phase 3-B 追加分）

- [ ] `python scripts/test_phase3b.py` → **全 PASS**
- [ ] `python scripts/approve_queue.py --list` → 正常表示
- [ ] `python scripts/approve_queue.py --queue-id <id> --approve --reason "..."` → READY に変更
- [ ] `python scripts/publish_queue.py --status READY --dry-run` → dry-run 正常終了

### 承認フロー確認

- [ ] WAITING_REVIEW → READY / REJECTED の変更が動作する
- [ ] 承認/却下ログが logs タブに記録される
- [ ] posted_results への書き込みがない
- [ ] queue.status が POSTED にならない

---

## Phase 3-A 整備（Phase 3-B 前に必須）

### テスト通過（Phase 3-A 追加分）

- [ ] `python scripts/test_phase3a.py` → **全 PASS**
- [ ] `python scripts/publish_queue.py --account-id night_scout --dry-run` → dry-run 正常終了
- [ ] `python scripts/phase3_safety_check.py` → publishers/dry_run.py 存在確認 PASS

### publish readiness

- [ ] `review_queue.py` で全アイテムの `[DRY/OK]` または `[DRY/WARN]` 確認
- [ ] `publish_queue.py --dry-run` で全アイテムが検証通過

---

## Phase 2.7 最終整備（Phase 3 前に必須）

Phase 2.7 で追加されたスクリプトを使って最終検証を行う。

### テスト通過（Phase 2.7 追加分）

- [ ] `python scripts/test_phase2.py` → PASS（既存テスト全通過）
- [ ] `python scripts/check_pipeline_integrity.py --account-id night_scout` → PASS/WARN のみ（FAIL なし）
- [ ] `python scripts/review_queue.py --account-id night_scout --status WAITING_REVIEW` → 対象件数表示・X投稿120字以内
- [ ] `python scripts/phase3_safety_check.py --use-sheets` → 全チェック通過

### score / level カラム修正

- [ ] `drafts.score` が正しく保存されている（--setup 実行後）
- [ ] `logs.level` が INFO/WARN/ERROR で正しく分類されている

---

## Phase 3 開始前の最終確認コマンド

```bash
# 1. Phase 2 テスト
python scripts/test_phase2.py

# 2. Gemini API テスト
python scripts/test_gemini_real.py

# 3. Sheets 接続テスト
python scripts/test_sheets_connection.py --dry-run

# 4. 総合診断
python scripts/preflight_check.py

# 5. パイプライン dry-run
python scripts/run_pipeline.py --account-id night_scout --dry-run --use-sheets

# 6. Sheets 書き込みテスト
python scripts/run_pipeline.py --account-id night_scout --use-sheets --test-write --limit 1

# 7. パイプライン整合性チェック（Phase 2.7 追加）
python scripts/check_pipeline_integrity.py --account-id night_scout

# 8. キュー確認（Phase 2.7 追加）
python scripts/review_queue.py --account-id night_scout --status WAITING_REVIEW

# 9. Phase 3 安全チェック（Phase 2.7 追加）
python scripts/phase3_safety_check.py --use-sheets
```

---

## Rate Limit 注意事項

| API | Free Tier 制限 |
|---|---|
| X API v2 (Free) | 投稿: 月500件 |
| Gemini 2.5 Flash | RPM: 15回/分（無料枠） |
| Google Sheets API | 読み書き: 100回/100秒 |

初回は最小限の件数で試験し、Rate Limit に余裕があることを確認してから増やす。
