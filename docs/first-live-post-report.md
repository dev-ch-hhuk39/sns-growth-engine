# First Live Post Report

## 概要

- Date: 2026-06-18
- 担当AI: Claude Code (Sonnet 4.6)
- 実運用フェーズ: SNS実運用開始フェーズ（初回）
- 結果: **READY_WITH_MISSING_CREDENTIALS**

## 実施内容

### G: 投稿テキスト生成

参照ソース: `src_ns_yt_cand_009` (@kyaba_camera YouTube)

取得コンテンツテーマ:
1. 有名キャバ嬢のLINE管理・顧客関係術
2. 昼職から転身してロッポンギTOPになった女性の1日
3. 高卒・極貧・いじめ経験を乗り越えた最強ホステス

生成投稿テキスト（確定版・99字）:
```
夜職で伸びる子に共通するのは、LINEの返し方が上手いこと。"また話したい"と思わせる会話ができる子は強い。学歴や見た目より、長く稼ぐには会話力が大事なんだよね。磨ける力だから、今からでも伸ばせる。
```

初期案（123字、参考）:
```
夜職で伸びる子に共通するのは、LINEの返し方が上手いこと。"また話したい"と感じさせる会話ができる子は、数字が後からついてくる。スカウトしてきた子を見てると、学歴や見た目より"会話力"の方が長期的な稼ぎに直結してると感じる。磨ける力だから強い。
```

投稿ルール確認:
- [x] スカウト視点（断定的でない語り口）
- [x] 99字（140字以内）
- [x] 夜職/キャバ女性向け
- [x] スカウト側の知見
- [x] 参考元の丸パクリなし（テーマ参照のみ、文章は独自生成）
- [x] 稼げる煽りなし
- [x] 不安煽りなし
- [x] 誇大表現なし
- [x] URLなし / mediaなし

### H: Preflight 確認

**media asset preflight:**
```
python3 scripts/preflight_media_assets.py --account-id night_scout --mock --dry-run
```
結果: `status=PASS` (sources=31, assets=2)
- 実download/cut/upload/post: 未実行

**X publisher dry-run:**
```
python3 scripts/publish_x_post.py --account-id night_scout \
  --text "<投稿文>" --confirm-post --dry-run
```
結果: `status=DRY_RUN` (99字)

**Threads publisher dry-run:**
```
python3 scripts/publish_threads_post.py --account-id night_scout \
  --text "<投稿文>" --confirm-post --dry-run
```
結果: `status=DRY_RUN` (99字) [WARN: 1行のみ、問題なし]

preflight 総合: **PASS**

### I: 実投稿 → BLOCKED (認証情報未設定)

X credentials 確認:
- `X_API_KEY`: 未設定
- `X_API_SECRET`: 未設定
- `X_ACCESS_TOKEN`: 未設定
- `X_ACCESS_TOKEN_SECRET`: 未設定

Threads credentials 確認:
- `THREADS_ACCESS_TOKEN`: 未設定
- `THREADS_USER_ID`: 未設定

判定: **READY_WITH_MISSING_CREDENTIALS**

Publisher dry-run 確認 (--dry-run --confirm-post):
```
→ status: DRY_RUN
→ message: DRY_RUN: would post to X (38字)
```
投稿ロジック自体は正常動作確認済み。

### J: posted_results 登録 (dry-run)

```
python3 scripts/import_posted_results.py --mock --dry-run
```
結果: `[DRY_RUN] 書き込みをスキップしました。`

### K: PDCA dry-run

```
python3 scripts/run_pdca_cycle.py --account-id night_scout --platform x --days 7 --dry-run --mock --generate-next-plan
```

結果:
- pdca_run_id: `pdca_8bcc26d2`
- total_results: 1 (mock)
- suggestion_count: 1 (WAITING_REVIEW)
- next_jobs_count: 3 (PLANNED)
- 改善提案: 全て `active=False` / `WAITING_REVIEW` (自動適用禁止)

### L: 安全フラグ確認

| フラグ | 状態 |
|---|---|
| `PUBLISH_ENABLED` | NOT_SET |
| `ALLOW_REAL_X_POST` | NOT_SET |
| `ALLOW_REAL_THREADS_POST` | NOT_SET |
| `ALLOW_CLOUDINARY_UPLOAD` | NOT_SET |
| `ALLOW_TRANSCRIPTION_API` | NOT_SET |

`.env` ファイル: コミット対象外確認済み (`.gitignore` に記載)

## 最終ステータス

**READY_WITH_MISSING_CREDENTIALS**

不足している認証情報:
- `X_API_KEY`
- `X_API_SECRET`
- `X_ACCESS_TOKEN`
- `X_ACCESS_TOKEN_SECRET`

または:
- `THREADS_ACCESS_TOKEN`
- `THREADS_USER_ID`

## 次のステップ（実投稿手順）

### Step 1: .env に認証情報を設定

X の場合:
```
X_API_KEY=<your_api_key>
X_API_SECRET=<your_api_secret>
X_ACCESS_TOKEN=<your_access_token>
X_ACCESS_TOKEN_SECRET=<your_access_token_secret>
ALLOW_REAL_X_POST=true
PUBLISH_ENABLED=true
```

Threads の場合:
```
THREADS_ACCESS_TOKEN=<your_access_token>
THREADS_USER_ID=<your_user_id>
ALLOW_REAL_THREADS_POST=true
PUBLISH_ENABLED=true
```

### Step 2: dry-run で最終確認

```bash
python3 scripts/publish_x_post.py \
  --account-id night_scout \
  --text '夜職で伸びる子に共通するのは、LINEの返し方が上手いこと。"また話したい"と思わせる会話ができる子は強い。学歴や見た目より、長く稼ぐには会話力が大事なんだよね。磨ける力だから、今からでも伸ばせる。' \
  --confirm-post --dry-run
```

### Step 3: 実投稿（X）

```bash
PUBLISH_ENABLED=true ALLOW_REAL_X_POST=true \
python3 scripts/publish_x_post.py \
  --account-id night_scout \
  --text '夜職で伸びる子に共通するのは、LINEの返し方が上手いこと。"また話したい"と思わせる会話ができる子は強い。学歴や見た目より、長く稼ぐには会話力が大事なんだよね。磨ける力だから、今からでも伸ばせる。' \
  --confirm-post --no-dry-run
```

### Step 4: metrics 確認スケジュール

| 時点 | 確認内容 |
|---|---|
| 投稿直後 | post_id / post_url を posted_results に登録 |
| 24時間後 | いいね / リポスト / リプライ / インプレッション |
| 48時間後 | エンゲージメント率を PDCA に入力し次回プランを生成 |

```bash
# 48時間後の PDCA
python3 scripts/run_pdca_cycle.py \
  --account-id night_scout --platform x \
  --days 7 --generate-next-plan
```

## 実行していないこと

- 実投稿: 未実行
- download/cut/upload: 未実行
- beauty_account active化: なし
- secrets表示: なし
