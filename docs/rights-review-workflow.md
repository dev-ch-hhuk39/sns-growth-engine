# 権利レビューワークフロー（Phase 2.28）

**作成日**: 2026-06-06

---

## 概要（Phase 2.28 変更内容）

Phase 2.28 で権利ゲートの動作を変更した。

### 変更前（Phase 2.24）

```
rights_status=unknown → queue に追加しない（完全ブロック）
```

### 変更後（Phase 2.28）

```
rights_status=unknown     → WAITING_REVIEW で queue に追加
                            rights_review_required=true を付与
rights_status=not_allowed → queue に追加しない（完全ブロック・変更なし）
media_reuse_risk=high     → queue に追加しない（完全ブロック・変更なし）
```

---

## フロー

```
1. generate_from_video_clips.py を実行
   → rights_status=unknown のクリップ:
       drafts: WAITING_REVIEW
       social_derivatives: WAITING_REVIEW
       queue: WAITING_REVIEW + rights_review_required=true
       video_clip_candidates: rights_review_required=true

2. review_queue.py で確認
   → [RIGHTS WARNING] が表示される
   → rights_status / source_video_url / media_reuse_risk が表示される

3. 人間が video_clip_candidates タブで確認
   → rights_status を allowed / not_allowed に更新
   → permission_status を granted / denied / not_required に更新

4. approve_queue.py で --approve を試みる
   → rights_review_required=true のアイテムは READY 昇格がブロックされる
   → rights_status を allowed に更新してから再生成が必要

5. generate_from_video_clips.py を再実行（rights_status=allowed のクリップ）
   → 新しい queue アイテムが rights_review_required=false で追加される

6. approve_queue.py で --approve → READY 昇格
```

---

## フィールド説明

| フィールド | 場所 | 値 | 意味 |
|---|---|---|---|
| `rights_review_required` | queue | `true` | READY 昇格前に権利確認必要 |
| `rights_review_required` | video_clip_candidates | `true` | 投稿文生成時に権利未確認 |
| `rights_status` | video_clip_candidates, queue | `unknown` | 人間未確認 |
| `rights_status` | video_clip_candidates, queue | `allowed` | 使用権確認済み |
| `rights_status` | video_clip_candidates, queue | `not_allowed` | 使用不可（完全ブロック） |

---

## approve_queue.py のブロック条件

```python
if rights_review_required == "true" or rights_status == "unknown":
    # READY 昇格をブロック
```

---

## なぜ unknown を complete block から WAITING_REVIEW に変えたか

- **Before**: unknown のクリップは draft も queue も見えない → 存在を把握できない
- **After**: WAITING_REVIEW で見えるようにする → 人間が確認しやすい
- **安全性**: approve_queue.py が READY 昇格をブロック → 誤投稿は防がれる

---

## 参考

- `docs/video-clip-rights-policy.md` - 権利ポリシー定義
- `src/generation/video_clip_generator.py` - 実装
- `scripts/approve_queue.py` - 承認時のブロックロジック
