# Production Launch Checklist

SNS自動投稿システム v2 の初回運用開始チェックリストです。

## Current Release

- PR: https://github.com/dev-ch-hhuk39/sns-growth-engine/pull/1
- Feature branch: `feature/codex-final-production-audit`
- Feature HEAD before docs rollout commit: `cfd31823f7ffb72f622d37bba9580e3284e2ac5b`
- Base: `origin/main` at `1edf83abc93623be83abe05bd0a9e12e2ff14d00`
- Status before merge: merge-ready after tests and dry-run/BLOCKED checks
- Merge result: PR #1 squash merged
- Production pipeline merge SHA: `759af859a4d70d9ec1105f8d70f1c4ea893f29db`
- main verification: minimum tests 4 / 4 PASS, dry-run / BLOCKED 5 / 5 PASS
- Follow-up PR: https://github.com/dev-ch-hhuk39/sns-growth-engine/pull/2
- Follow-up PR status: merge attempt blocked by connector approval credits; branch remains pushed for manual merge.
- Follow-up fix: `run_real_smoke_plan.py --platform threads` uses Threads readiness checks.

## Merge Gates

- [x] PR created
- [x] Conflict-sensitive files reviewed
- [x] Diff limited to `config`, `docs`, `scripts`, and `src`
- [x] `.env`, cookie, token, API key, image/video artifacts not included
- [x] `.claude/plans/` not committed
- [x] Phase13 minimum tests PASS
- [x] Phase9-13 regression PASS
- [x] dry-run / BLOCKED checks PASS
- [x] no real fetch/download/cut/upload/post executed
- [x] `beauty_account` remains WAITING_REVIEW / draft-only
- [x] `learning_rules active=true` not introduced
- [x] source priority auto-change not introduced

## Source Candidate Gates

- [x] fixed user-provided URLs: 54 / 54
- [x] `night_scout`: 31 sources
- [x] `liver_manager`: 24 sources
- [x] `beauty_account`: 36 sources
- [x] query sources: 37
- [x] note/article sources: 6
- [x] all production candidates inactive
- [x] all production candidates fetch disabled
- [x] download/cut/upload defaults false

## Required First Smoke Order

1. tool doctor
2. source registry validate
3. source candidate review
4. mock fetch dry-run
5. source_to_post pipeline mock dry-run
6. media preflight dry-run
7. publisher dry-run
8. posted_results import dry-run
9. PDCA dry-run
10. human-approved confirm-fetch for one source only
11. no download/cut/upload/post after confirm-fetch
12. separate approval for download/cut/upload/post
13. first one-post smoke stops at publisher dry-run
14. real post requires another explicit approval

## Commands

```bash
python3 scripts/check_source_fetcher_tools.py --dry-run
python3 scripts/manage_source_accounts.py --validate --dry-run
python3 scripts/review_source_candidates.py --account-id night_scout --dry-run
python3 scripts/fetch_source_posts.py --account-id night_scout --platform x --mock --dry-run
python3 scripts/run_source_to_post_pipeline.py --account-id night_scout --platform x --mock --dry-run
python3 scripts/preflight_media_assets.py --account-id night_scout --mock --dry-run
python3 scripts/publish_x_post.py --account-id night_scout --confirm-post --dry-run
python3 scripts/import_posted_results.py --mock --dry-run
python3 scripts/run_pdca_cycle.py --account-id night_scout --platform x --days 7 --dry-run --mock --generate-next-plan
```

## BLOCKED Checks

```bash
python3 scripts/fetch_source_posts.py --account-id night_scout --platform x --fetch --dry-run
python3 scripts/download_media_assets.py --account-id night_scout --download --dry-run
python3 scripts/cut_video_clips.py --account-id liver_manager --cut --dry-run
python3 scripts/upload_media_assets.py --account-id night_scout --upload --dry-run
```

Each command must print `BLOCKED`.

## Remaining WARN

- Real smoke readiness may report NOT_READY until credentials are configured.
- Sheets test-write is intentionally not part of this automated rollout.
- Abstract base classes may still contain `NotImplementedError`.
- Legacy docs may reference older blocked real-post behavior.
- PR #2 may remain unmerged until GitHub connector credits/approval are restored or a human merges it.

## Human Next Steps

1. Open the PR and review the diff.
2. Confirm source candidates that may be used for real fetch.
3. Run the manual smoke sequence in `docs/manual-smoke-test-sequence.md`.
4. Approve at most one `confirm-fetch` source for the first real collection check.
5. Keep download/cut/upload/post disabled until a separate approval round.
