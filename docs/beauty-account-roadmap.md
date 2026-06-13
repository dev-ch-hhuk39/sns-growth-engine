# beauty_account ロードマップ

## 現状（2026-06-11）

**Phase 6.1: draft_only 設計・基盤構築**

- [x] account_config JSON 作成（status=draft_only）
- [x] seeds.py に beauty_account エントリ追加（active=FALSE）
- [x] 禁止キーワード・テーマ設定
- [x] thread_series_generator による mock 生成確認
- [x] テストスクリプト作成・全 PASS 確認
- [ ] thread_series 実生成（LLM実API）：ユーザー承認後
- [ ] status = active への変更：条件達成後のみ

---

## ロードマップ

### Phase 6.1（現在）: draft_only 基盤
- account_config / seeds / thread_series 基盤を整備
- mock LLM でサンプル生成・レビューを繰り返す
- 禁止キーワード・テーマの検証

### Phase 6.1b（将来）: コンテンツ設計確定
- 10件以上のサンプル生成・人間レビュー
- カテゴリ別の投稿パターン確定
- CTAテキスト・LINE URL の準備

### Phase 6.1c（将来）: active 化前の最終確認
- 全サンプルの禁止キーワード・ブランドリスクチェック
- ユーザー承認
- status = "active" への変更

### Phase 6.1d（将来）: 本格運用
- 実LLM生成開始
- Sheets への投稿管理
- 投稿結果のラーニング

---

## READY 化の禁止事項

以下は自動実行・スクリプト自動化してはいけない:

- beauty_account の status = "active" への変更（ユーザー承認必須）
- beauty_account の queue.status = "READY" への変更
- beauty_account の実投稿（X / Threads）
- beauty_account の posted_results への保存

---

## 更新履歴

- Phase 6.1: 初期ロードマップ作成（2026-06-11）
- Phase 8: 活性化条件CLIを追加（check_beauty_activation_readiness.py）。現時点で常にBLOCKED/NOT_READY。詳細は `docs/beauty-account-activation-checklist.md` 参照（2026-06-13）
