# beauty_account ロードマップ

## コード準備済み

- [x] `beauty_account` のdraft-only設定
- [x] オーナー指定22参照元のmapping
- [x] personaとcanonical voice profile
- [x] voice / public post validator
- [x] 美容固有compliance
- [x] 美容医療の別レビュー・レーン
- [x] `beauty_account` 完全分離PDCA
- [x] 5生成ルート
- [x] 全候補 `WAITING_REVIEW`
- [x] 初期1〜2件/日の予定枠
- [x] credential名のプレースホルダー
- [x] focused tests

## オーナー入力後

1. Threads handleを設定
2. Threads user IDをsecretへ設定
3. OAuth credentialをsecretへ設定
4. `check_beauty_activation_readiness.py` で `READY_FOR_CANARY` を確認
5. WAITING_REVIEW候補を人間が確認
6. bounded canaryを1件ずつ実行
7. posted_results、read-after-write、metrics予約を確認
8. 問題がない場合だけ1〜2件/日の本番スケジュールを有効化

認証入力前にactive化、AUTO_READY、実投稿を行うことは禁止します。
