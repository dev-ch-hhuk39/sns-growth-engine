# 動画クリップ権利ポリシー

**作成日**: 2026-06-04

---

## 概要

動画クリップを SNS 投稿に転用する場合、著作権・肖像権・プラットフォーム利用規約に関するリスクを評価し、問題のあるコンテンツの自動投稿を防ぐ。

---

## 権利関連フィールド

| フィールド | 型 | 値 | 意味 |
|---|---|---|---|
| `rights_status` | string | `unknown` | デフォルト。人間未確認 |
| | | `allowed` | 使用権確認済み |
| | | `not_allowed` | 使用不可と確認済み |
| `permission_status` | string | `unknown` | デフォルト。許可状態未確認 |
| | | `granted` | クリエイターから許可取得済み |
| | | `denied` | クリエイターに拒否された |
| | | `not_required` | 許可不要（自社コンテンツ等） |
| `media_reuse_risk` | string | `low` | 再利用リスク低 |
| | | `medium` | 再利用リスク中（要確認） |
| | | `high` | 再利用リスク高（ブロック対象） |
| `imitation_risk` | string | `low` / `medium` / `high` | 模倣リスク |

---

## 権利ゲートルール（Phase 2.28 改訂）

### 完全ブロック条件

以下の条件のいずれかに該当する場合、クリップは **queue に追加されない**（draft は WAITING_REVIEW として保存）。

```
rights_status == "not_allowed"
OR media_reuse_risk == "high"
```

### 条件付き通過（Phase 2.28 変更）

```
rights_status == "unknown"
→ WAITING_REVIEW で queue に追加
  rights_review_required=true を付与
  approve_queue.py が READY 昇格をブロック
```

### Phase 2.28 変更の理由

- **Before（Phase 2.24）**: `unknown` は完全ブロック → draft/queue が見えない
- **After（Phase 2.28）**: `unknown` は WAITING_REVIEW で visible → 人間が確認しやすい
- **安全性は維持**: `approve_queue.py` が `rights_review_required=true` のアイテムの READY 昇格をブロック

---

## 権利確認フロー

```
1. analyze_video_clips.py でクリップ候補生成
   → rights_status=unknown, permission_status=unknown（デフォルト）

2. 人間がクリップ候補を確認
   → rights_status を allowed / not_allowed に更新
   → permission_status を granted / denied / not_required に更新

3. rights_status=allowed かつ media_reuse_risk != high のクリップのみ
   → generate_from_video_clips.py で投稿文生成
   → queue に WAITING_REVIEW で追加

4. 人間が投稿文を確認 → approve_queue.py で READY に昇格
```

---

## 禁止事項

- `rights_status=unknown` のままのクリップを queue に追加してはならない
- `not_allowed` なコンテンツを投稿してはならない
- クリエイターの明示的な許可なく `media_reuse_risk=high` のコンテンツを使用してはならない

---

## 実装上の保証

`src/generation/video_clip_generator.py` の `_is_rights_blocked()` / `_needs_rights_review()` 関数がこれを強制する。

```python
def _is_rights_blocked(candidate: dict) -> bool:
    """queue 追加を完全ブロックする条件（Phase 2.28）。"""
    rights = str(candidate.get("rights_status", "unknown")).lower()
    risk = str(candidate.get("media_reuse_risk", "low")).lower()
    if rights == "not_allowed":
        return True
    if risk == "high":
        return True
    return False


def _needs_rights_review(candidate: dict) -> bool:
    """rights_status=unknown の場合、人間レビューが必要。"""
    rights = str(candidate.get("rights_status", "unknown")).lower()
    return rights == "unknown"
```

`approve_queue.py` は `rights_review_required=true` のアイテムの READY 昇格をブロックする。
