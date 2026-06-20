# Legacy Repo Shutdown Plan

## 概要

- 作成日: 2026-06-20
- 更新日: 2026-06-20（停止完了）
- 目的: 旧3リポジトリの GitHub Actions を停止し、sns-growth-engine への一本化を完了させる

**絶対ルール:**
- 旧 repo は削除しない
- 旧 repo は archive しない（停止後 30日間保留）
- 旧 repo の secret 値を確認・表示・コピーしない

---

## 停止結果 (2026-06-20)

| リポジトリ | workflow 数 | 停止状況 | README 廃止通知 |
|---|---|---|---|
| X_autopost_yoru | 8本 | **disabled_manually ✅** | 追加済み ✅ |
| threads_auto_post_gs | 4本 | **disabled_manually ✅** | 追加済み ✅ |
| threads-liver-coachhing | 8本 | **disabled_manually ✅** | 追加済み ✅ |

**合計 20本 すべて停止済み。**  
Secret 混入チェック: `.env.example` はすべて値が空 ✅

---

## 停止した workflow 一覧

### X_autopost_yoru（8本）

| ID | 名前 | 種別 |
|---|---|---|
| 195039329 | X Auto Post (manual) | 投稿 |
| 195042648 | X Auto Post (queue from Sheet at 14:00 & 18:00 JST) | 投稿スケジューラー |
| 256121872 | コンテンツ収集・生成（夜職 X） | 収集・生成 |
| 268649376 | X Analyze Posts (yorusyoku) | 分析 |
| 268649377 | X Collect Posts (yorusyoku) | 収集 |
| 269714097 | X Cleanup Cloudinary Assets | メディア管理 |
| 269739296 | X Generate Review Rewrites (Gemini) | 生成 |
| 271261963 | X Legacy Tab Auto Post (x_autopost_yoru at 13/16/20/24 JST) | 投稿スケジューラー |

### threads_auto_post_gs（4本）

| ID | 名前 | 種別 |
|---|---|---|
| 188967298 | Threads Auto Post (queue from Sheet at 14:00 & 18:00 JST) | 投稿スケジューラー |
| 256121763 | コンテンツ収集・生成（夜職 Threads） | 収集・生成 |
| 262913430 | Refresh Threads Token | トークン管理 |
| 271675387 | Threads Legacy Tab Auto Post (auto-posttab at 13/16/20/24 JST) | 投稿スケジューラー |

### threads-liver-coachhing（8本）

| ID | 名前 | 種別 |
|---|---|---|
| 195083281 | Threads daily posts | 投稿スケジューラー |
| 256121495 | コンテンツ収集・生成（ライバー Threads） | 収集・生成 |
| 262911644 | Refresh Threads Token | トークン管理 |
| 274316508 | Liver Analyze Posts | 分析 |
| 274316509 | Liver Cleanup Cloudinary Assets | メディア管理 |
| 274316510 | Liver Collect Posts | 収集 |
| 274316511 | Liver Generate Review Rewrites (Gemini) | 生成 |
| 274316512 | Liver Threads Auto Post (queue at 14:00 & 18:00 JST) | 投稿スケジューラー |

---

## Secret 混入チェック結果

| リポジトリ | .env.example | Actions logs | config/json |
|---|---|---|---|
| X_autopost_yoru | 値なし ✅ | 未確認（目視推奨） | 未確認 |
| threads_auto_post_gs | 値なし ✅ | 未確認（目視推奨） | 未確認 |
| threads-liver-coachhing | 値なし ✅ | 未確認（目視推奨） | 未確認 |

Actions logs の目視確認推奨: GitHub → 各 repo → Actions → 最新の実行ログを確認。

---

## GitHub Secrets の扱い

旧 repo の GitHub Secrets は以下のタイミングで削除する。

**削除条件:**
1. 旧 repo の停止を 30日間確認完了
2. 新 repo での本番投稿が安定稼働している
3. 各認証情報の rotate が完了している

**削除手順（各 repo）:**
```
Settings → Secrets and variables → Actions → 各 secret の右側「削除」ボタン
```

**rotate 推奨優先度:**

| 認証情報 | 対象 repo | 優先度 | 理由 |
|---|---|---|---|
| THREADS_ACCESS_TOKEN (night_scout) | threads_auto_post_gs | 高 | 60日期限 |
| THREADS_ACCESS_TOKEN (liver_manager) | threads-liver-coachhing | 高 | 60日期限 |
| X_API_KEY / X_API_SECRET | X_autopost_yoru | 中 | 移行完了後 |
| X_ACCESS_TOKEN / X_ACCESS_TOKEN_SECRET | X_autopost_yoru | 中 | 移行完了後 |
| GCP_SA_JSON (X_autopost_yoru) / SA_JSON_BASE64 | 各 repo | 低 | 年次 |

Threads トークン rotate 注意: `refresh` すると旧トークンが即時無効化される。  
新 repo 側に先に設定してから rotate すること。

---

## 保留・archive スケジュール

| 時期 | アクション |
|---|---|
| 2026-06-20（停止日） | 全 workflow disable 完了 ✅ |
| 2026-07-20（30日後） | archive 可否を判断 |
| 2026-07-20 以降 | archive 後、GitHub Secrets 削除 |

**archive 手順:**
```
各 repo → Settings → Danger Zone → Archive this repository
```
archive すると: コード・履歴保持、workflow 完全停止、Issues/PR 読み取り専用、push 不可。

---

## Rollback 手順（緊急時）

新 repo で問題が発生し、旧 repo を再稼働させる必要がある場合:

```
1. GitHub → 各 repo → Settings → Actions → General → "Allow all actions"
   または Actions タブ → 対象 workflow → "Enable workflow"
2. 旧 repo の GitHub Secrets が有効であることを確認
3. 新 repo の PUBLISH_ENABLED / ALLOW_REAL_X_POST / ALLOW_REAL_THREADS_POST を .env から削除
```

archive 前（30日間）は復旧可能な状態を維持すること。

---

## 関連ドキュメント

- `docs/legacy-repo-migration-audit.md`: 旧 repo 詳細調査
- `docs/credential-migration-plan.md`: 認証情報の移行手順
- `docs/production-launch-checklist.md`: 本番開始チェックリスト
