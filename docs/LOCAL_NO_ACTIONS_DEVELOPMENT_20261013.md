# SNS Growth Engine — local-only development and manual release handoff
Updated: 2026-10-13 (Asia/Tokyo). This is a development policy, not a production completion assertion.

## Current owner instructions (supersedes older CI handoffs)

- ChatGPT performs the coding; **do not invoke Codex** to implement further work.
- **Never start, dispatch, depend on or wait for GitHub Actions CI.** Use verified offline tests on the authorized Mac. Static parsing of `.github/workflows/` by test scripts is permitted; it is **not** workflow execution.
- Do not access or modify shared production VPS, SSH/services, production cron or deployments in this development chat. The owner uses a separate common-VPS operations workflow for those actions.
- Do not use real Google Sheets writes, paid APIs, Cloudinary upload, real SNS posting, source media download, live IdP enrollment, or issue production credentials without specific approval. Preserve current physical-media network interlocks and permission controls.
- Keep changes in an isolated worktree. Never reset/clean the user's worktree, rebase unapproved changes, force push or overwrite another agent's files. Local tests and local commits are allowed.

## Current Git status and takeover

GitHub `dev-ch-hhuk39/sns-growth-engine` is currently **PUBLIC**.
Latest verified main at this takeover: `57ef785118ca9c34679723d94151435ce2f30dca`
(merged PR #393, Phase 5B-6P).

Codex created and **locally committed** `9b9891ee7c20dccb8af3ea17b8ead0d7e32aee01`
(verified post-success metrics reservation lifecycle / account-safe collection).
It did not push, open a PR, or merge. A prior push attempt was stopped by an
explicit **public-code-export approval** check. Do not bypass that review by
another connector or upload route.

The Codex worktree contains additional **uncommitted documentation only**,
which remains untouched. This ChatGPT development session created an isolated
worktree from the Codex *committed* code:

```text
<sibling worktree>/v2-chatgpt-local-noactions-20261013
```

Branch: `chatgpt/sns-completion-local-noactions-20261013`.
The worktree lives next to the existing local `v2` checkout; absolute
device/account paths are deliberately not embedded in this public-repo
documentation.
No remote push or GitHub Actions jobs were started by this takeover.
The base `v2` worktree remains dirty on `feat/content-quality-v2`;
do not change it.

The historical `docs/goal-status.json` is from **2026-07-28**
(21 of 35 criteria PASS then), so **it is not a current completion percentage**
and must not be edited without the official evidence collector. The
currently committed product Goal has more, additive three-account criteria.

## One-command local validation

From the isolated ChatGPT worktree:

```bash
python3 scripts/run_local_quality_gate.py --mode focused \
  --output /tmp/sns-qa-focused.json --log-dir /tmp/sns-qa-focused-logs
```

Runs the selected metrics reservation tests, inherited independent operator
IdP tests, legacy Sheets mutation inventory, SNS network sink inventory,
Ruff fatal lint, Python compile, git diff checks and local gitleaks history scan.

Before a local release/PR attempt:

```bash
python3 scripts/run_local_quality_gate.py --mode full \
  --output /tmp/sns-qa-full.json --log-dir /tmp/sns-qa-full-logs
```

Full mode additionally runs the *offline* repository test runner (excludes
8 external credential probes and 3 optional local-tool probes) and performs
**static** workflow safety tests. It does not execute a single workflow.
The report contains the local test results and paths under `/tmp`.
These reports are not proof of running on a production server, provider
permissions, or real posts. The source-level code deliberately has no
`gh`, `git push`, SSH, curl, or provider network call.

The report and logs **must be outside the Git worktree**, and are not
user or Library deliverables. Do not commit secrets or test logs.

## Existing Action-free runtime entrypoint

`scripts/run_buffered_production_host.sh` already implements the
`--trigger xserver_cron` and `--trigger manual` modes, account-scoped
execution, a read-only dry-run choice and an explicitly confirmed apply.
Its code targets the **immutable current release on the host**, requires
a private mode-0600 environment file, shared production deploy lock and
account/Google quota locks. GitHub recovery is another historical trigger,
but it is **not required** in order to use the cron/manual code path.

This development session does not install cron, source that environment
file, use the production locks, or invoke an apply. The existing entrypoint
and its runtime requirements should be audited and managed in the common-VPS
operations chat rather than rebuilt as a new scheduler. Do not treat the
presence of an entrypoint as evidence that cron is presently deployed.

## Release/pull-request constraint

**Never run GitHub Actions, even for testing a PR.** Historic
`.github/workflows/ci.yml` and protected-branch requirements may still
exist; they were not changed in this phase. Publishing a code branch
may trigger Actions unless the repository's settings are adjusted.
Changing branch protections or disabling production workflows must be
separately approved and reviewed; no such change has been made.

In addition, the remote is PUBLIC and the preceding attempt to export the
15-file Codex patch was explicitly blocked for destination/payload review.
Local passing tests alone do **not** authorize circumventing this export
review with a GitHub connector, manual upload, alternative push, or another
identity. Preserve the local reviewed commit for an authorized later release.

A normal later release path, *after* public-export approval and an
Actions-free branch/repo settings review, is: local quality report;
read-only diff review and secret scan; prepare a PR without triggering
GitHub Actions; review and merge according to agreed branch protections;
then hand off the verified SHA to the common-VPS operations chat.
Do not represent a local commit as a merged PR or live deployment.

## What remains before Goal completion

The repository has rich local code and tests for text generation, persona
filters, READY/replenishment, gated publisher/result persistence, and
post-success metrics reservations/PDCA. The newly inherited Codex commit
closes a real 24/72/168-hour **reservation planning/recovery** gap;
it does **not** create actual measurements.

The principal remaining work is not another layer of simulated
approval checks. It is **integration and real acceptance evidence**:

1. Validate Night/Liver production text schedule/result lifecycle and
   actual 24/72/168-hour measurement under the approved deployed SHA.
2. Confirm the current owner-governed account scope: `GOAL.md` requests
   three accounts including Beauty; `AGENTS.md` currently prohibits
   Beauty production operations. Do not silently enable Beauty.
3. Real protected operator IdP/Google service account and reporting-only
   workbook provisioning; read-only permission test, then a separately
   approved one-row canary using the existing 6J–6P gates.
4. Migrate eligible legacy operational Sheets update callers per source
   to one authoritative queue; preserve source rights, no-blind-retry
   and account boundaries.
5. Approve and verify media source rights, media/clip posting and
   read-after-write results. Existing media network interlocks remain
   enabled while this evidence is absent.
6. Review deployment/rollback/monitoring and production schedules
   **with the separate common-VPS operations chat**, without
   GitHub Actions CI. Measured PDCA observations require actual time.

Never mark `production_automation=ACTIVE` or Goal completion from
synthetic offline tests, unpublished PRs or an historical status file.
