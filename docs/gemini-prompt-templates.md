# Gemini プロンプトテンプレート仕様

## テンプレート一覧

| template_name | account_id | 用途 |
|---|---|---|
| `draft_generation_night_scout_v1` | night_scout | 夜職スカウト向け下書き生成 |
| `draft_generation_liver_manager_v1` | liver_manager | ライバーマネージャー向け下書き生成 |
| `draft_scoring_v1` | （全共通） | 既存下書きのスコアリング |
| `social_derivative_x_v1` | （全共通） | X（旧Twitter）投稿用派生テキスト生成 |
| `social_derivative_threads_v1` | （全共通） | Threads 投稿用派生テキスト生成 |

---

## 変数置換構文

プロンプト内の `{{variable_name}}` が実行時に置換されます。

| 変数 | 内容 |
|---|---|
| `{{account_id}}` | アカウントID |
| `{{account_name}}` | アカウント名 |
| `{{target_persona}}` | ターゲットペルソナ |
| `{{tone}}` | トンマナ |
| `{{line_url}}` | LINE URL |
| `{{cta_text}}` | CTA 文言 |
| `{{category_name}}` | カテゴリ名 |
| `{{category_description}}` | カテゴリ説明 |
| `{{reference_summary}}` | 参考投稿本文 |
| `{{reference_hook}}` | 参考投稿のフック |
| `{{reference_pain}}` | 参考投稿の読者の痛み |
| `{{reference_desire}}` | 参考投稿の読者の欲求 |
| `{{reusable_pattern}}` | 再利用パターン |
| `{{platform}}` | 対象プラットフォーム |
| `{{title}}` | 投稿タイトル（derivative 用） |
| `{{body_md}}` | 投稿本文（derivative 用） |

---

## Gemini 出力 JSON 仕様

### 下書き生成 (draft_generation_*)

```json
{
  "title": "投稿タイトル（20文字以内が理想）",
  "body_md": "Threads形式の本文。500文字以内。",
  "content": "body_md のプレーンテキスト版",
  "cta_text": "自然なCTA文言",
  "thumbnail_copy": "サムネコピー（不要なら空文字）",
  "pv_score": 80,
  "cv_score": 70,
  "brand_risk_score": 15,
  "score": 78,
  "score_reason": "スコア算出理由",
  "ai_review": "改善提案",
  "post_mode": "buzz | trust | cv | mixed"
}
```

### 派生投稿生成 (social_derivative_*)

```json
{
  "platform": "x または threads",
  "text": "投稿文",
  "hashtags": "ハッシュタグ（不要なら空文字）",
  "status": "READY または HUMAN_REVIEW または REJECT",
  "reason": "ステータス判断理由"
}
```

---

## テンプレートの更新方法

1. Google Sheets の `prompt_templates` タブを開く
2. 該当行の `prompt_text` セルを編集
3. 次回の generate_drafts 実行時から新テンプレートが使われる

Seeds（`src/seeds.py`）はフォールバック用。Sheets が優先されます。

---

## 共通 NG ルール（全テンプレート）

- 怪しい・情報商材っぽい表現
- 女性を雑に扱う・夜職を軽く見る表現
- ライバーを軽く扱う表現
- 「絶対稼げる」などの無責任な煽り
- 他店舗・他スカウト・他事務所を名指しで攻撃
- 差別的表現・SNS コミュニティガイドライン違反
