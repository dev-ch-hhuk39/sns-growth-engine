# SNS Growth Engine Reference-first Goal

## Current product goal

Build one reliable reference-first engine for `night_scout` and
`liver_manager`:

`registered sources -> normalized SourcePost + ordered Media -> understand -> choose route -> generate -> human review -> READY -> later publish/metrics/PDCA`

The current milestone prioritizes acquisition, exact parent/provenance binding,
rights, content understanding, persona-safe generation and review reliability.
It does not prioritize autonomous mass publishing.

## Required architecture

- Reference discovery priority: TikTok -> Threads -> X -> YouTube.
- Stable physical-media phase: X and YouTube only.
- X discovery: bounded metadata-only `gallery-dl`.
- X individual-post media and YouTube media: `yt-dlp`, after permission.
- Threads/TikTok desired active reference routes are non-browser.
- Threads/TikTok new physical-media acquisition is deferred.
- Content mix for both accounts: direct media 50%, reference text 30%, PDCA
  10%, new text 5%, approved clip 5%.
- Default geometry is `preserve_source`; forced 9:16 is explicit-only.
- Live Sheets `media_permissions` is the runtime authority for reusable media.
- X permission is source-specific and never inherits to Retweets, quotes or a
  different author.
- `WAITING_REVIEW` is not publishable; only human-approved `READY` inventory is
  worker-eligible.

## Completion and evidence

The current Reference-first code milestone is complete only when active paths
share the policy above, relevant regression is green and no permission,
provenance or publication gate is weakened.

The existing `config/goal_acceptance.json` and
`config/production_capability_matrix.json` remain additive production-evidence
contracts. Their historical criteria are not deleted or relaxed by this
rebaseline. Criteria that require live Sheets, Cloudinary, publishing, metrics
or scheduled-run evidence remain unverified until that evidence exists; a
mock, fixture, dry-run or green workflow is not production proof.

The whole product must not be called production-complete while X dual-account
physical Goldens are blocked by missing source-specific reusable-media
permission or while final destructive legacy cleanup remains gated behind
those Goldens.

X publishing and `beauty_account` activation are outside the current Goal.
Secrets, cookies, tokens, storage state, source media and production-only
configuration must never be committed.
