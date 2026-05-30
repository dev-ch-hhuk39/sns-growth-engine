# Phase 2.15: AI Approval Scoring

**フェーズ**: 2.15  
**ステータス**: 実装中  
**目的**: 投稿案に対してAIがスコアリングし人間レビューを支援する

---

## 概要

生成された投稿文（`drafts` タブ）に対して複数の観点でスコアリングを行い、  
自動承認可否を判定する。

`publish_decision.py`（既存）との役割分担:
- `approval_scorer.py`（新）: 生成時点のAIスコアリング。drafts.status = `SCORED` / `WAITING_REVIEW`
- `publish_decision.py`（既存）: 承認済み下書きのキューイング判定。変更しない。

---

## スコア体系

### buzz_potential_score（0〜100）

バズ可能性スコア。以下の要素から算出:
- reference の buzz_score をベースに
- hook_style の有効性
- 文字数の適切性
- CTA有無

### conversion_potential_score（0〜100）

コンバージョン可能性。以下を考慮:
- CTA有無・明確さ
- 夜職・ライバー等のターゲットペルソナへの訴求強度
- プロフィールクリック・LINE誘導への誘い

### brand_risk_score（0〜1、低いほどよい）

ブランドリスク。以下を考慮:
- imitation_risk（高いほどリスク）
- 参考投稿テキストとの類似度（文字列レベル）

### imitation_risk（low / medium / high）

模倣リスク判定。cloudinary_client.assess_imitation_risk と同じロジック。

### media_reuse_risk（low / medium / high）

メディア再利用リスク。media_asset.media_reuse_risk を引き継ぐ。

---

## confidence_level（HIGH / MEDIUM / LOW）

総合的な投稿品質の信頼度。

| レベル | 条件 |
|---|---|
| HIGH | buzz_potential_score >= 70 かつ brand_risk_score <= 0.3 かつ text_policy = OK |
| MEDIUM | buzz_potential_score >= 50 かつ brand_risk_score <= 0.5 |
| LOW | それ以外 |

---

## ai_publish_recommendation

AIによる投稿推奨判定。

| 値 | 条件 |
|---|---|
| `recommend` | confidence_level = HIGH かつ imitation_risk != high |
| `review` | MEDIUM または imitation_risk = high |
| `reject` | confidence_level = LOW または brand_risk_score > 0.7 |

---

## auto_approve 判定

`auto_approve_threshold`（generation_jobs で設定）と buzz_potential_score を比較し、  
閾値以上の場合は status = `APPROVED`、それ以外は `WAITING_REVIEW` にする。

---

## 実装ファイル

- `src/generation/approval_scorer.py` — スコアリング本体

---

## 関連フェーズ

- Phase 2.14: reference_based_generator（入力元）
- Phase 2.16: text_policy（文字数チェック連携）
