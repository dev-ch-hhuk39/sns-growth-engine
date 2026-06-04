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

## 権利ゲートルール

以下の条件のいずれかに該当する場合、クリップは **queue に追加されない**（draft は WAITING_REVIEW として保存）。

```
rights_status IN ("unknown", "not_allowed")
OR media_reuse_risk == "high"
```

### なぜ `unknown` もブロックするか

`unknown` = 人間レビューが未実施の状態。自動投稿すると著作権侵害になる可能性があるため、**デフォルトでブロック**する設計。

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

`src/generation/video_clip_generator.py` の `_is_rights_blocked()` 関数がこれを強制する。

```python
def _is_rights_blocked(candidate: dict) -> bool:
    rights = str(candidate.get("rights_status", "unknown")).lower()
    risk = str(candidate.get("media_reuse_risk", "low")).lower()
    if rights in ("unknown", "not_allowed"):
        return True
    if risk == "high":
        return True
    return False
```

この関数は `save_clip_generation_result()` 内で呼ばれ、True の場合は queue への追加をスキップする。
