# 複数AI共通作業規約 (AGENTS.md)

このドキュメントは、Codex、Antigravity、およびその他のAI開発ツールが、本プロジェクトで作業を行う際の恒久的なルールを定めたものです。頻繁に変更される進捗情報などは `START_HERE.md` を参照してください。

## 1. プロジェクト概要
SNS Growth Engine v2は、権利台帳に基づくソース取得、メディア理解、キャプション生成、および承認済みコンテンツのThreadsへの自動投稿を行うシステムです。

## 2. 最終Goal
`GOAL.md` および `config/goal_acceptance.json` で定義された35の要件を完全に満たし、実環境での稼働証跡を得ること。

## 3. 使用技術
- Python 3 (バックエンド、バッチ処理)
- GitHub Actions (CI/CD、スケジュール処理)
- Google Sheets (データストア、権限台帳)
- Cloudinary (メディアアセット管理)

## 4. ディレクトリ構成
- `src/`: コアロジック
- `scripts/`: エントリーポイント、バッチスクリプト
- `tests/`: 自動テスト
- `docs/`: 運用ドキュメント、AI間引き継ぎ記録
- `config/`: 設定ファイル

## 5. 正本となるデータ
- 権限・状態：Google Sheetsの各台帳
- 進捗・状態：`START_HERE.md` および `docs/goal-status.json`

## 6. Git運用ルール
- **main**: 常に安定版。直接コミット禁止。
- **目的別ブランチ**: `feature/` `fix/` `docs/` などをプレフィックスとし、ツール名への依存は不要。作業前に必ず最新のmainから分岐すること。
- 他のAIが作成したブランチを無断で書き換えない。
- 強制プッシュ (force push)、未確認のrebase、未コミット変更の無断破棄は禁止。

## 7. PR・CIルール
- 変更はPR経由でmainへマージする。
- CI（GitHub Actions）をすべて通過すること。workflow successを機能成功と混同しないこと。

## 8. テスト必須条件
- テストを省略しないこと。
- 新機能の追加・変更には対応するテストを追加・修正すること。

## 9. セキュリティ規約・秘密情報の取扱い
- secret、cookie、tokenはリポジトリにコミットしない。
- 実行中のAIはこれらの情報を読み取ったり、出力したりしない。

## 10. 投稿ゲート・実投稿時の条件
- **実投稿**: 明示されたcanary工程のみで行う。
- テスト投稿、dry-runを本番のPASSとして扱わない。
- 投稿ゲート (publish / Threads post gate) の権限や閾値を弱めないこと。

## 11. 変更禁止事項
- X (旧Twitter) への投稿
- `beauty_account` の操作
- validator閾値の低下
- 既存テストの削除や弱体化

## 12. AI間引き継ぎルール
- 作業開始時: `git fetch origin` 後に本ファイル、`START_HERE.md`、`docs/current-work.md`、`docs/ai-work-handoff.md`の最新記録を読む。
- 作業終了時: テスト実行、コミット、PR作成後、`START_HERE.md` と `docs/ai-work-handoff.md` を更新し、`docs/current-work.md` のステータスを `INACTIVE` または `HANDED_OFF` に変更する。
