# START HERE

## 文書情報

- updated_at: 2026-07-25T15:15:00+09:00
- updated_by: Antigravity
- document_branch: `ops/wp3b-diagnostic-fidelity`
- related_pr: `TBD`
- audited_main_sha: `304a2c126223199a0d3554ed78509ea3652d2198`
- audited_origin_main_sha: `304a2c126223199a0d3554ed78509ea3652d2198`
- PR #26: MERGED
- PR #26 merge commit: `304a2c126223199a0d3554ed78509ea3652d2198`
- post-merge CI: 30146464509 / SUCCESS
- WP3 production read-only run: 30146525043 / FAILURE
- current task: WP3-B diagnostic fidelity
- current branch: ops/wp3b-diagnostic-fidelity
- document_status: `PRODUCTION_BASELINE_FAILED_DIAGNOSTICS_IN_PROGRESS`

Confirmed hard failure:
- parent integrity failures: 6

Confirmed blockers:
- Liver Threads source: MISSING

Unverified due workflow secret injection gap:
- Night Threads credential
- Liver Threads credential
- Cloudinary credentials

Additional diagnostics:
- stale inflight slots: 2
- Liver permission partial coverage:
  missing_or_invalid_source_id = src_lm_yt_cand_001

この文書内に、文書自身を含む最終commit SHAを固定値で記録しない。
最新のPR headはGitHubのPR #26を参照する。

## 最終Goal

`GOAL.md`と`config/goal_acceptance.json`で定義された35項目を、実証証拠付きで35/35 PASSにする。

## 現在確認済みの完了事項

- strict public validatorは維持されている
- permission gateは維持されている
- media captionの外部モデル呼び出しは1 run最大1回、timeout 25秒
- rejected candidateはvalidatorを弱めず`NO_ELIGIBLE_CANDIDATE`として処理される
- dispatch-only media workflowはschedule障害として誤検知されない
- Liver投稿なしmedia preparation run `29893298582`はsuccess
- Night投稿なしmedia preparation run `29893929836`はsuccess
- 上記2件では実投稿ゲートはfalse
- 上記2件は実投稿成功の証拠ではない

## 実装済みだが本番証拠不足

- Night Scout text-only pipeline
- Liver Manager text-only pipeline
- source acquisitionの一部
- transcription
- source-grounded caption generation
- media candidate preparation
- slot idempotency
- quarantine
- next-candidate selection
- backend failover
- schedule recoveryのコードとテスト
- direct media posting経路
- generated clip posting経路

各項目は、コードが存在することと本番Goalを満たすことを区別する。

## 未確認または未達

- text-onlyの現在の資格情報状態
- text-only READY在庫
- text-only no-post理由
- Night direct media Goal用READY在庫
- Night generated clip Goal用READY在庫
- Liver direct media Goal用READY在庫
- Liver generated clip Goal用READY在庫
- Night direct media実Threads投稿
- Night generated clip実Threads投稿
- Liver direct media実Threads投稿
- Liver generated clip実Threads投稿
- 全投稿の本文・メディア一致証拠
- 全10スロットの本番経路検証
- schedule delay recoveryの最終main証拠
- Goal 35/35

## Goal対象外・実行禁止

- Xへの実投稿
- X schedule
- `beauty_account`操作

これらを`NOT_IMPLEMENTED`としてGoal残作業へ含めない。

## 外部ブロッカー

- Liver Manager用の承認済み第三者Threads source account URL: `UNVERIFIED`
- Threads token再認可の必要性: `UNVERIFIED`
- 必要sourceのpermission ledger状態: `UNVERIFIED`

存在しないと断定せず、WP3のread-only検証で確認する。

## 正しい残作業順序

1. Work Package 3の残存検証
3. Work Package 4: Goal固有media inventory作成
4. Work Package 5: 4本のproduction canary
5. Work Package 6: 最終テスト、証跡生成、35/35評価

## Work Package 3の残存検証

投稿ゲートをfalseにしたまま、以下を確認する。

- Google Sheets schema
- 63-check production verifier
- text-only資格情報
- text-only READY在庫
- text-only no-post理由
- Night source accountとsource post
- Liver Manager用Threads source account URLの存在
- YouTube/TikTok source
- Threads provider routing
- TikTok fallback
- permission ledger
- duplicate queue
- stale slot
- posted_save_failed_count

## Work Package 4

各アカウントについて、投稿せずに次を1件ずつ作成する。

- validator-approved direct media READY asset
- transcript-grounded generated clip READY asset

合計4件のGoal用READY inventoryを作成する。

## Work Package 5

次の順序で最大1件ずつ実投稿する。

1. Night direct media
2. Night generated clip
3. Liver direct media
4. Liver generated clip

各投稿でThreads permalink、Cloudinary asset、Sheets、slot、queue、caption alignmentを確認する。

## Work Package 6

- 全テスト
- compile
- Ruff
- mypy
- dependency audit
- license audit
- gitleaks
- GitHub Actions
- production verifier
- Goal evidence生成
- `evaluate_goal.py --json`
- 35/35 PASS
- mainとorigin/main一致

## docs/goal-status.jsonの取り扱いについて

docs/goal-status.jsonは旧監査時点のsnapshotであり、現在のmainを示す最新評価ではない。
WP6でmachine-readable evidence collectorとevaluate_goal.pyを実行した時点で再生成する。
それまではSHAだけを手作業で更新しない。

## 次のAIの開始手順

1. `git fetch origin`
2. `git status --short`
3. `git branch --show-current`
4. `git rev-parse HEAD`
5. `git rev-parse origin/main`
6. `AGENTS.md`を読む
7. `START_HERE.md`を読む
8. `docs/current-work.md`を読む
9. `docs/ai-work-handoff.md`の最新記録を読む
10. 指示された作業範囲だけを実行する
