# START HERE - V1 Production Completion

Updated: 2026-08-28

## Read first

1. Current user task and task-specific Owner Source of Truth
2. `AGENTS.md`
3. `GOAL.md`
4. `docs/current-work.md`
5. Latest section of `docs/ai-work-handoff.md`

## Current state

- Base main: `2f1749d4167d91d8c4d6d45ef0abdb3333bb00df` (PR #264 merged)
- Active work branch: `fix/v1-direct-evidence-voice-final-20260827`
- Keep the existing dirty worktree and do not reset, clean, rebase, or discard it.
- `.runtime/`, `.ai-tmp/`, credentials, tokens, cookies, and storage state are never committed.
- Active production accounts: `night_scout`, `liver_manager`, `beauty_account`.
- `tiktok_shop` remains `CREDENTIAL_PENDING` and must not receive a fabricated identity.

## Current implementation target

- Direct Media selection requires usable source text before external download cost.
- Stored Cloudinary media that only needs understanding refresh is preferred over a new network download.
- Caption, semantic, persona, or public-validator failures never quarantine physically valid media.
- Only narrowly proven legacy downstream false quarantines receive one bounded retry.
- Night Scout and Liver Manager Direct Media may become `READY` only through strict Hybrid AI, rights, permission, validator, internal-leak, account-fit, and media URL gates.
- Beauty remains human-review-only and is never included in autonomous READY promotion.
- Direct preparation never publishes. Scheduled publishers remain separately gated and bounded to one post.

## Validation baseline

- Direct Media focused tests: 46/46 PASS.
- Repository script regression: 876/876 PASS.
- Pytest suite: 146/146 PASS.
- V1 autonomous completion audit: 100/100 PASS.
- Workflow safety contracts: 504/504 PASS.
- Ruff fatal rules, compileall, source registry validation, and `git diff --check`: PASS.

## Exact next order

1. Commit this branch, push it, open one PR, and obtain exact-head CI success.
2. Merge normally and synchronize local `main` with `origin/main`.
3. Run Liver Manager Direct preparation in production and require a real non-empty `READY` queue ID with Sheets read-after-write.
4. Run the Liver Direct publisher in dry-run mode against that inventory.
5. Run Night Direct preparation; `READY` is accepted when eligible media exists, otherwise exact `NO_ELIGIBLE_MEDIA` is fail-closed.
6. Run Beauty preparation and require a reviewable `WAITING_REVIEW` candidate without fabricating approval.
7. Verify Night/Liver text dry-runs, active workflows, schedules, global config, and X publishing disabled.
8. Claim V1 completion only when every condition in the current Owner contract is backed by production evidence.

## Safety boundary

- Do not lower rights, provenance, permission, author, parent, account, semantic, persona, quality, or Hybrid AI gates.
- Do not bypass CAPTCHA/login challenges. External provider failures are bounded and fail-soft.
- Do not auto-promote Beauty.
- Do not publish to X.
- Do not describe a dry-run, mock, or software-only result as production proof.
