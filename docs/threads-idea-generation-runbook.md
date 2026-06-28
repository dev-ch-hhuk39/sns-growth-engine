# Threads Idea Generation Runbook

Date: 2026-06-28

参考投稿・切り抜き候補から Threads 投稿案を生成するための標準 CLI 入口。
生成専用で投稿はしない。本 doc は薄い入口で、詳細は既存 doc を参照する。

## 標準 CLI

| CLI | 役割 | 既定 |
|---|---|---|
| `generate_threads_ideas_from_references.py` | Threads 投稿案生成（参考 / 切り抜き） | PLAN_ONLY |

## 使い方

```bash
# 参考投稿から
python3 scripts/generate_threads_ideas_from_references.py --account-id night_scout --platform threads --source references
# 切り抜きから
python3 scripts/generate_threads_ideas_from_references.py --account-id night_scout --platform threads --source clips
# 本番生成
python3 scripts/generate_threads_ideas_from_references.py --account-id night_scout --source references --apply --confirm-generate
```

- 主要フラグ: `--account-id`{night_scout,liver_manager,beauty_account} / `--platform`（既定 threads） / `--source`{references,clips}（既定 references） / `--top-n`（既定 3） / `--apply` / `--confirm-generate`。
- 投稿先は `threads` のみ。X は将来対応のみで本 CLI では生成しない。

## 自動投稿されない保証（多層防御）

投稿案は `WAITING_REVIEW` で書き込まれる。これは worker の `ELIGIBLE_STATUSES`={WAITING_REVIEW, PLANNED} に含まれるが、自動投稿はされない:

1. 本 CLI も委譲先も投稿処理を一切呼ばない（生成専用）。
2. 実投稿は別経路 worker の三重ゲート（`--confirm-real-post` かつ `PUBLISH_ENABLED=true` かつ `ALLOW_REAL_THREADS_POST=true`）が必要。現状すべて禁止。
3. 承認は `approve_queue.py` で人間が WAITING_REVIEW → READY/REJECTED に行う。

詳細な生成姿勢マトリクス（経路別の status / generation_mode / verify 境界）は
[reference-pipeline-runbook.md](reference-pipeline-runbook.md) の「生成姿勢マトリクス」を参照。

## 安全方針

- `beauty_account` は対象外（draft_only）。生成された投稿候補は自動投稿対象にしない。

## 関連 doc

- [reference-based-prompt-design.md](reference-based-prompt-design.md) — 参考ベース prompt 設計
- [approve-queue-usage.md](approve-queue-usage.md) — 人間承認フロー
- [reference-pipeline-runbook.md](reference-pipeline-runbook.md) — 全 CLI 横断の安全設計・生成姿勢マトリクス
