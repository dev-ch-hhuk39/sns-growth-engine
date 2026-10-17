# P0 Threads: 投稿設定をONにするだけでは本番投稿を許可しない

対象は night_scout / liver_manager の **Threadsテキストのみ**。Beauty・画像・動画は対象外。

## 独立した投稿許可の条件

従来の BUFFERED_POSTING_ENABLED=true と SNS_P0_ONCE_GATE_ENABLED=true
の両方だけでは投稿を開始できない。既存の送信台帳とGoogle Sheets側の
投稿審査・投稿枠制約も引き続き適用する。

加えて、オーナー署名の短時間承認
shared/p0_once_private/approved_text_canary_<account_id>.json を必須とする。

- 認証：所有者だけが読める0600ファイル、HMAC-SHA256、改ざん防止、秘密キー非表示
- 対象：アカウント、投稿枠ID、キューID、正確なテキストの source_fingerprint、デプロイSHA
- 有効期間：発行から最大30分。古い承認や別リリースへ流用不可
- 実行：VPSの入口と、予約枠を変える前と、低レベル送信の直前にそれぞれ照合
- 失効、テキスト編集、キュー・アカウント違い、署名不正は Sheets 更新前に拒否
- 既存の一回限りのP0送信台帳と二重投稿禁止はそのまま維持

署名は管理者申告の記録であり、外部の証拠を自動で検証したことにはならない。

## 管理者による確認が必要な7項目

1. external_legacy_writers_frozen: 旧ホスト・外部ツールの書き込み権限が停止済み
2. historic_outcomes_reconciled: 過去の送信結果不明・重複データを照合済み
3. durable_backup_restored: 永続バックアップと本番相当の復元試験が完了
4. account_identity_and_rights_approved: 正しいアカウントと投稿素材の権利を確認済み
5. exact_text_and_queue_owner_approved: 予定本文、queue_id、投稿枠を個別に承認済み
6. metrics_alerting_and_rollback_prepared: 停止手順、計測、24h/72h/168h確認を準備済み
7. operator_accepts_one_use_no_retry: 不明な送信結果は絶対に再送しないと承認済み

**いずれも未確認のまま true と申告しないこと。** 現時点では本番承認ファイルを作成しない。

## 今後、すべての証拠が揃った場合の操作（現在は実行しない）

所有者が正しいJSON申請ファイルを非公開・0600権限でホスト上に用意する。
値はすべて当該キューに固有で、source_sha256 は
p0_real_delivery_once.source_fingerprint(account_id, queue_id, text)
で計算した値を用いる。

例の項目構成（以下はダミー。実務上の証拠ではない）：

~~~json
{
  "schema": "sns_p0_exact_text_canary_approval_v1",
  "account_id": "night_scout",
  "slot_id": "example_slot_123",
  "queue_id": "example_queue_1234",
  "source_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "release_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "approved_at_utc": "2026-10-17T04:00:00Z",
  "expires_at_utc": "2026-10-17T04:20:00Z",
  "approval_mode": "OWNER_SIGNED_EXACT_TEXT_CANARY_AFTER_EXTERNAL_EVIDENCE",
  "attestations": {
    "external_legacy_writers_frozen": true,
    "historic_outcomes_reconciled": true,
    "durable_backup_restored": true,
    "account_identity_and_rights_approved": true,
    "exact_text_and_queue_owner_approved": true,
    "metrics_alerting_and_rollback_prepared": true,
    "operator_accepts_one_use_no_retry": true
  }
}
~~~

申請が事実であると独立確認できた場合だけ、ホスト上で所有者が署名する。
このCLIを実行しても投稿設定はONにならない。既存承認の上書きは不可。

~~~bash
python3 -B scripts/p0_exact_canary_approval.py \
  --sign-private-request /home/operator/private/approved-request.json \
  --confirm OWNER_SIGNED_EXACT_TEXT_CANARY_AFTER_EXTERNAL_EVIDENCE
~~~

秘密キーをログ、コマンド引数、GitHubに表示しない。生の投稿文やトークンは
承認結果や検証ログに出力しない。

## 初回運用カナリアと完全自動化の区別

- 初回は1アカウント・1本文・1キューの承認済みテキストのみ
- 送信台帳、プロバイダー結果、Sheetsのread-after-writeを確認
- 24h/72h/168h計測が完了するまで無人・連続投稿を開始しない
- リトライ禁止：結果不明ならその場で停止してプロバイダーと人間が照合
- 他の媒体・旧ツールを技術的に停止する効果はない
- 投稿権限や実投稿は今回ONにしていない。別途正式な承認が必要

関連実装：scripts/p0_exact_canary_approval.py、
scripts/run_buffered_production_host.sh、
scripts/reconcile_due_production_slots.py、
scripts/process_threads_queue.py、
scripts/test_p0_exact_canary_approval.py

## 継続運用についての追記（2026-10-17）

最初の1件だけの承認と、実カナリア＋正確なライブSheets＋3計測予約を必須とする継続自動投稿の許可は別。詳しくは docs/P0_CONTINUOUS_POST_RELEASE_20261017.md を参照。通常モードの既定はcanaryで、本番投稿許可は現在OFF。\n