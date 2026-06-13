# 実LLM生成テスト手順

Phase 8以降で、MOCK_LLM=false による実LLM生成を安全に行うための手順書。

## 前提条件（全て満たすこと）

- [ ] `PUBLISH_ENABLED=false`
- [ ] `ALLOW_REAL_X_POST=false`
- [ ] `ALLOW_REAL_THREADS_POST=false`
- [ ] `MOCK_LLM=true` → `false` に変更する（生成時のみ）
- [ ] 有効なLLM APIキー設定済み（値は表示しない）
- [ ] beauty_account は draft_only のまま
- [ ] content safety check が通ること

## preflight実行

```bash
# night_scout / X
python3 scripts/preflight_real_llm_generation.py --account-id night_scout --platform x --mock

# beauty_account / Threads（WAITING_REVIEW止まりを確認）
python3 scripts/preflight_real_llm_generation.py --account-id beauty_account --platform threads --mock
```

## 実LLM生成の手順（次フェーズ以降）

1. preflight で PASS/WARN のみであることを確認
2. `MOCK_LLM=false` に変更
3. 1件だけ生成（`--count 1`）
4. content safety check を通す
5. `MOCK_LLM=true` に戻す
6. 生成結果を確認（WAITING_REVIEW）
7. human review → approve or reject

## 禁止事項

- 実LLM生成後の自動投稿
- beauty_account の生成結果を READY/POSTED にする
- APIキーや生成コンテンツをログに出力する
- forbidden_keywords を含む生成結果を保存する
