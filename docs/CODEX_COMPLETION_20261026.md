# SNS Growth Engine — Codex 2026-10-26 implementation and live audit

## Authority, scope and custody

The owner's 2026-10-26 attachment explicitly supersedes the old no-Codex/no-VPS-development instructions and includes all three managed accounts. Normal operation should migrate away from hosted Actions; protected-main `pr-gate` and signed P0 post approval remain mandatory. No production acceptance criteria are waived. X publishing remains disabled.

Source worktree: `/Users/hayatoa/Projects/sns-growth-engine-bank-acceptance-20261024`, branch `chatgpt/sns-bank-acceptance-20261024`, HEAD `41838cf518206f4aaa067e87fd6f38e96afa78a5`. A fresh fetch confirmed main `fc1a9306da974da1b27f968c7a6d073bd098383a`.

Implementation is isolated at `/private/tmp/sns-growth-engine-completion-20261026`, branch `codex/sns-production-completion-20261026`. The source worktree's five untracked renewal prototypes were audited and copied, not staged, overwritten or discarded. Their original SHA-256 manifest is `/private/tmp/sns-original-token-renewal-sha256.json`; a subsequent comparison confirmed all five unchanged. The older Oct-12 worktree and unpushed `9b9891e` were not reapplied onto the newer product.

## Implemented

### Token renewal

The existing prototype is completed locally; no duplicate credential store, provider account or database is introduced.

- A mode-0600, exclusive, no-symlink PREPARED record is file-fsynced and directory-fsynced **before** the refresh request. A killed process or lost response therefore leaves a durable no-retry barrier. Failure to persist the barrier prevents dispatch.
- Legacy `.refresh-unknown-night_scout` evidence has no automated clear path. The success path may remove only this invocation's exact inode/nonce after verified token persistence, not an earlier operator/unknown record.
- Read current official Meta token metadata; require the pinned app/user identity, verified issue and expiry times, unexpired token and minimum refresh age. Actual provider expiry determines whether renewal is due; a stale local expiry cannot authorize refresh.
- Before saving, recheck the refreshed user's ID/handle/app, increased expiry, returned TTL and retention of existing scopes. Reuse `threads_token_store.store_token` for atomic private storage, preserve account/user/app identity, and verify the resolved saved token without printing it.
- Main CLI handles selected accounts independently. A quarantined Night result remains visibly BLOCKED while other accounts can be inspected independently. Missing/invalid data never becomes a valid refresh.
- Scope remains the fixed official HTTPS endpoint with Bearer authentication and denied redirects. No token is put in the refresh URL or command arguments. No GitHub Secrets mutation, publisher, paid API or Sheets writer is involved.
- The weekly systemd unit remains a **source artifact**, not activated. Its bounded 600-second budget covers the lock wait and three accounts' bounded requests. It requires posting OFF and retains the existing service sandbox/store path.

### Review sync

` sns_local_publication_review_job.py` also previously created its marker only inside an exception handler. It now persists intent before starting the first write-capable subprocess. SIGKILL/power loss after a possible write cannot bypass the next-run quarantine. Both sync and decision readbacks must pass before only the current run's inode/nonce is completed. Old review quarantine remains a hard stop; source changes do not release the live writer or its timer.

### Regression failures found in inherited work

The baseline run reported 5 failed scripts, all caused by one inherited change: `sns_failclosed_unapproved_ready.py` had added an exact one-row `update_queue_item` call without registering it in the frozen Sheets mutation manifest. Code review confirmed its pinned hash/account/original-text scope, no existing approval/result/media, posting-OFF requirement and readback checks. One reviewed callsite is now registered and classified as P0 queue/review work. The inventory assertions and fail-closed cutover conditions are unchanged. All five affected scripts pass.

A working-tree Gitleaks scan found a historical Git SHA near a key-like documentation label. GitHub's official Git commit endpoint confirmed the value is a real revision. The label was clarified; the full SHA remains, and no new secret-scan suppression or broad exclusion was added.

## Delivery

Implementation commit `b8764cd35415a8382080e267afb58b4f1a14e46f` is published on the dedicated branch. [PR #472](https://github.com/dev-ch-hhuk39/sns-growth-engine/pull/472) contains the inherited operations work plus this completion change. Main `fc1a930` was merged normally; conflicting progress-document prefixes were combined while retaining the main Aftercare handoff. No Python, config or workflow content changed during this integration. Current required-check and merge state is authoritative on the PR.

## Local verification

- Full `run_local_quality_gate.py --mode full`: **PASS**.
- Repository regression: **1,092/1,092 scripts**, zero failures; the existing 8 external credential/network probes and 3 optional local-tool probes excluded, no new exclusions.
- Workflow static safety: **619 PASS / 0 FAIL**, 64 workflows. The previously reported 620 was an earlier source state; this is the measured current count.
- Renewal prototype 5 cases, crash/persistence/account isolation 12, lifecycle watchdog 5, timer contracts 3, review writer 9: PASS.
- Ruff fatal rules, compileall, unstaged/staged diff checks, branch-history Gitleaks and redacted working-tree Gitleaks: PASS.
- Full report: `/private/tmp/sns-20261026-final-quality.json`; detailed logs and repository JSON under `/private/tmp/sns-20261026-final-quality-logs/`.
- After direct owner approval, the exact five-file payload passed **22 offline tests** on the existing VPS Python runtime, using an empty environment in `/tmp/sns-renewal-offline-Ypa6CJqu`: renewal 5, crash/persistence/account isolation 12, watchdog 5. No production credentials were loaded. The source was pushed as `b8764cd`; [PR #472](https://github.com/dev-ch-hhuk39/sns-growth-engine/pull/472) runs the protected PR checks. No scheduled or production workflow was manually dispatched.

## Live evidence (all times JST, 2026-10-26)

| Item | Current evidence | Assessment |
| --- | --- | --- |
| Main protection | GitHub API: enforced admins, strict `pr-gate`, pull-request rule retained | Verified, unchanged |
| Running SNS release | `94b744f431199ea52e9444aa02552b83c982bdff`; previous `7be8dc6cd66670ee38438354b22ec91487f7e7f2` | New development code not deployed |
| Posting / token barrier | Existing official expiry service requires posting OFF; Night unknown marker still mode 0600; renewal timer disabled | No refresh/retry/post executed |
| Tokens, 11:20:22 | Official read-only watchdog: all 3 valid, ID matched, about 17.21 days left | Expiry monitoring works; renewal still not live |
| Review, 11:20:33 | 2063 queue / 1652 review / 1645 reviewable, missing=0, drift=0, acknowledged feedback=10, unverified=0 | Fresh independent read-only consistency PASS; writer remains quarantined/disabled |
| READY, 11:25:56 | Night 3/3, Liver 3/3, Beauty 1/1 for next 24h | Fresh read-only PASS; not proof of 30-item Bank or publishing |
| VPS filesystem | 8,628,527,104 available bytes (~8.04GiB), 84% used; RAM 1957MiB | **Below unchanged 9GiB release floor** |
| SNS storage | releases 5,973,786,624 bytes, shared 17,096,704; pip cache ~86KiB; HF cache ~565MB | No sufficiently large proven-disposable cache; no deletion performed |
| Release retention | Eight current release markers dated Oct 23–24 | Still under 7-day grace; no forced release prune or dedup |
| Runtime dependency | Live setuptools 79.0.1 | OSV API returns 3 advisory records; pinned 84.1.0 returns 0, but fixed version is not deployed |
| R2 backup | Actual `chadult-r2-offsite-backup.service` success at 09:52:27 | Successful last backup; not a new restore drill |
| R2 health | Actual `chadult-r2-offsite-health.service` success at 11:01:02; last backup within 36h | PASS; stale-lock history was not treated as a current lock |
| R2 capacity | 10:17:35 capacity audit: 6,206,752,561 bytes, 400 snapshots, 0 stale tags; internal budget 8GB, forecast 40.2d | Normal repository budget; not an account-wide free-tier guarantee |
| Shared retention | Last retention service result exit 3 at 07:53:56 | Not repaired/deleted here; protection/retention remains intact |
| Hosted schedules | API state + fetched main YAML: 13 operations schedules **plus 1 old scheduled CI**, total **14** | Do not disable CI as a whole; branch removes only CI schedule after protected merge |

One comprehensive read-only readiness diagnostic was stopped after discovering the VPS lacks `jq`. It produced no accepted Bank/media result. Only that transient audit was stopped; the three existing READY/review/expiry timers were independently confirmed active. No claim is made that Bank was freshly recounted. The prior 8/9/30 figures and the 48 `PENDING_HUMAN_QA` local drafts are historical/unaccepted inputs, not current accepted reserves.

## Per-account acceptance checkpoint

`Source tested` below is code evidence; it never substitutes for production rollout proof.

| Capability | Night | Liver | Beauty |
| --- | --- | --- | --- |
| Discovery | Source tested; fresh live collection not performed | Same | Same |
| Generation | Source tested; private pending drafts not accepted | Same | Source tested; no new accepted batch |
| Quality / persona | Full regression PASS | Full regression PASS | Full regression PASS |
| 30-item reserve | Not freshly verified | Not freshly verified | Not freshly verified |
| 24h schedule coverage | Live 3/3 | Live 3/3 | Live 1/1 |
| Media | Signed first-wave acceptance incomplete | Signed first-wave acceptance incomplete | No fresh media acceptance |
| Real publish | OFF, signed P0 canary not executed | OFF, signed P0 canary not executed | OFF |
| Measurements | Code tested; no new timed live measurements | Same | Same |
| PDCA | Code tested; new measured feedback not proven | Same | Same |
| Monitoring | Live token/review/READY PASS | Same | Same |

**Development Acceptance remains BLOCKED**, because the required live canary/deployment/recovery evidence is incomplete. Production automation is not declared ACTIVE. 24h/72h/168h observation is not fabricated or relabeled PASS. `docs/goal-status.json` is unchanged.

## Release and recovery prerequisites

1. Review this branch and the inherited unmerged work; retain the protected-main `pr-gate`. Routine Actions-free operation is separate from required PR checks. The new request is not permission to forge a status or bypass the protection.
2. **Completed:** direct owner approval received and the five-file Linux token payload validated successfully, without changing production token files or services. Review-worker tests passed locally; do not misrepresent them as part of the approved five-file VPS run. Any additional runtime-install payload remains a separate rollout action.
3. Resolve the legacy Night unknown outcome through independent owner-authenticated evidence/re-authorization, not another refresh request or marker deletion. Preserve the old marker and token until replacement identity/expiry and protected persistence are verified. Current valid tokens give time for this prerequisite; they do not justify blind replay.
4. Before any real renewal, deploy the matching renewal helper and lifecycle watchdog as an approved, versioned bundle and verify host permissions, independent ID/app anchors, timeout, service sandbox and rollback custody. Run read-only preflight first, then one explicitly accepted account pilot, independently read back identity/expiry/store and marker state, then consider timer activation. Never enable a timer merely because offline tests pass.
5. Full immutable deployment remains blocked until the unchanged 9GiB floor is met. Preserve 7-day release retention, current/previous/emergency custody and R2 protection. No lower threshold, shared-cache purge, hardlink dedup or unapproved paid disk expansion is a substitute. The source fix for setuptools is ready but not installed.
6. Review writer restart requires approved deployed source, fresh independent projection/decision readback and an explicit resolution of the old unknown operation. This code deliberately cannot clear that old latch.
7. Recount usable Bank against the exact current canonical runtime gates, perform QA on pending private drafts, and refill through the existing approved routes. Signed Night/Liver P0 canaries are a separate authorization step; no mass publishing is implied.

Rollback: leave renewal/review writer timers disabled while adopting the source change. Existing read-only monitors remain active. Preserve old credential files and every unknown-operation record. Roll back code through the approved immutable release/pinned helper mechanism; never restore an old credential over a verified newly rotated token or delete audit records as an automatic rollback.

Official interfaces checked: [Meta-owned Threads collection](https://www.postman.com/meta/threads/documentation/dht3nzz/threads-api), [Cloudflare bucket locks](https://developers.cloudflare.com/r2/buckets/bucket-locks/), and the [OSV query API](https://google.github.io/osv.dev/post-v1-querybatch/). Bucket protection takes precedence over lifecycle deletion; no policy change was made.
