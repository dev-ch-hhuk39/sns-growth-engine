# SNS Growth Engine｜完了までの継続指示・VPS最小構成・R2復旧の正本（2026-10-21 JST）

**Owner directive:** 2026-10-21、ユーザーは「この指示を繰り返さない。新しいChadult Desktop CommanderカスタムMCPとGitHubを利用して、R2へのバックアップ移行、VPS必要最小限化、全残課題の実装・検証をできる限り一括実行して完了まで進めてほしい」と指示した。本書と [GitHub Issue #439](https://github.com/dev-ch-hhuk39/sns-growth-engine/issues/439) を複数チャット/担当間の引き継ぎ正本とする。本書の作成はChatGPT単独の永続的バックグラウンド実行を意味しない。既存systemd/GitHubスケジュールにより自動監視は継続する。

## 対象・安全条件

- 対象は**SNS Growth Engine**の所有物：VPS `/opt/github-runners/sns-growth-engine/` と `/var/lib/sns-growth-engine/`。ただしAgentOps管理共通R2バックアップとの接続については、AgentOps側の既存運用と整合させて変更する。
- 共通Docker/containerd/BuildKit、他サービスのDB・キャッシュ・ファイル・ロールバック、OSグローバルPython、他アプリのジョブは対象外。SNS専用領域にも他所有者・マウント先・hardlink共有資産があれば停止。
- 現行・直前・独立緊急復旧リリースを**最低3世代**保持し、pendingが存在するなら追加保護。復旧可能性を削減のために犠牲にしない。
- SNS投稿/P0送信・外部送信は現状OFF。ユーザーが明示的に別途許可しない限り有効化しない。
- すべての削除は個別正確SHA、7日間保護、所有者/デバイス/マウント・共有ハードリンク検査、rootの全プロセスのcmdline/cwd/FD、共通VPS deploy lock、復旧検証、再計測・ヘルス検査を通す。未検証バックアップは削除しない。既存の正確SHA承認がない新対象の削除は保留。
- R2バケットは`chadult-shared-vps-backup-private`。**新規バケット・トークン禁止**。root所有のAgentOps共通restic（クライアント側暗号化）と容量5,000,000,000バイトの内部ガードを利用し、Cloudflareアカウント全体の無料枠とは分けて監視する。

## 2026-10-21に本番で確認した完了事項

- SNS本番`current=b444247d06877bc537318cdb004cff4d1417df3c`、Python 3.11.17 / Pillow 13.0.0。依存関係監査、統合テスト、秘密情報検査、隔離Linux起動・Sheets読み取りヘルス PASS。前版 `4c162d5fb96168b2c88b8b58b40b8d918b3017dd`、独立緊急 `bec16989c859e97abe53a736afb6d76bc12338a1` を保護。pendingなし。SNS投稿/P0 OFF。
- AgentOps本番`/usr/local/libexec/chadult-offsite-backup/agentops-43ba97d-sns-sheets-r2-20261021`。以前の`agentops-2fe2485-r2-unified-20261021`はロールバック用に保持。中央単一R2日次バックアップ/ヘルスsystemd timerは有効。
- 2026-10-21 13:49 JSTから中央**本物のマルチサービスR2バックアップ.service**を手動実行。TTBA/Core/Fukuri/Portal/LIVE/Liveluencer/SNS各ステップ COMPLETE、SNS P0 SQL/初期SQLite/configのR2実読み戻し・隔離復元PASS、SNSマスターGoogle Sheets59タブ・104セグメントの暗号化R2保存・実読み戻しPASS、`ENCRYPTED_OFFSITE_BACKUP_SUCCESS`、systemd Result=success、終了コード0。共通サービス全体の成功であり、各ツールの全データのDR完了を保証しない。
- Google Sheets は数式・セル値・タブ構造のR2隔離復元に成功。フォーマット、入力規則、セル保護、ACL、Apps Script、**実際の新規ネイティブSheetsへの復元**は未検証。[Issue #437](https://github.com/dev-ch-hhuk39/sns-growth-engine/issues/437)継続。
- SNS専用pipキャッシュで84,409,551バイト（80.50MiB）論理サイズ削減を完了。HFモデルやPython3.11.17 Runner toolcacheは依存関係があるため未削除。
- SNS読取専用Storage Lifecycle Monitorは日次、root側AgentOps R2バックアップは毎日~02:19 JST、容量監視・復旧証跡はGitHub/日誌へ集約する。

## 最新SNS容量実測・保留対象

2026-10-21 13:47 JST：VPS空き10,432,626,688 bytes（使用率約80%）、SNS所有リリース9世代合計5,193,836KiB、SNS専用HFモデルキャッシュ551,380KiB、Runner `_work/_tool` 583,392KiB。

| リリースSHA | サイズ KiB | 保持/整理 |
|---|---:|---|
| `b444247d06877bc537318cdb004cff4d1417df3c` | 733,752 | **現行・永続保護** |
| `4c162d5fb96168b2c88b8b58b40b8d918b3017dd` | 740,452 | **前版・保護** |
| `bec16989c859e97abe53a736afb6d76bc12338a1` | 737,180 | **独立緊急復旧・保護** |
| `ae42996de3287b3a370d49e8c08b8032da706171` | 736,840 | 7日間は**10/23 18:16 JST**まで |
| `2fd217c5910704cdf3f686f0ebadbc731a33c1fd` | 737,008 | **10/24 13:55 JST**まで |
| `f6b78bacd6fa4a72d67894bd3c09cbac38391d99` | 737,184 | **10/24 14:46 JST**まで |
| `a45ed15f05095b283728be94b84d72957237a44f` | 16,936 | 不完全、**10/26 20:57 JST**まで |
| `32ea12cc5fec3b9709f67f1f36da1c8fe6f2b897` | 16,856 | 不完全、**10/26 20:57 JST**まで |

5つの整理候補合計 **2,244,824 KiB（約2.14GiB）**。日時はディレクトリ更新時刻から算出した**審査開始可能時刻**であり、直ちに削除可能との判定ではない。リリース構造を一括削除せず、確実に使われていないSHAを指定して個別の権限・プロセス・復旧条件を調べる。

## この会話で追加した次の改善

`scripts/prune_obsolete_runtime_releases.py`に追加安全検査：
- Linux /proc/self/mountinfoから対象ツリー内のbind等マウントを検出して削除停止
- すべての対象ファイル/ディレクトリ/シンボリックリンクのSNS所有UIDと同一デバイスを検査
- 特殊ファイル・未知のハードリンクは削除停止
- os.walkではシンボリックリンクの先を追跡せず、fdベースのsymlink-safe rmtreeを要求
- 対象プロセス、共通deployロック、7日間、現行/前版/独立緊急保護は既存コードのまま追加。
- Macで24テストPASS（Linux専用7件はスキップ）、**VPS上では24テストすべてPASS**。Linuxで現行の整理候補2ディレクトリに新しい読取専用ツリー安全監査を実行しPASS。削除は0件。

## 完了条件・残件

1. R2中央日次バックアップに継続失敗がなく、SNS P0/Sheetsのリモート読み戻し・隔離復元が確認できること。失敗すればローカル状態を保持。
2. Google Sheetsの値/数式だけでなくネイティブ復元に必要なメタデータ・再構築と権限に関して実地検証すること（#437）。
3. 7日間経過した所有確認済み旧リリースを対象限定で整理し、**実際の回収バイト数**を測定。無条件削除や共通キャッシュ削除をしない。
4. 今後のリリース配布で~720MiBのvenvが無制限に蓄積しないよう保持期限・上限・障害通知を運用すること。容量監視は既存のGitHub読取専用ワークフロー、削除は適切な権限・承認の範囲で行う。
5. AUTO_READYの品質SLOが現在未達。直近のNo-Post `Autopilot AUTO_READY Pilot` #39522078604 は `GENERATION_PROCESS_TIMEOUT`, `AI_APPROVAL_BUDGET_EXHAUSTED`, `NO_PUBLISHABLE_READY`。品質承認を緩めず生成タイムアウト/予算配分/ready候補数のコードを調査・テストして直す。外部投稿を許可しない。
6. コード変更はGitHub PR、単体テスト、Mac full quality、Linux隔離テスト、本番は事前後のヘルス・rollback条件を通過させる。不要なユーザー手動コマンド実行を要求しない。

**引き継ぎ方法**：次の担当者はこの文書→Issue #439→Issue #437→最新GitHub main/PR→VPS実測の順で確認し、最新実態と矛盾する古い数値で削除判断をしない。ChatGPTのタスク枠は2026-10-21時点で上限10件で追加できなかったため、専用の新規ChatGPT定期タスクは作成されていない。既存のVPS/GitHub定期監視は引き続き稼働し、ChatGPTがチャット外で自動的に開発作業をし続けると主張しない。
