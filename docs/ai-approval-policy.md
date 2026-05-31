# AI 承認ポリシー

**更新日**: 2026-05-31

---

## 概要

生成された投稿案は `approval_scorer.py` によって自動スコアリングされ、  
人間レビューが必要かどうかを判定する。

---

## スコアリングフロー

```
generated draft
  ↓
approval_scorer.score_generated_post()
  ├─ buzz_potential_score (0〜100)
  ├─ conversion_potential_score (0〜100)
  ├─ brand_risk_score (0.0〜1.0)
  ├─ imitation_risk (low/medium/high)
  ├─ media_reuse_risk (low/medium/high)
  ├─ text_policy_status (OK/WARN/FAIL)
  ├─ confidence_level (HIGH/MEDIUM/LOW)
  └─ ai_publish_recommendation (recommend/review/reject)
```

---

## confidence_level 判定基準

| レベル | 条件 |
|---|---|
| HIGH | buzz_potential_score >= 70 AND brand_risk_score <= 0.3 AND text_policy_status = "OK" |
| MEDIUM | buzz_potential_score >= 50 AND brand_risk_score <= 0.5 |
| LOW | 上記以外（スコア不足 または リスク高） |

---

## ai_publish_recommendation 判定基準

| 値 | 条件 |
|---|---|
| `recommend` | confidence_level = HIGH AND imitation_risk != "high" |
| `review` | confidence_level = MEDIUM OR imitation_risk = "high" |
| `reject` | confidence_level = LOW OR brand_risk_score > 0.7 |

---

## auto_approve 判定

generation_jobs の `auto_approve_threshold` と比較:
- buzz_potential_score >= auto_approve_threshold → `APPROVED`
- それ以外 → `WAITING_REVIEW`

デフォルト閾値: 80.0

---

## publish_decision.py との関係

`approval_scorer.py`（新）と `publish_decision.py`（既存）は独立した責務を持つ:

| モジュール | 責務 | 動作タイミング |
|---|---|---|
| `approval_scorer.py` | 生成時点の品質スコアリング | 投稿文生成直後 |
| `publish_decision.py` | 承認済み下書きのキュー登録判定 | 投稿実行前 |

**`publish_decision.py` は変更しない。** スコア結果を `drafts` テーブルに保存するのみ。

---

## drafts テーブルへの保存項目

Phase 2.15 で `drafts` タブに以下の列を追加:
- `buzz_potential_score`
- `conversion_potential_score`
- `confidence_level`
- `ai_publish_recommendation`
- `generation_mode`
- `hypothesis`
- `media_strategy`
- `imitation_risk`
- `media_reuse_risk`

---

## Phase 2.17: コンテンツテーマガード

`score_generated_post()` に `account_config` 引数を追加。  
`apply_content_theme_guard()` が呼ばれ、禁止キーワード検出時は:

- `ai_publish_recommendation` → `"reject"`
- `confidence_level` → `"LOW"`
- `brand_risk_score` → +0.4（最大1.0）
- `suggested_status` → `"WAITING_REVIEW"`

詳細: `docs/phase2-17-content-theme-guard.md`
