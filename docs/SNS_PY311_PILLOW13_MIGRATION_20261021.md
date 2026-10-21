# SNS Growth Engine｜Python 3.11・Pillow 13移行計画（2026-10-21）

## 事実と変更範囲

- 本番VPSの `/usr/bin/python3` は Python 3.10.12。稼働中の `current`、`previous`、独立した緊急復旧用リリースはPython 3.10の実行環境を持つ。
- 2026-10-21にGitHub依存関係監査がPillow 12.3.0の8件の既知脆弱性を検出。公式Pillow 13.0.0はPython 3.11以上が必要。
- 専用SNS GitHub Runnerの `_work/_tool/Python/3.11.17/x64` にPython 3.11.17がある。ただしその実行ファイルの動的ライブラリの検索先は元のGitHubホストパスを指し、Xserverでそのまま実行するとlibpythonの読み込みに失敗する。
- Python 3.11 + Pillow 13.0.0を含む本番・メディア用の依存関係について、2026-10-21にVPSでbinary-only、install --dry-runの依存関係解決が成功した。実際のフルインストール、cron互換性、隔離本番ヘルスの合格は別途必要。

## 安全な実装

- 新しいリリースをステージする際だけ、SNS専用Runnerの**厳密な3.11.17**を使って**--copies**方式のリリース専用venvを生成する。共有OSのPython、他サービス、稼働中venvは変更しない。
- コピーされたPython実行ファイルだけに、ハッシュ固定の `patchelf==0.17.2.4` を使って専用Runner配下のlibpythonへの検索パスを設定する。改変対象のソースPython本体や共有ライブラリには触れない。元の実行ファイルにLD_LIBRARY_PATHが必要でも、新venvは環境変数なしで独立起動を検査する。
- `patchelf`は正確なホイール名とSHA-256を一致照合し、取得失敗・署名対象の不一致・バージョン不一致時はステージ作成を中断する。取得物は一時領域に限定して削除する。
- `requirements.txt`のPillowは13.0.0とし、ステージ完了前にPythonバージョン、Pillowバージョン、pip checkを検査する。
- 専用RunnerのPython toolcacheは、リリースがpyvenv.cfgで参照している間は**再生成可能キャッシュではなく復旧に必要な実行基盤**として保護する。従来の手動toolcache削除スクリプトも参照が残れば停止する。
- 2026-10-21にSNS専用Runner上の一時隔離環境でフル依存インストールとPillow PNG・PyAV・CTranslate2・ONNX Runtime・Sheetsクライアント・Playwrightの起動がPASS。安全監査を受け、GitHubワークフローは保護されたmainの手動dispatchのみとし、PRコードを共有VPSのRunnerで自動実行しない。SNSに送信しない。全工程で専用VPS共有デプロイロックを遵守する。
- 現行・直前・独立緊急用を3段で保護し、`pending`や復旧用環境の削除を禁止する。SNS実投稿/P0送信ゲートは引き続きOFF。

## 本番反映条件

1. PRの全必須CI（特にpip-auditとシークレット検査）がPASS。
2. 専用VPSのPython 3.11隔離フルインストール・ネイティブモジュールのテストPASS。
3. R2 P0 SQL、初期SQLiteと機密設定の最新読み戻し・隔離復元PASS。Google Sheets全データの独立復元は未対応であり、完全DRの主張を禁止。
4. ステージ前9GiB、ステージ後8GiBの空き容量基準、既存の媒体準備80%制限を遵守。
5. 投稿OFFの本番ステージ・読取ヘルス・アトミック切替を成功させ、旧リリースの回復方法を保持。
6. 切替後の独立ヘルスチェックとR2スケジューラ検査。失敗時は元版へロールバック。

## 容量の注意

この修正は脆弱性と再現性の問題を解決するものであり、リリースごとの大型メディア依存環境の複製をまだ削減しない。旧版には7日間保護、現行・previous・緊急復旧版の永久的な保護条件がある。共有venvの無検証ハードリンク化や、基盤Pythonのtoolcache削除を禁止する。

関連：[セキュリティIssue #436](https://github.com/dev-ch-hhuk39/sns-growth-engine/issues/436)、[ストレージPR #435](https://github.com/dev-ch-hhuk39/sns-growth-engine/pull/435)、[Google Sheets復元Issue #437](https://github.com/dev-ch-hhuk39/sns-growth-engine/issues/437)。
