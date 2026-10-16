# SNS Growth Engine — P0 release-candidate acceptance and finish line

Date: 2026-10-14 JST. Package baseline: Mac-only `f4bf7e21e96f1d561e6414a03e044c488e5c1df6`.

## Decision

**Phase 6AH–6AL code is an offline release rehearsal, not a completed SNS posting service or an operational SQLite migration.** The new orchestrator reduces separate steps but deliberately never grants real posting, Google Sheets writes, or live SQLite authority. A clean local smoke test **cannot replace production acceptance**.

## Implemented together

| Phase | Offline capability | Hard restriction |
|---|---|---|
| 6AH | Validate strict metadata-only queue and posted-results snapshot; detect duplicate IDs, unsafe media, uncertain outcomes, missing result proof | Source is untrusted, no rights or provider identity grant |
| 6AI | Compare two distinct, close-in-time captures; reject changed identity, status, source and export drift | Both captures can be incomplete/unauthenticated |
| 6AJ | Atomically stage HMAC-only metadata in temporary **in-memory** SQLite and independently read back | Reject disk DB, no operational DB migration |
| 6AK | Combine preflight, parity, shadow and existing local P0 SQLite one-use CAS in one rehearsal | Real publisher not wired; all claims end BLOCKED |
| 6AL | One-shot guarded installer on the exact original Mac checkout or its verified AH/AJ descendants | Refuse dirty/divergent sources; full QA and Git commit locally only |

## Run after integrating on Mac

```sh
# 1. Unzip the combined bundle OUTSIDE the Git repository.
# 2. Run from an authorized local terminal (no GitHub Actions):
bash /path/to/sns_p0_phase6ah_al_release_bundle/apply_to_local_mac.sh \
  '/Users/hayatoa/claudecodeプロジェクトディレクトリ/dev/SNS自動投稿システム/v2-chatgpt-local-noactions-20261013'
```

The installer verifies SHA-256 files, the exact expected branch and ancestor, status cleanliness, existing installed stage checksums and any unexpected changes. It runs each included unit suite, the **existing repository's focused and full offline quality gates**, records actual test counts, and commits **locally only after PASS**. Failure before commit restores replaced handoff/QA files and deletes only files it installed; no push, deployment or SNS/Google request is attempted. If a guard fails, inspect the divergence; **do not bypass the guard or delete unknown files**.

After integration, a second explicit, offline-only check can use authorized *minimal metadata* snapshots:

```sh
python3 scripts/rehearse_p0_release_candidate.py \
  --before /private/operator/before.json \
  --after /private/operator/after.json --simulate \
  --output /tmp/sns-p0-release-rehearsal-unique.json
```

Both inputs must be separate absolute files. No captions, media URLs, credentials, or original source evidence are accepted in the minimal metadata exports. The tool reads the frozen repo AST writer inventory and uses existing blocked CAS journal and shadow modules. A rehearsal only uses `sqlite3.connect(':memory:')`, and the report never contains original IDs. Its exit code is **always 2**, including when `local_rehearsal_status=PASS_LOCAL_NOT_PRODUCTION`.

## Completion criteria for actual production readiness

No additional Phase-letter numbering is required for these gates. Work directly through this table and verify each criterion against independent operational evidence.

| Gate | Evidence required | Current state |
|---|---|---|
| 1. Integrated source | Install combined patch on actual clean Mac branch, run full test suite, record commit SHA | **Not verified** (Desktop Commander usage cap) |
| 2. Functional business acceptance | Create/review/schedule text and image/video variants; validate account routing, dry-run, editorial approval, failures and retries across real app/UI | **Not verified end to end** |
| 3. Single source of truth | Determine authoritative production queue; reconcile 165 historical direct Sheets mutation calls, including 71 historical P0; discover *external* writers, then freeze/cut over one family at a time | **Not completed**; counts are historical AST baseline, not live inventory |
| 4. Identity, ACL, rights | Operator-controlled scoped service principal, access revocation, authenticated source export; media rights and per-account release evidence | **Not verified** |
| 5. Concurrency and recovery | One-use claim owning the **actual** publisher sink, backup & tested restore, no blind repost after ambiguous delivery, tested rollback and audit | **Not connected to production** |
| 6. Real production canary | Operator-authorized Threads text post, independent readback of provider post ID/URL, queue + result consistency and no duplicates | **Not performed** |
| 7. Media canary | Independent publish-time rights/identity checks and authorized image/video live tests, without disabling existing Media SAFE STOP | **Not performed** |
| 8. Production learning | 24h/72h/168h live metrics, per-account attribution and verified strategy change consumption | **Not performed** |

The actual provider tests, real data migration and release owner approvals must be completed on the authorized operational systems. A local installation or a mock test is never automatic permission to publish or cut over. The shared VPS operations owner retains server-side execution, backup, restore, monitoring, and rollback control. GitHub Actions stays disabled under the existing free-tier workflow policy.

## Test evidence scope

- Original 6AH: 27 isolated unit tests.
- Original 6AI/AJ: 35 isolated unit tests.
- New 6AK/AL: 19 additional integration/negative tests, including source drift, contradictory writer inventory, media rights, CAS bypass attempts, unsafe acknowledgements and output-scrubbing.
- Final combined isolated suite and guarded installer mock-checkout tests are documented in `TEST_REPORT.md` inside this package.
- **Mac's repository-wide test suite is not run in this isolated sandbox.** It runs as part of the guarded installer on the actual checkout.

## Avoiding repetitive development

If the local install passes, the next activity is **not another generic feature phase**. Use this acceptance table, collect the missing actual operational evidence, and fix only defects preventing a named acceptance gate. That is the shortest route from a large offline codebase to a production service.

- Full Mac offline QA: 992/992 PASS. Source, rights, provider and live writer cutover **remain blocked**.
