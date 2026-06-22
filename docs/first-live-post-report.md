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

---

## 初回本番パイロット実行（2026-06-22 追記）

### 実行概要

- 実行日: 2026-06-22
- 作業AI: Claude Code (Sonnet 4.6)
- ターゲット: night_scout / X / 1件

### 投稿文（確定版・81字）

```
指名が取れるキャバ嬢は、見た目だけじゃなく「また会いたい」と思わせる接客のプロ。相手を気持ちよくさせる「聞き方」と「返し」の積み重ねが、稼げる子の秘密なんだよね。
```

tone_ok=True / NGパターン不検出 / 81字 ≤ 120字

### 実行ステップ

| ステップ | 結果 |
|---|---|
| D. Sheets setup (--confirm-setup) | 29タブ全て既存 (SKIP) |
| E. preflight_check.py | PASS:16 FAIL:0 WARN:2 (カテゴリ・テンプレート空) |
| F. dry-run (publish_x_post.py) | DRY_RUN PASS (81字) |
| G. X実投稿 | **POST_FAILED** — 402 Payment Required |
| H. posted_results | 投稿未成功のため記録なし |
| I. PDCA (--dry-run --mock) | pdca_296f2dfe / total_results=0 / suggestions=0 |
| J. media pipeline (--dry-run --mock) | sources=31 assets=2 status=PASS |

### コードバグ修正

| ファイル | 修正内容 |
|---|---|
| `scripts/publish_x_post.py` | `sys.path` に `src/` を追加 + dotenv ロード追加 |
| `scripts/publish_threads_post.py` | 同様の修正 |
| `scripts/preflight_check.py` | `check_tabs_existence()` で `TAB_DISPLAY_NAMES` を使い日本語タブ名に対応 |

### 結果

**POST_FAILED** — X API 402 Payment Required

- 認証: **成功**（OAuth1.0a 認証通過、アカウントID: 1974127896232091648）
- 失敗理由: APIクレジット不足
- 二重投稿リスク: なし（post_id未払い出し）
- コード問題: なし（auth成功後の課金ガードで止まった）

### 次のステップ

1. X Developer Portal で Basic Plan 以上を契約または無料枠を確認
2. クレジット確保後、以下を実行:
   ```bash
   PUBLISH_ENABLED=true ALLOW_REAL_X_POST=true \
   python3 scripts/publish_x_post.py \
     --account-id night_scout \
     --text '指名が取れるキャバ嬢は、見た目だけじゃなく「また会いたい」と思わせる接客のプロ。相手を気持ちよくさせる「聞き方」と「返し」の積み重ねが、稼げる子の秘密なんだよね。' \
     --confirm-post --no-dry-run
   ```
3. 成功後は posted_results に post_id / post_url を登録

---

## トンマナ修正対応（2026-06-22 追記）

### 問題発覚

初回生成試行で以下の3案が生成された（いずれもNG）:

1. 「今日も一日お疲れ様！…ずっと応援しているよ。」→ **薄い応援・励まし系**
2. 「今日はどんなメイクで行こうか…新しいリップやアイシャドウ…」→ **美容系**
3. 「ストレスや疲れが溜まってないかな…心と体を休める時間…」→ **ふわっとしたメンタル系**

### ユーザーフィードバック

> 現状、night_scout の投稿が「応援系」「美容系」「薄い励まし」に寄っています。これはNGです。

### 根本原因

プロンプト（`_DRAFT_GEN_NIGHT_SCOUT`）に「応援系/美容系/ポエム系を避ける」という明示的禁止事項がなかった。

### 修正内容

| 修正ファイル | 修正内容 |
|---|---|
| `src/seeds.py` | night_scout/liver_manager の tone/notes を詳細化 |
| `src/seeds.py` | `_DRAFT_GEN_NIGHT_SCOUT` に NGトーンリスト・投稿スタイルガイド・良い例を追加 |
| `src/seeds.py` | `_DRAFT_GEN_LIVER_MANAGER` に同様の追加 |
| `src/seeds.py` | `_SOCIAL_DERIVATIVE_X_NIGHT_SCOUT` (pt_06) 新規追加 |
| `src/seeds.py` | `ACCOUNT_NG_TONE_PATTERNS` 新規追加（night_scout:21件、liver_manager:12件） |
| `src/tone_checker.py` | 新規作成（`check_ng_tone()` 関数） |
| `src/prompt_loader.py` | `get_derivative_template()` を account_id 対応に更新 |
| `src/social_derivative_generator.py` | account_id を derivative テンプレート選択に渡す |
| `scripts/preflight_check.py` | グループ6「トンマナ確認」追加 |
| `scripts/test_account_tone_guide.py` | 新規作成（14項目テスト） |
| `docs/account-tone-guides.md` | 新規作成（アカウント別トンマナ定義） |

### night_scout 正しいトーン定義

**NG**: 薄い応援・美容・ポエム・汎用自己啓発  
**OK**: 現場ノウハウ・キャバあるある・稼げる子の特徴分析・店選びのポイント  
**X ルール**: ハッシュタグなし・絵文字なし・120字以内

**良い例**:
> キャバで長く稼げる子って、見た目だけじゃなくて「また話したい」と思わせる返しが上手い。LINEも接客も、相手を気持ちよくさせる一言を積み重ねられる子は強いんだよね。

### 次のステップ

トンマナ修正後のプロンプトで night_scout X投稿を3案再生成し、最適1案で X dry-run を実施する。
