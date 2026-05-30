# Phase 2.14: reference_based Gemini Prompt

**フェーズ**: 2.14  
**ステータス**: 実装中  
**目的**: 収集投稿をベースにしたリライト用Geminiプロンプトをv2に統合する

---

## 概要

`generation_jobs` の各ジョブに対してGemini APIを呼び出し、  
参考投稿の「勝ち要素」を活かした新規投稿文を生成する。

生成された投稿文は `drafts` タブに保存し、  
Phase 2.15 の approval_scorer でスコアリングする。

---

## 2つの生成モード

### reference_based（80%）

参考投稿のスコア・分析結果を入力として与え、その勝ち要素を活かしたリライトを生成する。

入力情報:
- `reference_post.text` — 元テキスト（構造参照用、模倣禁止）
- `reference_post_score.hook_style` — フック手法
- `reference_post_score.content_angle` — コンテンツアングル
- `reference_post_score.why_it_grew` — バズ理由分析
- `reference_post_score.replay_tip` — 再現のヒント
- `reference_post_score.buzz_score` — スコア（参考値）

### original_hypothesis（20%）

アカウントのペルソナ・ジャンル・過去スコアを入力として与え、独自の仮説・視点から投稿を生成する。

---

## 安全ガード

- デフォルトは MOCK_LLM モード（実際のGemini API呼び出しなし）
- `MOCK_LLM=false` かつ `DRY_RUN=false` の場合のみ実API呼び出し
- 文字数ポリシー違反時は最大2回リライト試行
- 2回失敗後は `status=WAITING_REVIEW` で保存し人間確認を促す

---

## 文字数制約

プロンプトに明示する文字数制約:

| プラットフォーム | 推奨上限 | ハード上限 |
|---|---|---|
| X | 120文字 | 140文字 |
| Threads | 500文字 | 800文字 |

---

## 出力フォーマット（Gemini JSON応答）

```json
{
  "content": "投稿本文",
  "title": "タイトル（任意）",
  "cta_text": "CTA文言（任意）",
  "hypothesis": "仮説（original_hypothesisモード時）",
  "media_strategy": "none|reference_image|original_image",
  "generation_notes": "生成メモ"
}
```

---

## 実装ファイル

- `src/generation/reference_based_generator.py` — Gemini呼び出し本体
- `prompts/rewrite_reference.md` — プロンプトテンプレート
- `scripts/generate_from_jobs.py` — CLI

---

## 関連フェーズ

- Phase 2.13: generation_planner（ジョブ供給元）
- Phase 2.15: approval_scorer（スコアリング先）
- Phase 2.16: text_policy（文字数チェック）
