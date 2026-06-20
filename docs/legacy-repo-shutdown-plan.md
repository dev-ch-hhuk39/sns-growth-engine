# Legacy Repo Shutdown Plan

## 概要

- 作成日: 2026-06-20
- 目的: 旧3リポジトリの GitHub Actions を停止し、sns-growth-engine への一本化を完了させる
- 前提: 新 repo で実投稿が動作確認済みであること（認証情報設定 + dry-run PASS が条件）

**絶対ルール:**
- 旧 repo は削除しない
- 旧 repo は archive しない（停止後 30日間保留）
- 旧 repo の secret 値を確認・表示・コピーしない
- 旧 repo の .env 値を表示しない

---

## 停止順序（推奨）

重複投稿リスクが最も高いものから停止する。

1. **threads-liver-coachhing**（8回/日、liver_manager/Threads）
2. **X_autopost_yoru**（6回/日、night_scout/X）
3. **threads_auto_post_gs**（2回/日、night_scout/Threads）

---

## 停止手順

### 共通手順（各リポジトリで繰り返す）

```
1. https://github.com/dev-ch-hhuk39/<repo-name>/settings/actions
   → Actions permissions: "Disable actions" を選択して Save

   または個別 workflow を無効化する場合:
2. https://github.com/dev-ch-hhuk39/<repo-name>/actions
   → 対象 workflow を選択 → "..." → "Disable workflow"
```

### Step 1: threads-liver-coachhing の停止

対象 workflow: `threads-daily.yml`（8スケジュール）

```
URL: https://github.com/dev-ch-hhuk39/threads-liver-coachhing/actions
```

停止後の確認:
- [ ] 翌日 00:00 / 03:00 / 06:00 / 09:00 / 12:00 / 15:00 / 18:00 / 21:00 JST で実行されていないこと
- [ ] `last_run.txt` の更新が止まっていること（24時間後に確認）

### Step 2: X_autopost_yoru の停止

対象 workflow:
- `x_time_window.yml`（13:45 / 17:45 JST）
- `x_legacy_tab_time_window.yml`（12:45 / 15:45 / 19:45 / 23:45 JST）

```
URL: https://github.com/dev-ch-hhuk39/X_autopost_yoru/actions
```

停止後の確認:
- [ ] 翌日の全 6スロットで実行されていないこと
- [ ] night_scout の X 投稿が止まっていること

### Step 3: threads_auto_post_gs の停止

対象 workflow: `threads-daily.yml`（13:45 / 17:45 JST）

```
URL: https://github.com/dev-ch-hhuk39/threads_auto_post_gs/actions
```

停止後の確認:
- [ ] 翌日 13:45 / 17:45 JST で実行されていないこと
- [ ] night_scout の Threads 投稿が止まっていること

---

## 停止確認チェックリスト

全リポジトリ停止後、以下を確認してから新 repo の本番投稿を開始する。

```
[ ] threads-liver-coachhing: workflow disabled, 24時間実行なし確認
[ ] X_autopost_yoru: 両 workflow disabled, 24時間実行なし確認
[ ] threads_auto_post_gs: workflow disabled, 24時間実行なし確認
[ ] 各アカウントの SNS タイムラインで意図しない投稿がないこと確認
[ ] docs/production-launch-checklist.md の "Legacy Repos Stopped" チェックを完了
```

---

## 停止後の保留期間

| 経過時間 | アクション |
|---|---|
| 停止直後〜7日 | 各アカウントのタイムラインを監視（重複・意図しない投稿がないか） |
| 7〜30日 | 新 repo の本番投稿が安定稼働していることを確認 |
| 30日後以降 | archive 検討（リポジトリ設定 → Archive this repository） |

archive すると:
- コードと履歴は保持される
- workflow は完全停止
- Issues/PR が読み取り専用になる
- プッシュ不可（fork は可能）

---

## Secret rotate のタイミング

旧 repo の停止が確認できたら、以下のタイミングで secret rotate を実施する。

### X 認証情報 (night_scout)

旧 repo 停止確認後 + 新 repo での X 投稿が安定稼働後:

```
X_API_KEY / X_API_SECRET / X_ACCESS_TOKEN / X_ACCESS_TOKEN_SECRET
```

rotate 方法:
- https://developer.twitter.com/en/portal/ から新しい Access Token を生成
- 新 repo の `.env` に新しい値を設定
- 旧 repo の GitHub Secrets は削除（Settings → Secrets and variables → Actions → Remove）

### Threads 認証情報

#### night_scout (threads_auto_post_gs)

```
THREADS_ACCESS_TOKEN / THREADS_USER_ID
```

rotate 後は旧トークンが即時無効化されるため、必ず新 repo 側に先に設定してから rotate する。

#### liver_manager (threads-liver-coachhing)

```
THREADS_ACCESS_TOKEN / THREADS_USER_ID  ← night_scout とは別の値
```

同様に新 repo 側に先に設定してから rotate する。

---

## rollback 手順（緊急時）

新 repo で問題が発生し、旧 repo を再稼働させる必要がある場合:

1. 旧 repo の workflow を re-enable する
   - Settings → Actions → General → Allow all actions
   または Actions タブから個別 workflow を Enable
2. 旧 repo の GitHub Secrets が有効であることを確認（期限切れの場合は再設定が必要）
3. 新 repo の `PUBLISH_ENABLED` / `ALLOW_REAL_X_POST` / `ALLOW_REAL_THREADS_POST` を `.env` から削除

旧 repo は archive せず保留期間中は復旧可能な状態を維持すること。

---

## 関連ドキュメント

- `docs/legacy-repo-migration-audit.md`: 旧 repo の詳細調査結果
- `docs/credential-migration-plan.md`: 認証情報の移行手順
- `docs/production-launch-checklist.md`: 新 repo 本番開始チェックリスト
