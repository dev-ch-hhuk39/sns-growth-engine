# 複数AI共通作業規約 (AGENTS.md)

このドキュメントは、Codex、Antigravity、およびその他のAI開発ツールが、本プロジェクトで作業を行う際の恒久的なルールを定めたものです。頻繁に変更される進捗情報などは `START_HERE.md` を参照してください。

## 1. プロジェクト概要
SNS Growth Engine v2は、権利台帳に基づくソース取得、メディア理解、キャプション生成、および承認済みコンテンツのThreadsへの自動投稿を行うシステムです。

## 2. 最終Goal
`GOAL.md` および `config/goal_acceptance.json` で定義された35の要件を完全に満たし、実環境での稼働証跡を得ること。

## AIの役割と設計権限

本プロジェクトでは、設計・方針・作業範囲は各タスクの明示的な実装指示で決定される。

実装を担当するAIは、指定された設計と受入条件に従ってコード変更、テスト、commit、push、PR更新を行う。

実装AIは、以下を独自判断で行ってはならない。

- Goalの変更
- Work Packageの再定義
- 受入条件の緩和
- validator閾値の変更
- permission gateの変更
- 投稿ゲートの恒久的な有効化
- データモデルの大規模変更
- 別の投稿先や別アカウントの追加
- 指定範囲外のリファクタリング

設計上の矛盾、既存コードとの重大な不一致、安全に実装できない問題を発見した場合は、勝手に再設計せず停止して報告する。

## 正本となる情報

- 最終Goal: `GOAL.md`
- 合格条件: `config/goal_acceptance.json`
- 実際の状態: Git、GitHub Actions、Google Sheets、Cloudinary、Threadsの実証証跡
- 実装順序: `docs/goal-completion-implementation-plan.md`
- 恒久的作業規約: `AGENTS.md`
- 現在地の要約: `START_HERE.md`
- セッション履歴: `docs/ai-work-handoff.md`
- 現在の作業予約: `docs/current-work.md`
- 機械評価結果: `docs/goal-status.json`

`START_HERE.md`と`docs/ai-work-handoff.md`は実証証拠より優先しない。
`docs/goal-status.json`はevidence collectorまたはGoal評価処理によって生成し、SHAだけを手作業で差し替えない。

## 使用技術
- Python 3 (バックエンド、バッチ処理)
- GitHub Actions (CI/CD、スケジュール処理)
- Google Sheets (データストア、権限台帳)
- Cloudinary (メディアアセット管理)

## ディレクトリ構成
- `src/`: コアロジック
- `scripts/`: エントリーポイント、バッチスクリプト
- `scripts/test_*.py`: 単体・統合・契約テスト
- `scripts/run_repository_tests.py`: リポジトリ全体テストランナー
- `.github/workflows/`: CI、本番準備、投稿、回復、監査workflow
- `docs/`: 運用ドキュメント、AI間引き継ぎ記録
- `config/`: 設定ファイル

## Git運用ルール
- **main**: 常に安定版。直接コミット禁止。
- **目的別ブランチ**: `feature/` `fix/` `docs/` などをプレフィックスとし、ツール名への依存は不要。作業前に必ず最新のmainから分岐すること。
- 他のAIが作成したブランチを無断で書き換えない。
- 強制プッシュ (force push)、未確認のrebase、未コミット変更の無断破棄は禁止。

## PR・CIルール
- 変更はPR経由でmainへマージする。
- CI（GitHub Actions）をすべて通過すること。workflow successを機能成功と混同しないこと。

## テスト必須条件
- テストを省略しないこと。
- 新機能の追加・変更には対応するテストを追加・修正すること。

## セキュリティ規約・秘密情報の取扱い
- secret、cookie、tokenはリポジトリにコミットしない。
- 実行中のAIはこれらの情報を読み取ったり、出力したりしない。

## 投稿ゲート・実投稿時の条件
- **実投稿**: 明示されたcanary工程のみで行う。
- テスト投稿、dry-runを本番のPASSとして扱わない。
- 投稿ゲート (publish / Threads post gate) の権限や閾値を弱めないこと。

## 変更禁止事項
- validator閾値の低下
- 既存テストの削除や弱体化

## 現在のGoal対象外

- Xへの実投稿
- `beauty_account`の操作
- X用scheduleの有効化

これらは未実装項目としてGoal進捗に含めない。
明示的に別Goalが作成されるまで、実装・実行・有効化しない。

## AI間引き継ぎルール
- 作業開始時: `git fetch origin` 後に本ファイル、`START_HERE.md`、`docs/current-work.md`、`docs/ai-work-handoff.md`の最新記録を読む。
- 作業終了時: テスト実行、コミット、PR作成後、`START_HERE.md`、`docs/current-work.md`、`docs/ai-work-handoff.md`を更新する。ただし、`docs/goal-status.json`は証拠収集・評価処理を実行した場合だけ更新する。通常の文書更新や小規模実装ごとに、手作業でGoal statusを書き換えないこと。
