# Phase 2.16: 文字数制限強化

**フェーズ**: 2.16  
**ステータス**: 実装中  
**目的**: 全プラットフォームの文字数制限をコード・プロンプト双方で徹底する

---

## 制約値

| プラットフォーム | soft_limit（推奨） | hard_limit（超過禁止） |
|---|---|---|
| X | 120文字 | 140文字 |
| Threads | 500文字 | 800文字 |

注: `text_policy.py` では Threads の soft を 600 / hard を 800 と定義されているが、  
生成プロンプトでは保守的に 500文字を推奨上限として指示する。

---

## 適用箇所

### 1. 生成プロンプト（Phase 2.14）

Gemini への指示文に文字数制約を明記する。

```
# 文字数制約
- X の場合: 120文字以内（絶対に140文字を超えないこと）
- Threads の場合: 500文字以内（推奨）、800文字を超えないこと
```

### 2. 生成後チェック（Phase 2.14 リライトループ）

- 生成された投稿文に `check_text_policy()` を適用
- `status=WARN` または `FAIL` の場合は最大2回リライト
- 2回失敗後は `status=WAITING_REVIEW` で保存

### 3. approval_scorer（Phase 2.15）

- `text_policy_status` を drafts に保存
- `FAIL` の場合は `confidence_level` を LOW に下げる

### 4. social_derivatives

- `char_count` / `text_policy_status` を保存
- `FAIL` の場合はキュー登録をブロック

---

## text_policy.py（既存）

`src/text_policy.py` に実装済み:

```python
check_text_policy(text: str, platform: str) -> TextPolicyResult
# TextPolicyResult.status: "OK" | "WARN" | "FAIL"
# TextPolicyResult.char_count: int
# TextPolicyResult.message: str
```

---

## 実装ファイル

- `src/text_policy.py` — 既存（変更なし）
- `src/generation/reference_based_generator.py` — プロンプト制約 + リライトループ
- `src/generation/approval_scorer.py` — text_policy_status 評価
