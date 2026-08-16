# Reference-first media core (2026-08-11)

## Active architecture

Active reference discovery: TikTok -> X -> YouTube. Threads is
`DEFERRED_OSS_CANDIDATE` by the latest owner policy.

Physical media acquisition: X and YouTube use yt-dlp. Owner-authorized TikTok
individual posts use bounded public-embed direct HTTP after exact registered-
author and permission-ledger checks. Threads reference and physical acquisition
are deferred and have no active route.

The acquisition router now validates every active profile backend against
`config/acquisition_backend_capabilities.json`. Browser, auth-only and opaque
external-service candidates cannot enter the backend-only production chain.
See `docs/oss-acquisition-stack-20260811.md` and run
`python3 scripts/acquisition_doctor.py --json` for the current matrix.

TikTok remains an active text/structure source and may trigger physical
acquisition only for exact owner-authorized individual posts. Registered
Threads identities and permission history are retained, but no Threads
reference acquisition or physical-media attempt runs while deferred.

The 2026-08-11 bounded audit found a safe anonymous TikTok route after the
yt-dlp/gallery-dl and ssut profile paths failed. Public embed hydration now
resolves exact individual posts for all three registered Liver sources; one
owner-authorized post also passed physical A/V, provenance, permission and
WAITING_REVIEW verification. Threads public HTML still returns a logged-out
application-404 SSR payload for one Night and one Liver source, while maintained
alternatives require Playwright/session state or an opaque conversion service.
The v21/v22 Graph and oEmbed experiments are retained only as historical code.
Meta Graph, Meta oEmbed, Playwright, browser automation and browser sessions
are `NOT_USED_BY_OWNER_POLICY` for Threads reference acquisition. Meta auth is
not a blocker and is not required by the doctor or completion evaluator.

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
- New physical-media acquisition for Threads. TikTok browser acquisition stays
  deprecated; the active TikTok route is public HTTP only.
- Implicit force_9_16 defaults.
- Clip ratios above 5%.

These paths are not hard-deleted in this refactor so rollback and evidence remain available. Delete them only after the new path passes real X/YouTube goldens for both operational accounts.

## Regression-contract migration after first full harness

The first repository harness after the refactor produced 10 failures. They were traced to stale contracts that assumed Threads physical download, Threads browser-session routing, Playwright TikTok fallback, an exact historical source count, or a scheduled Threads-centric direct-media preparation workflow. The updated contract keeps X/YouTube/TikTok active, defers Threads safely, and adds owner-authorized TikTok physical acquisition without reactivating browsers. Permission-ledger, exact-author, content-understanding, rights, video-first and review safety checks remain mandatory.

## Physical-source eligibility normalization

The legacy `media_growth_engine.allowed_source_ids` list is physical-media inventory, not the active reference registry. It is filtered by each registered source's actual normalized platform, retaining X, YouTube and explicitly owner-authorized TikTok sources. Threads remains registered but deferred. Regression contracts use the production rights policy and platform normalizer instead of requiring a raw `rights_status` field spelling.

## Discovery-plan rights contract

`build_discovery_plan().selected_sources` is a lightweight source-selection view and may omit enriched rights/permission fields. Physical-media safety is therefore checked in two stages: the selected row must normalize to an active physical platform, and its exactly matching `source_results` row must carry an allowed rights status plus `permission_status=approved`. TikTok additionally requires an individual `/@handle/video/<id>` parent whose author matches the registry and a recognized TikTok CDN media child. This keeps the contract fail-closed without requiring presentation-only fields on the lightweight selection record.

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

## Agent Reach and owner permission activation

Agent Reach 1.5.0 was installed from official commit
`1221ecd0c3e0502ee37406f03543bedf7503f2c7` into the isolated user-home venv.
Its repository role is limited to optional generic-Web analysis. It has no
native Threads or TikTok channel, and its X route requires explicit auth. It
does not replace the canonical acquisition router or reactivate browser paths.
The measured matrix is in `docs/agent-reach-capability-audit-20260811.md`.

The owner-attested permission decision for 24 exact X/Threads/TikTok source
identities was applied to `media_permissions` and verified read-after-write.
Permissions are source/account/handle-specific, Threads-destination-only, and
never inherited by a retweet, quote, repost, or third-party author. This
permission activation does not prove X physical acquisition: bounded X Golden
probes remain blocked by explicit-auth/profile discovery and the absence of a
video on the one known Night Scout individual status.

The separate v21 decision grants the two exact YouTube identities only:
`src_ns_yt_cand_006/@ichijo_hibiki` and
`src_lm_yt_cand_001/@suu-san_pococha`. Live Sheets apply and read-after-write
passed with zero invalid rows. Their existing A/V files now pass the rights
gate and reach `WAITING_REVIEW`; this does not authorize any other YouTube
source or production publication.
