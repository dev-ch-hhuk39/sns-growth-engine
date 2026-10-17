# SNS Growth Engine 専用GitHub RunnerのPython再生成キャッシュ回復

日時：2026-10-17 JST。VPSの8GiB最小空き容量基準を下げずに、
SNS Growth Engine専用セルフホストGitHub Runnerの再生成可能な
setup-pythonキャッシュだけを安全に整理する。

## 対象の境界

- 正確なパス：/opt/github-runners/sns-growth-engine/_work/_tool/Python
- 削除してよい候補：actions/setup-pythonが生成する完成済みの通常ディレクトリ。
  30分以上未変更かつ確認済み構造のPythonバージョンキャッシュ（最大5件）
- 絶対に触れない：本番 .buffered-runtime/current、過去のリリース、
  shared/runtime.env、p0_once_private SQLite、投稿素材、Sheets、Docker、
  他のGitHub Runner、他サービス全ファイル、手動の未保存ファイル
- Pythonのツールキャッシュは必要時にactions/setup-pythonが再生成する。
  削除後の初回セットアップには再取得時間やネットワークが必要になる。

## 二段階の実行

専用GitHubワークフロー sns-runner-toolcache-recovery.yml は手動でのみ起動できる。
最初は confirm_cleanup=false で、固定パス、構造、バージョン数、
変更後の経過時間、600MiB以上の回収可能量を確認する。

dry-runがPASSした場合だけ、オペレーターが confirm_cleanup=true として
同一mainリビジョンで再実行する。実行時はChadult VPS共通の
デプロイ排他ロックを保持し、キャッシュを使用中のプロセスがあれば停止する。

このワークフローはSNS専用ランナーの再生成可能キャッシュ以外を削除しない。
実投稿・Google Sheetsの更新・投稿ONを行うステップはない。

## 注意事項

- デプロイには前後の安全容量が必要。整理しても不足なら停止する。
- ロールバックリリースは必ず保持する。
- デプロイ時の8GiB安全基準を引き下げない。
- 投稿OFFで本番反映に成功後、独立したVPS監査でmain SHA、
  BUFFERED_POSTING_ENABLED、SNS_P0_ONCE_GATE_ENABLEDを再確認する。
- 実運用開始には外部単一ライター、永続バックアップ、履歴照合、権利と本人承認が別途必要。
