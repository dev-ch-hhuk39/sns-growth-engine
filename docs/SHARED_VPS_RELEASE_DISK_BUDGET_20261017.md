# 共有VPS：SNSのimmutable releaseによる容量逼迫防止（2026-10-17）

## 根拠
2026-10-17実機で、SNS Growth Engineの本番releaseが6世代・各約716～720MiB（合計約4.3GiB）あり、全社共有49GiB VPSのディスク使用率が88%に達した。その他のAutomation Core、LIVE百貨、TTBA、Fukuri、Renewal HPも同居する。SNSのrelease作成に必要な容量を、従来の8GiB最低空き容量に加えて予算化する。

## 実装と変更範囲
- 新しいSNSリリース（存在しないrevision）をステージングする際は、処理前に共有VPS正本の `chadult-vps-resource-check --preflight 9` を必須とする。
- 依存パッケージとPython環境をstageに作成した後、正式なreleaseディレクトリへ昇格する前に `--preflight 8` を再実行。不足時は既存のtrapが**その実行で作ったstageだけ**を除去する。
- 9GiBは予測stage容量約720MiBに対する1GiBのバッファ。これは容量増を止める**fail-closedゲート**であって、不要releaseを勝手に削除する仕組みではない。
- 既存revisionに対するscheduler-only設定・既存リリースの検証では、新たなstage作成がなければ9GiBの追加バッファを要求しない。
- mainの部署ワークフローとglobal-deploy-lockの中のトランザクションも9GiBを必要とする。postingは従来どおりOFFがデフォルトで、外部投稿や公開はしない。

## 除外／今後の運用
- 現行 `current`、直前 `previous`、`pending`、shared、P0のDB、実投稿/権限/バックアップや他ツールのファイルに変更なし。
- SNSの旧releaseを7日未満で削除する案は採用しない。現行・previous・pendingを保護して、7日以上経過し、参照・復元を確認した版だけ専用の `prune_obsolete_runtime_releases.py` で整理する。
- GitHub上のソース・テスト変更は、その後実際に本番runtimeを切り替えたという証拠ではない。容量ゲートは次のrelease運用時に適用。
- 全社側で容量を増やし続ける原因は他アプリのbuild/backupにもある。これらはVPS Opsが別途保持ルールを定義し、不要と証明できない限り削除しない。

## 検証
- macOSの独立一時領域で `bash -n` を2つのdeployシェルに実施：PASS。
- `tests/test_sns_immutable_release_disk_headroom.py`：7/7 PASS。
- VPS本番の投稿・release・cron・Docker image/volume/DBには変更なし。
