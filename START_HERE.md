# START HERE - Reference-first Media Core

Updated: 2026-08-11

## Read first

1. Current user task and any task-specific Owner Source of Truth
2. `AGENTS.md`
3. `GOAL.md`
4. `docs/current-work.md`
5. Latest section of `docs/ai-work-handoff.md`
6. `docs/reference-first-media-core-20260811.md`
7. `docs/reference-first-completion.md`
8. `docs/reference-first-entrypoint-classification.md`

## Current local state

- Branch: `refactor/reference-first-media-core-20260811-20260811-054925`
- v21 start HEAD: `f0d938c6080ad580eb5e86f46c1ab8b880151565`
- Do not reset, clean, rebase, discard or reconstruct this branch from main.
- Historical production evidence remains in `docs/ai-work-handoff.md`; it does
  not override current policy.

## Active architecture

- Managed accounts: `night_scout`, `liver_manager`
- Active reference priority: TikTok -> X -> YouTube
- Stable physical media: X + YouTube via `yt-dlp`, plus exact owner-authorized
  TikTok public-embed media
- X discovery: bounded metadata-only `gallery-dl`
- Threads reference acquisition: `DEFERRED_OSS_CANDIDATE`; Meta Graph,
  Meta oEmbed, Playwright and browser/session routes are
  `NOT_USED_BY_OWNER_POLICY`
- Mix: direct 50 / reference text 30 / PDCA 10 / new text 5 / clip 5
- Geometry: `preserve_source`
- Reusable media authority: live Sheets `media_permissions`
- Review: `WAITING_REVIEW` is ineligible; `READY` is eligible
- Completion: software/integration evidence is evaluated separately from live
  production evidence by `scripts/evaluate_reference_first_completion.py`

## Safety boundary

- Reusable-media permissions remain exact source/account/handle rows. Never
  infer or mirror a grant to another source or a third-party repost.
- Public X content is not reusable merely because it is publicly accessible.
- X status author must match the registered source handle.
- No X publish, no `beauty_account`, no production Sheets/Cloudinary/social
  mutation without explicit authorization.
- Deprecated Playwright/browser acquisition code remains for rollback only and
  is not part of active routing.

## Validation baseline

The v20 milestone was 825/825 repository tests, zero failures. After any
change, run focused tests, Python compile, the repository test runner, Ruff
fatal rules and `git diff --check`. Never update `docs/goal-status.json` by
hand.

## Deferred platform

YouTube physical acquisition and exact owner permission have dual-account PASS
evidence. Threads requires no Meta authentication: it remains deferred until
the owner supplies an acceptable GitHub/OSS backend candidate and that route
passes bounded read-only, provenance and safety verification.

Legacy Graph/oEmbed/browser code remains historical and inactive so useful
evidence is not destroyed. It must not be selected by production routing.

The current internal target is
`SOFTWARE_COMPLETE_EXTERNAL_BLOCKERS_ONLY`. It does not authorize production
writes and must not be described as production evidence complete.
