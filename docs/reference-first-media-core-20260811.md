# Reference-first media core (2026-08-11)

## Active architecture

Reference discovery: TikTok -> Threads -> X -> YouTube.

Physical media acquisition: X + YouTube only, using yt-dlp.

TikTok/Threads remain valid text/structure reference sources but do not trigger new physical-media download attempts.

Content mix for Night Scout and Liver Manager: 50% direct reference media, 30% reference text, 10% PDCA, 5% new text, 5% approved clips.

Both accounts share acquisition, normalization, route selection, media handling, review and publishing safety. Account-specific behavior is limited to relevance/quality judgment and persona/copy generation.

Aspect-ratio default is preserve_source. Vertical conversion requires an explicit transformation request.

Active scheduled/manual reference-acquisition workflows do not install a
browser runtime or pass browser storage state. Legacy browser adapters remain
registered only so old evidence and rollback paths are readable; the routing
configuration cannot select them.

## Runtime permission contract

Physical acquisition and Direct Media selection evaluate the latest matching
live `media_permissions` row. The row must be non-revoked, unexpired,
`permission_status=approved`, have owned/licensed/approved-creator rights,
contain evidence type/reference and approval identity/time, cover the target
account when scoped, and enable every operation used by the route.

For X, the individual `/status/<id>` author must also equal the registered
source handle. Profile discovery suppresses Retweets, quotes, replies and
expanded child content; a third-party post can never inherit registered-source
permission.

## Deprecated from the active path

- Threads browser-session acquisition for scheduled media preparation.
- Playwright Threads media preparation.
- TikTok Playwright physical-media fallback.
- New physical-media acquisition for Threads/TikTok.
- Implicit force_9_16 defaults.
- Clip ratios above 5%.

These paths are not hard-deleted in this refactor so rollback and evidence remain available. Delete them only after the new path passes real X/YouTube goldens for both operational accounts.

## Regression-contract migration after first full harness

The first repository harness after the refactor produced 10 failures. They were traced to stale contracts that assumed Threads physical download, Threads browser-session routing, Playwright TikTok fallback, an exact historical source count, or a scheduled Threads-centric direct-media preparation workflow. The updated contract keeps TikTok/Threads as reference-discovery platforms while physical-media acquisition stays X/YouTube only. Permission-ledger, content-understanding, rights, video-first and review safety checks remain mandatory.

## Physical-source eligibility normalization

The legacy `media_growth_engine.allowed_source_ids` list is physical-media inventory, not the four-platform reference registry. It is now filtered by each registered source's actual normalized platform, retaining only X/YouTube. TikTok/Threads remain available through the reference acquisition routes. Regression contracts use the production rights policy and platform normalizer instead of requiring a raw `rights_status` field spelling.

## Discovery-plan rights contract

`build_discovery_plan().selected_sources` is a lightweight source-selection view and may omit enriched rights/permission fields. Physical-media safety is therefore checked in two stages: the selected row must normalize to X/YouTube, and its exactly matching `source_results` row must carry an allowed rights status plus `permission_status=approved`. This keeps the contract fail-closed without requiring presentation-only fields on the lightweight selection record.

## Cleanup candidates, not deletion targets

- Threads browser-session/public Playwright/screen adapters
- TikTok Playwright adapter
- Browser installation steps retained only in legacy workflows
- historical force-9:16 assumptions and Threads/TikTok physical-media tests

Active workflows no longer select or install these browser routes. The source
files remain until X and YouTube both have dual-account physical Goldens and a
fresh reachability audit confirms deletion is safe.

## Completion and runtime classification

`config/reference_first_completion.json` classifies every workflow and major
entry point as canonical, inactive compatibility, obsolete/dead, or
external-blocked. `scripts/evaluate_reference_first_completion.py` validates
that inventory and checks executable publisher, metrics, PDCA and permission
contracts. See `docs/reference-first-entrypoint-classification.md` and
`docs/reference-first-completion.md`.

The no-write dual-account integration contract is PASS when source identity,
exact parent/media attachment, understanding, direct/reference/clip routing,
persona generation, final public validation, review eligibility,
`preserve_source` geometry and permission checks all pass for Night Scout and
Liver Manager. Production success remains a separate evidence class.
