# 複数AI共通作業規約

この文書はSNS Growth Engine v2の恒久的な作業規約です。進捗は`START_HERE.md`、作業予約は`docs/current-work.md`、履歴は`docs/ai-work-handoff.md`を参照してください。

## 1. 指示の優先順位

1. 現在の明示的なユーザー指示
2. タスクで指定された最新のOwner Source of Truth
3. `GOAL.md`と機械受入条件
4. 本文書とその他のrepo docs

過去のhandoffは履歴証拠であり、最新オーナー方針より優先しません。validator、rights/provenance gate、投稿安全を古いdocsに合わせて弱めてはいけません。

## 2. プロダクト目的

`night_scout`と`liver_manager`の共通Reference-first基盤を構築します。

`registered reference sources -> normalized SourcePost + ordered Media -> understand -> route selection -> media/copy generation -> human review -> READY -> later publish/metrics/PDCA`

当面は自動投稿拡大よりも、参照取得、正確な親子関係、出典、権利、理解、生成、人間Reviewの信頼性を優先します。

## 3. 現行アーキテクチャ規約

- 管理対象: `night_scout`, `liver_manager`
- 参照discovery順: TikTok -> Threads -> X -> YouTube
- 安定期の物理media: X + YouTubeのみ
- X profile discovery: bounded metadata-only `gallery-dl`
- Xの個別status media: source-specific permission後の`yt-dlp`
- YouTube media: `yt-dlp`
- Threads/TikTokの稼働中のdesired route: non-browser
- Threads/TikTokの新規物理mediaは当面deferred
- 比率: direct media 50 / reference text 30 / PDCA 10 / new text 5 / approved clip 5
- geometry: `preserve_source`。9:16強制は明示変換時のみ
- `media_permissions`の最新有効行が再利用mediaのruntime正本
- XのRetweet/quote/第三者postに登録sourceの権限を継承しない
- `WAITING_REVIEW`はworker対象外、`READY`のみworker対象

## 4. アカウント境界

- Night Scout: 夜職女性向け、経験のある論理的なスカウト、一人称は`僕`。
- Liver Manager: TikTok LIVE配信者向け、実務的な女性マネージャー、一人称は`私`。`僕`/`俺`は不可。
- X投稿と`beauty_account`操作は現行Goal対象外。

## 5. 権利・セキュリティ

- secret、cookie、token、storage stateを読み取り・表示・commitしない。
- 公開されていることをmedia再利用許可とみなさない。
- permission evidenceと必要operation flagsがなければdownload/cut/upload/repostしない。
- X権限はsource-specificであり、登録handleと個別status authorの一致が必須。
- 投稿、production Sheets書込み、Cloudinary uploadは明示承認なしに行わない。
- validator閾値、permission/provenance/publish gate、テストassertionを緑化目的で弱めない。

## 6. Git・編集規約

- 明示指示なく`main`へ直接commitしない。
- force push、未承認rebase、reset/clean、未commit差分の破棄をしない。
- 他AI/ユーザーの変更を元に戻さず、共存させる。
- 関連ファイル、呼出関係、型、テストを調査してから最小変更を行う。
- legacy/deprecated pathはX+YouTubeの両アカウントGoldenが揃うまで物理削除せず、非稼働で残す。

## 7. 検証と引き継ぎ

- 変更Pythonのcompile、focused tests、repository regression、Ruff fatal rules、`git diff --check`を実行する。
- 機械受入条件は実production証拠が必要な項目をdry-run/mockでPASSにしない。
- 作業終了時は`START_HERE.md`、`docs/current-work.md`、`docs/ai-work-handoff.md`を同期する。
- `docs/goal-status.json`は正式なevidence collector/evaluator実行時だけ更新する。
