# Phase 2.7 最終整備

Phase 3（SNS 本番投稿）に入る前の最終整備フェーズ。
データ品質・安全ガード・運用ツールを整える。

---

## 実施内容

### 1. drafts.score 保存不備の修正

**問題:** pipeline 実行時に score=85/90 が出力されているにもかかわらず、
Google Sheets の drafts タブには score=None が保存されていた。

**原因:** 実際の Sheets tabs は古いスキーマで作成されており、
`score`, `score_reason`, `pv_score`, `cv_score`, `brand_risk_score` カラムが存在しなかった。
`save_draft()` は `ws.row_values(1)` で実際のヘッダーを取得してマッピングするため、
ヘッダーにないカラムは黙って無視されていた。

**修正:** `setup_and_verify.py --setup` を実行して `_ensure_tab()` で不足カラムを右端に追加。
コード変更は不要（TAB_DEFINITIONS には既に正しく定義済み）。

### 2. logs.level = None の修正

**問題:** logs タブに `level` カラムがなく、全行 level=None だった。

**修正内容:**
- `TAB_DEFINITIONS["logs"]` に `"level"` を追加（operation と status の間）
- `SheetsClient.log()` に `level: str = ""` パラメータを追加
- status から level を自動導出: ERROR/FAIL → ERROR, WARN → WARN, その他 → INFO
- `MockSheetsClient.log()` も同様に更新

### 3. check_pipeline_integrity.py 追加

実際の Sheets データを読み取り整合性を検証するスクリプト。
詳細: [pipeline-integrity-check.md](./pipeline-integrity-check.md)

### 4. review_queue.py 追加

WAITING_REVIEW のキューアイテムを drafts/social_derivatives と JOIN して確認するビューア。
詳細: [review-queue-usage.md](./review-queue-usage.md)

### 5. phase3_safety_check.py 追加

Phase 3 移行前の安全条件を一括検証するスクリプト。

```bash
python scripts/phase3_safety_check.py --use-sheets
```

チェック項目:
- PUBLISH_ENABLED=false であること
- X/Threads API 認証情報が未設定であること
- x_publisher.py / threads_publisher.py が存在しないこと
- posted_results が空であること
- logs に ERROR レベルが0件であること
- 既存3プロジェクトの git が clean であること

---

## 実行手順

```bash
cd v2

# Step 1: スキーマ更新（score/level カラムを Sheets に反映）
python scripts/setup_and_verify.py --setup

# Step 2: 検証
python scripts/setup_and_verify.py --verify

# Step 3: テスト
python scripts/test_phase2.py

# Step 4: Mode D 再テスト（実Sheets書き込み）
python scripts/run_pipeline.py --account-id night_scout --platforms x,threads --limit 1 --use-sheets --test-write

# Step 5: 整合性チェック
python scripts/check_pipeline_integrity.py --account-id night_scout

# Step 6: キュー確認
python scripts/review_queue.py --account-id night_scout --status WAITING_REVIEW

# Step 7: Phase 3 安全チェック
python scripts/phase3_safety_check.py --use-sheets

# Step 8: 総合診断
python scripts/preflight_check.py
```

---

## Go/No-Go 判断

すべての手順が PASS になれば Phase 3 実装を開始できる。
判断基準の詳細: [phase3-go-no-go.md](./phase3-go-no-go.md)
