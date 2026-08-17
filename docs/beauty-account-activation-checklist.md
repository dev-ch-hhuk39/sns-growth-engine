# beauty_account activation checklist

## 現在

コード側はcanary直前まで準備済みです。`draft_only`、全件 `WAITING_REVIEW`、scheduled publish無効を維持しています。

## オーナーが最後に用意するもの

- [ ] Threads handle
- [ ] Threads user ID
- [ ] OAuth credential

credentialの値はリポジトリやdocsへ書かず、次のsecret名へ登録します。

- `THREADS_HANDLE_BEAUTY_ACCOUNT`
- `THREADS_USER_ID_BEAUTY_ACCOUNT`
- `THREADS_ACCESS_TOKEN_BEAUTY_ACCOUNT`

`THREADS_ACCESS_TOKEN_BEAUTY_ACCOUNT`にはThreadsの長期トークンを登録します。既存の
`Refresh Threads Tokens`は毎週実行し、有効期限前に更新して同じsecretへ書き戻します。書き戻しには
Secrets更新権限を持つ`GH_SECRET_WRITE_TOKEN`が必要です。トークン値はログへ表示しません。

## Canary

- [ ] readinessが `READY_FOR_CANARY`
- [ ] persona / voice / beauty compliance PASS
- [ ] 美容医療候補は別レーンで人間レビュー済み
- [ ] 権利が必要なメディア候補はpermission evidence PASS
- [ ] 投稿本文と投稿先を人間が確認
- [ ] bounded canary成功
- [ ] permalink / posted_results / read-after-write確認
- [ ] metrics 24h / 72h / 7d予約

## 本番移行

canary成功後に限り、1〜2件/日のスケジュールを有効化します。
PDCAはbeauty_accountのMEASURED実績だけを使用し、安全・権限・投稿上限を変更しません。

1. 上記3 secretをGitHub Environment `production`へ登録する。
2. `Beauty Threads Production`を`dry_run`で実行し、認証・Sheets・publisherを確認する。
3. `prepare`で作成された`WAITING_REVIEW`を人間が確認し、1件だけ`READY`にする。
4. bounded canary成功とread-after-writeを確認した後、設定ファイルの本番有効化PRと
   `BEAUTY_ACTIVATION_APPROVED=true`を同時に適用する。

`BEAUTY_ACTIVATION_APPROVED`だけで`draft_only`を迂回できません。有効化前はpublish scheduleが
`NO_POST`または安全ゲートで停止します。prepare scheduleは09:30 / 18:30 JSTに審査候補だけを作り、
有効化後のpublish scheduleは11:30 / 20:30 JSTに人間承認済み`READY`だけを1件処理します。
