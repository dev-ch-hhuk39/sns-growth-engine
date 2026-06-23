# Threads 初回実投稿レポート

## 概要

- Date: 2026-06-23
- 担当AI: Claude Code (Sonnet 4.6)
- アカウント: night_scout (`@kyaba_consul_mizu`)
- プラットフォーム: Threads
- 結果: **SUCCESS**

---

## 投稿内容

```
キャバで指名が取れる子って、見た目だけじゃなくて「また会いたい」と思わせる接客ができる子。

相手を気持ちよくさせる聞き方と返しを積み重ねられる子は、長く稼げるんだよね。
```

- 文字数: 86字
- メディア: なし
- post_id: `18127402414723102`
- posted_url: https://www.threads.com/@kyaba_consul_mizu/post/DZ6Drm5k9SL
- posted_at: 2026-06-23T00:00:00Z

---

## 投稿プロセス

### 前提条件チェック

| チェック項目 | 結果 |
|---|---|
| PUBLISH_ENABLED=true | ✅ 設定済み |
| ALLOW_REAL_THREADS_POST=true | ✅ 設定済み |
| THREADS_ACCESS_TOKEN_NIGHT_SCOUT | ✅ 設定済み (len=189) |
| THREADS_USER_ID_NIGHT_SCOUT | ✅ 設定済み |
| テキスト検証 | ✅ PASS (86字) |
| beauty_account ガード | ✅ 対象外 |
| X 投稿ブロック | ✅ 維持 (402 Payment Required) |

### 実行手順

1. `dry_run=True` で検証（PASS）
2. `dry_run=False` で実投稿
3. Threads Graph API 2ステップ:
   - `POST /{user_id}/threads` → container_id 取得
   - `POST /{user_id}/threads_publish` → post_id 取得
4. `GET /{post_id}?fields=permalink` → posted_url 取得（API経由）
5. posted_results を Sheets に保存

### posted_results 保存

- result_id: `r-5da1d941`
- draft_id: `cli_direct_threads_first_post`
- Sheets: posted_results タブに書き込み済み

---

## バグ修正（この投稿で発見・修正）

### 1. Threads post_url 生成方法の修正

**問題**: 数値 user_id を使った URL（`https://www.threads.com/@17841...`）は無効。

**修正**: Threads Graph API から permalink を取得するアプローチに変更。

```python
# Before (bug): 数値 user_id を URL に直接埋め込む
def _build_post_url(user_id: str, post_id: str) -> str:
    return f"https://www.threads.com/@{user_id}/post/{post_id}"

# After (fix): API から permalink を取得
def _try_fetch_permalink(post_id: str, access_token: str) -> str | None:
    url = f"{THREADS_API_BASE}/{post_id}"
    params = {"fields": "permalink", "access_token": access_token}
    resp = requests.get(url, params=params, timeout=10)
    return resp.json().get("permalink")
```

### 2. PublishResult.is_dry_run_ok @property 欠落の修正

**問題**: `@property` がなかったため、`result.is_dry_run_ok` が bound method オブジェクト（常に truthy）を返していた。実投稿時も「DRY_RUN」と表示される誤動作。

**修正**: `@property` デコレータを追加。

```python
# Before (bug):
def is_dry_run_ok(self) -> bool:
    return self.dry_run and self.success

# After (fix):
@property
def is_dry_run_ok(self) -> bool:
    return self.dry_run and self.success
```

### 3. GitHub Actions workflow env渡し漏れの修正

**問題**: `content-pilot-publish.yml` に共通 secret のみ設定。
`THREADS_ACCESS_TOKEN_NIGHT_SCOUT` 等のアカウント固有 secret が渡されず、
`threads_credentials.py` が fallback の共通 token を参照（または BLOCKED_MISSING_CREDENTIALS）していた。

**修正**: アカウント固有 secrets 8本を `env:` ブロックに追加。

---

## PDCA 分析（48h 計測前）

### 投稿評価 (初回)

| 項目 | 評価 |
|---|---|
| フック | キャバで指名が取れる子は〜（スカウト視点、断定的でない） |
| 本文 | 接客力・聞き方・返しを具体化 |
| CTA | なし（初回観察優先） |
| 文字数 | 86字（推奨 80〜120字内） |
| トーン | 夜職従事者への実践的アドバイス |

### 次回改善候補 (WAITING_REVIEW)

1. CTA テスト: フォロー誘導フレーズの A/B
2. 時間帯テスト: 投稿タイミング最適化
3. 形式テスト: 箇条書き vs 文章形式

---

## 次のアクション

- [ ] 48h 後に Threads インサイトから impressions / likes / replies を確認
- [ ] `posted_results` の metrics_status を MEASURED に更新
- [ ] PDCA 分析を実施し、次回投稿テキストを生成
- [ ] X 投稿: 402 Payment Required 解消待ち（外部ブロッカー維持）

---

## X 投稿状況

X は API 課金プラン未加入により 402 Payment Required。
投稿テキストを `data/manual_post_queue.json` に保存済み（status=retry_ready）。
手動投稿または課金プラン加入後に対応。

---

## 関連ファイル

- `src/publishers/threads_publisher.py` — ThreadsPublisher 実装
- `src/publishers/base.py` — PublishResult @property 修正
- `.github/workflows/content-pilot-publish.yml` — account-specific secrets 追加
- `data/threads_night_scout_first_post.json` — 初回投稿記録（git管理外）
- `scripts/save_first_threads_post.py` — posted_results 保存スクリプト
- `docs/youtube-tiktok-clipping-runbook.md` — 次フェーズ（clip pipeline）手順書
