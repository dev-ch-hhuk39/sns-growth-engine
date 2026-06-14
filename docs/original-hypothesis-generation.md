# Original Hypothesis Generation（Phase 10）

## 概要

`src/generation/original_hypothesis_generator.py` が実装するオリジナル仮説生成機能。

トレンドや仮説をもとに、各アカウントのトーンに合わせたオリジナル投稿下書きを生成する。

## アカウント別トーン定義

| account_id | tone_label | 説明 |
|---|---|---|
| night_scout | 夜の情報収集者 | ライバー・エンタメ・夜の発見をカジュアルに伝える |
| liver_manager | ライバーマネージャー | ライバー育成・管理のプロとして信頼感のある発信 |
| beauty_account | ビューティーコンシェルジュ | 美容・コスメを丁寧に紹介（医療広告・薬機法注意） |

## 使い方

```python
from src.generation.original_hypothesis_generator import OriginalHypothesisGenerator

gen = OriginalHypothesisGenerator()
result = gen.generate(
    account_id="night_scout",
    platform="x",
    post_type="text_post",
    topic="深夜のライバー配信トレンド",
    hypothesis="深夜2時台の配信は視聴者が集中しやすい",
    count=2,
    mock=True,
)
print(result["status"])   # OK
print(len(result["drafts"]))  # 2
```

## 安全設計

| 条件 | 挙動 |
|---|---|
| beauty_account | status=WAITING_REVIEW、drafts に beauty フラグ付き |
| dry_run=True | status=DRY_RUN、draft_count=0 |
| X の文字数超過（280字超） | safety_warnings に警告追加 |

## CLI

```bash
# dry_run（生成確認のみ）
python scripts/generate_original_hypothesis_posts.py \
  --account-id night_scout \
  --platform x \
  --topic "夜の配信トレンド" \
  --hypothesis "深夜枠は単価が高い" \
  --count 3 \
  --dry-run

# mock 生成
python scripts/generate_original_hypothesis_posts.py \
  --account-id night_scout \
  --platform x \
  --mock
```

## 返り値

| フィールド | 説明 |
|---|---|
| status | OK / WAITING_REVIEW / DRY_RUN / ERROR |
| account_id | 対象アカウント |
| drafts | 生成下書きリスト |
| draft_count | 下書き数 |
| safety_warnings | 安全警告リスト |
