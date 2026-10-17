# SNS Growth Engine — 初回署名付きカナリアと継続自動投稿の二段階許可

2026-10-17 JST。対象は Night Scout / Liver Manager のThreadsテキストのみ。
画像・動画・Beauty・X・他のSNS投稿やGoogle Sheets権限移行は対象外。

## 二段階にする理由

GOAL.md では安全な通常テキスト投稿を毎回人間が承認せず継続する。
初回カナリア1件だけの署名では、この条件が達成できない。
初回カナリアと、実証拠確認後の継続リリースを分離した。
両方とも投稿スイッチ、認証、権利、品質、1回限りの送信台帳、
二重投稿抑止、日次上限、クールダウン、Kill switchを迂回しない。

## 第一段階：正確な1件への初回承認（既定）

外部ライター停止、過去履歴、独立の永続バックアップ・復元、
権利と投稿先の本人確認、正確な本文と計測・停止手段を確認してから、
管理者が対象1件へ署名する。

アカウント別の所有者限定0600ファイル：
- approved_text_canary_night_scout.json
- approved_text_canary_liver_manager.json

旧単一ファイル approved_text_canary.json は読み取り互換のみ。
承認は最大30分。アカウント、slot、queue、本文SHA、リリースSHAを固定。
署名だけでは投稿設定が有効にならない。現状は実投稿なし。

## 第二段階：継続自動テキスト投稿（初期状態で禁止）

所有者限定runtime.env内の SNS_P0_AUTONOMY_MODE=continuous が必要。
未設定時は canary。未知値は拒否。GitHubの環境入力だけで継続モードへ
昇格できない。さらに次の証拠を各アカウントで個別確認する。

1. 所有者署名の対象アカウント・実リリースSHA固定の有効な30日以内の承認
2. 同アカウントの初回カナリアが署名付きP0台帳でPOSTED_VERIFIED
3. カナリアの不可逆one-use SEND記録が1件、正しい外部投稿IDと本文SHA
4. 未解決の送信結果が1件も残っていない
5. 本番Sheets posted_resultsに正しいアカウント・queue・result・外部投稿IDが1件だけ
6. 投稿が実投稿かつREAD_AFTER_WRITE_PASSで、本文SHA・正しいThreads URLも一致
7. 24h/72h/168hの計測予約が正しいID・日時・アカウントで3件、FAILEDなし
8. 既存のaccount fit・persona・rights・未承認素材拒否・送信抑止・日次上限が全て有効

VPSホスト入口では署名とP0台帳を検査するが、これは本番Sheets証拠の確認を
代替しない。予約枠claim前とThreads送信前は必ず生のSheetsのRAW値を再読する。
不一致時はPROCESSING書き込みと一回限りのCLAIMより前に停止する。

## 継続署名（本日時点では実行しない）

署名が必要なJSONのスキーマ:
- schema = sns_p0_continuous_text_release_v1
- account_id = night_scout か liver_manager
- release_sha = 実際の40桁mainデプロイSHA
- approved_at_utc / expires_at_utc = UTCのZ形式、最大30日
- approval_mode = OWNER_SIGNED_CONTINUOUS_AFTER_VERIFIED_CANARY_AND_EXTERNAL_EVIDENCE
- canary_queue_id / canary_source_sha256 / canary_external_post_id / canary_result_id
- attestations = 8つの管理者証拠確認をすべてtrue

attestationsのキー：
- external_legacy_writers_frozen
- historic_outcomes_reconciled
- durable_independent_backup_restored
- account_identity_and_rights_approved
- verified_first_canary_with_3_metrics_reserved
- metrics_alerting_and_rollback_prepared
- operator_accepts_irreversible_one_use_no_retry
- owner_approved_bounded_continuous_text_only

承認済みの正確なデータを0600の非公開申請ファイルへ保存後、
**所有者が本番ホスト上のみ**で明示的に署名する。

    python3 -B scripts/p0_release_mode_authority.py \
      --sign-private-request /owner/private/continuous-release-request.json \
      --confirm OWNER_SIGNED_CONTINUOUS_AFTER_VERIFIED_CANARY_AND_EXTERNAL_EVIDENCE

新しい承認は approved_continuous_<account>_<approved_at UTC>.json 形式で
新規作成のみ。上書き不可、有効な署名の重複はエラー、履歴は最大64件。
操作しても投稿ONにもモード変更にもならない。

設定ONの前に外部writer、独立した永続バックアップ、送信履歴、
初回の実投稿・計測を本人が確認する。同じVPS上の初期空DBバックアップや
一時復元成功を、独立災害復旧証拠として承認してはならない。

## 実装と境界

- scripts/p0_exact_canary_approval.py : 初回のアカウント別署名
- scripts/p0_release_mode_authority.py : ホスト台帳 + Sheets RAW証拠の二段階ゲート
- scripts/run_buffered_production_host.sh : 本番ホスト前段の許可チェック
- scripts/reconcile_due_production_slots.py : slot claim前チェック
- scripts/process_threads_queue.py : PROCESSING変更前・P0 claim前チェック
- scripts/write_buffered_runtime_env.py : owner-onlyの運用モードを保存
- scripts/test_p0_release_mode_authority.py : 未送信の実証拠・拒否条件テスト

**本作業で実投稿、投稿設定ON、実Sheets更新、権限変更は一切行わない。**

完了の区別：コード実装/QA/CI/投稿OFFデプロイと、実カナリア・実継続運用
の証拠は別。Beauty、Mediaの実送信権限も、この二段階ゲートでは解放されない。
