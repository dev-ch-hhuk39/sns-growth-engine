# SNS｜予定投稿枠の読み取り専用監査・障害分類（2026-10-21）

## 目的

`.github/workflows/content-slot-recovery.yml` の scheduled job は1時間ごとに各アカウントの公開予定枠を**読み取り専用**で検査する。従来は `reconcile_due_production_slots.py --dry-run` が exit 2を返すと、ログには `READ_ONLY_SLOT_AUDIT_FAILED` だけが表示され、在庫不足と認証・APIなどの障害を区別できなかった。

## 変更内容

- 本来の監査コマンドと終了コードは変更しない。未充足の場合は引き続き失敗扱いとし、誤って正常判定しない。
- `scripts/summarize_readonly_slot_audit.py` は一時ファイルのJSONを最大2MBだけ読み、事前に定義した `status`・`reason` の分類名と件数のみ出力する。
- 投稿本文、キューID、外部リンク、認証トークン、Google Sheetsの値、例外本文はログへ出さない。未知のreasonは `OTHER_REDACTED` に置き換える。アカウント不一致・`dry_run=false`・JSON破損・件数上限超過はfail closedとする。
- `GITHUB_ACTIONS` のrawエラーは引き続き `$RUNNER_TEMP` にだけ出力し、Artifactに追加しない。
- `--apply`、実投稿、キュー更新、権限・R2設定の変更は一切行わない。

## 解釈例

- `NO_VALIDATED_BUFFERED_QUEUE`：投稿予定枠に対して、既存の品質・承認・重複・アカウント・日時・メディア条件を通過する候補が見つからない。勝手にREADYに変更しない。
- `DAILY_CAP_REACHED` / `COOLDOWN_ACTIVE`：既存の投稿数・間隔制限によりブロック。
- `OTHER_REDACTED` / `SLOT_AUDIT_UNVERIFIED_REPORT`：原因は未確定。受信エラー本文や秘密情報は表示せず、サービスアカウント・API・スクリプト構造を権限内で個別監査する。

## 完了基準

合成テスト7件、既存GitHub workflow契約テスト5件、全安全検査がPASS。mainへの統合後、次回scheduled dry-runで新しい分類ログが得られること。**Night Scout / Liver ManagerのREADYがまだ不足している問題を解決したわけではない。** 継続トラッキング：SNS Issue #441 / #439。
