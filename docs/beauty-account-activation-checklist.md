# beauty_account 活性化チェックリスト

beauty_account を active 化するための前提条件と承認手順。

## 現在のステータス

**beauty_account は現時点で active 化しません。**

draft_only のまま運用し、以下の条件がすべて満たされた時点でのみ active 化を検討する。

## 必要条件（全て満たすこと）

- [ ] thread_series 生成 10件以上
- [ ] human review 10件以上完了
- [ ] 全レビュー済み投稿の medical/ad risk = low
- [ ] forbidden_keywords なし（全件）
- [ ] before/after 断定表現なし
- [ ] 価格/施術/クリニック断定なし
- [ ] CTA 過多なし（1投稿あたり1CTA以下を推奨）
- [ ] content quality score >= 7.0 （平均）

## 承認手順

1. `check_beauty_activation_readiness.py` で全条件を確認
2. ユーザーによる明示的な承認（口頭またはGitHub issue）
3. `beauty_account.json` の `draft_only: false` への変更（ユーザーが行う）
4. `allow_real_post: true` への変更は **別途** ユーザー承認が必要

## 医療広告・薬機法リスク

- 「確実に○○になる」「△△を治す」等の断定表現は禁止
- 施術名・クリニック名・価格の具体的記載は禁止
- before/after 比較は禁止
- 医薬品・医療機器の効能・効果の記載は禁止

## 確認CLI

```bash
python3 scripts/check_beauty_activation_readiness.py --account-id beauty_account --mock
```

このCLIは現時点では常に BLOCKED / NOT_READY を返します。
