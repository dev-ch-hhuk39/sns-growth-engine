# Reference-first media core (2026-08-11)

## Active architecture

Active reference discovery: Threads -> TikTok -> X -> YouTube. Threads uses a
bounded three-stage public route: threads-cli crawler, logged-out persisted
query, then public Playwright. Exhaustion is `DEFERRED` per source.

Physical media acquisition: X and YouTube use yt-dlp. Owner-authorized TikTok
individual posts use bounded public-embed direct HTTP after exact registered-
author and permission-ledger checks. Threads reference acquisition is active;
Threads physical-media reuse remains deferred and permission-gated.

The acquisition router now validates every active profile backend against
`config/acquisition_backend_capabilities.json`. Auth-only and opaque external-
service candidates cannot enter the production chain. Browser execution is
permitted only as the final cookie-free Threads reference fallback.
See `docs/oss-acquisition-stack-20260811.md` and run
`python3 scripts/acquisition_doctor.py --json` for the current matrix.

TikTok remains an active text/structure source and may trigger physical
acquisition only for exact owner-authorized individual posts. Registered
Threads identities can provide exact-author individual-post text and ordered
media metadata, but no Threads physical-media attempt is authorized by that.

The 2026-08-11 bounded audit found a safe anonymous TikTok route after the
yt-dlp/gallery-dl and ssut profile paths failed. Public embed hydration now
resolves exact individual posts for all three registered Liver sources; one
owner-authorized post also passed physical A/V, provenance, permission and
WAITING_REVIEW verification. The 2026-08-17 live bounded Threads probe used the
pinned public CLI route without login, API key or browser. Seven of nine owner
profiles returned 14 individual posts and 22 ordered media metadata items. Two
profiles exposed no public crawler-visible posts and exhausted all configured
routes; they are `DEFERRED`, not global failures. Meta auth is not required.

Content mix for Night Scout and Liver Manager: 50% direct reference media, 30% reference text, 10% PDCA, 5% new text, 5% approved clips.

Both accounts share acquisition, normalization, route selection, media handling, review and publishing safety. Account-specific behavior is limited to relevance/quality judgment and persona/copy generation.

Aspect-ratio default is preserve_source. Vertical conversion requires an explicit transformation request.

Active acquisition workflows install the pinned CLI. Workflows that can reach
the final Threads fallback also install Playwright Chromium, but never pass
browser storage state or login credentials.

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

- Authenticated Threads browser-session acquisition.
- Playwright Threads physical-media preparation; public Playwright remains a
  reference-only final fallback.
- TikTok Playwright physical-media fallback.
- New physical-media acquisition for Threads. TikTok browser acquisition stays
  deprecated; the active TikTok route is public HTTP only.
- Implicit force_9_16 defaults.
- Clip ratios above 5%.

These paths are not hard-deleted in this refactor so rollback and evidence remain available. Delete them only after the new path passes real X/YouTube goldens for both operational accounts.

## Regression-contract migration after first full harness

The first repository harness after the refactor produced 10 failures. They were traced to stale contracts that assumed Threads physical download, Threads browser-session routing, Playwright TikTok fallback, an exact historical source count, or a scheduled Threads-centric direct-media preparation workflow. The updated contract keeps X/YouTube/TikTok active, enables bounded Threads reference acquisition, and keeps Threads physical reuse deferred. Permission-ledger, exact-author, content-understanding, rights, video-first and review safety checks remain mandatory.

## Physical-source eligibility normalization

The legacy `media_growth_engine.allowed_source_ids` list is physical-media inventory, not the active reference registry. It is filtered by each registered source's actual normalized platform, retaining X, YouTube and explicitly owner-authorized TikTok sources. Threads reference identities are active; Threads physical media remains deferred. Regression contracts use the production rights policy and platform normalizer instead of requiring a raw `rights_status` field spelling.

## Discovery-plan rights contract

`build_discovery_plan().selected_sources` is a lightweight source-selection view and may omit enriched rights/permission fields. Physical-media safety is therefore checked in two stages: the selected row must normalize to an active physical platform, and its exactly matching `source_results` row must carry an allowed rights status plus `permission_status=approved`. TikTok additionally requires an individual `/@handle/video/<id>` parent whose author matches the registry and a recognized TikTok CDN media child. This keeps the contract fail-closed without requiring presentation-only fields on the lightweight selection record.

## Cleanup candidates, not deletion targets

- Threads authenticated browser-session adapters; keep the cookie-free public
  screen adapter because it is the active final reference fallback
- TikTok Playwright adapter
- Browser installation steps retained only in legacy workflows
- historical force-9:16 assumptions and Threads/TikTok physical-media tests

Active workflows do not select authenticated browser routes or provide storage
state. The public Threads screen fallback is installed only where its route can
be reached.

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
