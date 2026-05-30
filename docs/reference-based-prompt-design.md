# reference_based プロンプト設計

**更新日**: 2026-05-31

---

## 設計原則

1. **構造を活かし、表現は変える**: 元投稿のテキストを引用せず、フック・アングル・構成のみ参照する
2. **プラットフォーム最適化**: X は短く鋭く、Threads は読み物として展開する
3. **文字数は上限に余裕を持たせる**: ハード上限の85%以内を目安に
4. **JSON出力を強制**: 後続パースが容易になるよう構造化レスポンスを要求する

---

## reference_based プロンプト構造

```
## あなたの役割
あなたはSNSコンテンツライターです。
以下の「参考投稿分析」を読み、その勝ち要素を活かした
新しい投稿文を{account_id}向けに書いてください。

## アカウント情報
- アカウントID: {account_id}
- プラットフォーム: {platform}
- ターゲットペルソナ: {target_persona}
- トーン: {tone}
- ジャンル: {main_genre}

## 参考投稿分析
- フックスタイル: {hook_style}
- コンテンツアングル: {content_angle}
- バズ理由: {why_it_grew}
- 再現ヒント: {replay_tip}
- バズスコア: {buzz_score}

## 文字数制約
- {platform == "x" ? "120文字以内（絶対に140文字を超えないこと）" : "500文字以内（推奨）、800文字を超えないこと"}

## 禁止事項
- 参考投稿のテキストを直接コピー・引用しないこと
- 元投稿のアカウント名・固有名詞をそのまま使わないこと

## 出力形式（JSON）
{"content":"投稿本文","title":"タイトル（任意、省略可）","cta_text":"CTA（省略可）","media_strategy":"none","generation_notes":"生成メモ"}
```

---

## original_hypothesis プロンプト構造

```
## あなたの役割
あなたはSNSコンテンツライターです。
以下の「アカウント情報」と「仮説テーマ」をもとに、
オリジナルの投稿文を書いてください。

## アカウント情報
- アカウントID: {account_id}
- プラットフォーム: {platform}
- ターゲットペルソナ: {target_persona}
- トーン: {tone}
- ジャンル: {main_genre}

## 仮説テーマ（任意）
{hypothesis_hint}

## 文字数制約
- {platform == "x" ? "120文字以内（絶対に140文字を超えないこと）" : "500文字以内（推奨）、800文字を超えないこと"}

## 出力形式（JSON）
{"content":"投稿本文","title":"タイトル（任意）","cta_text":"CTA（省略可）","hypothesis":"採用した仮説","media_strategy":"none","generation_notes":"生成メモ"}
```

---

## MOCKレスポンス（MOCK_LLM=true 時）

```json
{
  "content": "[MOCK] テスト投稿文です。参考投稿の勝ち要素を活かしました。",
  "title": "テスト下書き",
  "cta_text": "",
  "hypothesis": "",
  "media_strategy": "none",
  "generation_notes": "mock response"
}
```

---

## リライトループ

```
generate() → check_text_policy()
  OK → 完了
  WARN/FAIL → retry 1回目
    OK → 完了
    WARN/FAIL → retry 2回目
      OK → 完了
      WARN/FAIL → status=WAITING_REVIEW で保存（人間確認）
```
