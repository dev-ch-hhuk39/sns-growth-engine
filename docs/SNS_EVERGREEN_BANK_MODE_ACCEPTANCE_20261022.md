# SNS Growth Engine | Evergreen bank CLI repair (2026-10-22 JST)

## Root cause verified

During the AUTO_READY pilot GitHub run 39691990553, the first Liver Manager READY maintenance returned DELIVERY_READY for its required text slots, but the subsequent evergreen reserve refill failed. The evergreen-only branch of main() also unconditionally computed _coverage_result(0,0), giving NO_REQUIRED_TEXT_SLOTS even when the independent evergreen reserve itself was adequately replenished. An empty set of required text delivery slots must remain a failure in the ordinary delivery mode; it is not a valid assessment of reserve stock in bank-only mode.

The bank replenisher could also run more paid generation attempts after a provider timeout or rate limit. The existing paid-generation failure circuit is now honored in evergreen mode, reducing unnecessary retries without altering editorial, AI approval or publishing gates.

## Implementation contracts

- Evergreen-only --apply returns PASS (exit 0) only if each requested account explicitly returns READY_INVENTORY_OK and usable_evergreen/minimum are positive consistent integers with usable >= minimum. A missing, duplicated or mismatched account, stock shortfall, invalid count or quality failure remains FAILED (exit 1).
- Evergreen-only --dry-run returns PLAN_ONLY (exit 0) only when all requested accounts returned PLAN_ONLY, not as proof of live inventory.
- Ordinary text delivery _coverage_result(0,0) still fails with NO_REQUIRED_TEXT_SLOTS. Account, exact slot/date, validator, AI and owner review, no-post and kill-switch rules are unchanged.
- When a bank-generation attempt reports a hard blocker, provider rate limit, timeout, unavailable provider, or paid AI budget exhaustion, discontinue that bank's repeated paid attempts. Do not turn rejected content into READY.
- Client-side encrypted Cloudflare R2 backup, Sheets schema, permissions, existing live SNS jobs and historical releases are unaffected by this source-only PR.

## Verification and rollout

Run the new synthetic offline regression tests and existing ready safety tests, full CI plus security checks, then merge protected main. Before any SNS immutable runtime deployment, independently verify recent R2 encrypted restore, 9GiB/8GiB disk gates, posting/P0 OFF, current/previous/emergency rollbacks and no premature old-release deletion.

This changes an inaccurate CLI exit status, not the number or quality of actual approved READY candidates. Outstanding inventory and provider issues remain in GitHub issues #441 and #439.
