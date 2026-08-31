# SNS Growth Engine Production Goal

## Product goal

Operate one account-isolated growth loop for `night_scout`, `liver_manager`,
and `beauty_account`:

`collect -> analyze -> generate -> validate -> auto READY -> scheduled publish -> persist -> measure -> learn -> replenish`

Normal operation must not require a human to seed a queue, approve every post,
or dispatch a workflow. Each account has independent sources, credentials,
persona, inventory, caps, metrics and learning state. A failure or review item
for one account must not stop the other accounts.

## Autonomous review policy

- Low-risk text that passes account fit, persona, public-text, novelty,
  diversity and safety validation is auto-approved.
- Human review is reserved for genuinely high-risk claims, regulated Beauty
  medical content, uncertain rights, uncertain provenance and policy
  exceptions.
- A review-held candidate never consumes the whole slot. The engine must try
  bounded regeneration and a safe route fallback, while preserving the held
  candidate for review.
- Media is automatic only when `media_permissions` proves an eligible rights
  status, target account, Threads scope, provenance and unexpired permission.
  Unknown or reference-only media is never reused.
- `config/autonomous_mode.json` is the publication authority for the generic
  text loop. Approved-media execution is deliberately delegated to
  `config/media_growth_engine.json` and its dedicated workflows; false media
  flags in the text loop are isolation boundaries, not a disabled product.

## Production reliability contract

- READY inventory is replenished before publish windows and recovered with a
  bounded attempt at publish time.
- Text slots may recover through another safe text route. Media slots use only
  approved inventory and fail closed with `SKIPPED_POLICY` when none exists;
  they never silently become text posts. Media replenishment continues.
- Intended slots missed because of inventory exhaustion, generation failure,
  quality exhaustion, upstream preparation failure or ordinary review waiting
  are operational failures, not successful safe skips.
- Policy blocks and operational failures use different reason codes.
- Publisher idempotency, ambiguous-publish no-retry, account isolation,
  duplicate prevention, posted-results read-after-write and 24h/72h/168h
  metric reservations are mandatory.
- PDCA uses measured metrics from the same account only. Metrics and prior
  posts are internal learning inputs; public text never describes the PDCA
  process or claims internal measurements.
- X publishing and Beauty cross-account learning remain disabled.

## Acceptance layers

Development/rollout acceptance is decided from tests, CI, active workflows and
configuration, strict READY generation, one bounded production canary per
account, result read-after-write, recovery wiring, metric reservations and
PDCA wiring. When these pass, `development_acceptance=PASS`,
`production_automation=ACTIVE` and `production_canary=PASS` are valid without
waiting for future wall-clock windows.

Long-term production observation continues separately. Three consecutive real
schedule events, measured 24h/72h/168h collections and later same-account PDCA
consumption remain mandatory evidence, but pending windows are reported as
`production_observation=IN_PROGRESS`; they do not reopen completed development.
Temporary external failures must still demonstrate bounded retry/backoff,
explicit failure/alerting and no duplicate publish.

The criteria in `config/goal_acceptance.json` are additive: historical
criteria are retained, while current three-account production criteria are
required as well. `config/production_capability_matrix.json` is the canonical
capability contract. Missing rollout evidence blocks development acceptance;
missing time-based observation evidence blocks only production observation.

Secrets, tokens, cookies, storage state, source media and production-only
configuration must never be committed.
