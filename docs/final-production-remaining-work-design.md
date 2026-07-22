# Final Production Remaining-Work Design

Date: 2026-07-22 JST  
Baseline: `main` / `origin/main` `3e05812a514b95827b99dc20736951c02269c6e6`

## Audit Verdict

The system has working production infrastructure, bounded source acquisition,
permission-ledger authority, Cloudinary preparation, and a protected
GitHub-hosted execution surface. It is **not** yet a Goal-complete daily media
autopilot. The fail-closed evaluator correctly reports `17/35 PASS` because
the current evidence is stale and the four required same-scope canaries have
not been independently proven.

The production Sheets verifier is currently `63/63` with zero posted-save
failures. Direct Media Preparation run `29888790626` completed for both
accounts without invoking a publisher. GitHub CI run `29889173716` passed at
the current main SHA. Repository visibility, protected `main`, the protected
`production` Environment, and secret-name-only inspection were independently
confirmed.

## Confirmed Gaps

| ID | Gap | Current evidence | Required outcome |
| --- | --- | --- | --- |
| G1 | Goal evidence is stale | `docs/goal-status.json` has older commit/visibility state | Mechanical collection on final main; no prose-based PASS |
| G2 | Direct asset identity is incomplete | uploaded `media_assets` rows can lack `media_asset_id`, parent IDs and status | One immutable asset record with ID, source parent, Cloudinary ID/URL, hash, type, rights, and lifecycle |
| G3 | Slot lifecycle is incomplete | five `content_slot_runs` remain `RUNNING`; business-date fields are blank in historical rows | Every claimed slot reaches terminal state and has JST business date/attempt/recovery provenance |
| G4 | Liver direct caption alignment is intermittent | recent runs block on coverage/unsupported claims, while one later PASS exists | Structured source evidence feeds a regenerate/provider/next-candidate chain without threshold reduction |
| G5 | Goal-qualified media inventory is not proven | legacy `MEDIA_READY` and `POSTED` rows exist but lack complete Goal evidence | At least three unused direct and three unused clip assets per account, all independently validated |
| G6 | Generated-clip E2E is unproven for Night Scout | old clip slot failures and no current-scope proof | discovery -> transcript -> semantic segmentation -> 8-45s ffmpeg clip -> Cloudinary -> READY with parent/evidence |
| G7 | Ten-slot schedule contract is inconsistent | health check reports six schedule mismatches; configured workflows split text/direct/clip paths | One canonical JST 04:00 business-date slot registry, ten mapped workflows, and delayed-event recovery |
| G8 | Real canary/evidence sequence is incomplete | old posts exist but are excluded by current evaluator scope | Four bounded canaries with public verification and read-after-write evidence |
| G9 | Liver Threads reference discovery is absent | Sheets/config/history search found no approved third-party liver Threads account | Record as external blocker only after all other paths complete; never reclassify the posting account |

## Non-Negotiable Runtime Invariants

1. `media_permissions` remains the only authority for direct reuse, clips,
   storage, and reposting. A config row never grants permission.
2. X and `beauty_account` remain blocked. No cookie, CAPTCHA bypass, stealth
   browser state, paid proxy, VPS, self-hosted runner, or paid API dependency.
3. `public_post_text` is the only text given to a publisher. Internal analysis,
   source metadata, queue IDs, and transcript/OCR bodies never reach public
   text.
4. Caption thresholds stay fail-closed: alignment >= 0.72, main-claim coverage
   >= 0.70, unsupported claims = 0, source-copy <= 0.65, recent-post <= 0.75.
5. Download/cut/upload/post remain explicit scoped workflow gates. Preparation
   cannot publish. Publishing cannot rediscover or mutate source media.
6. All actions remain `ubuntu-latest`, SHA-pinned, default-branch-only for
   production, and use the protected production environment.

## Target Data Contract

The implementation model must make these IDs non-optional at persistence
boundaries and verify read-after-write:

```
source_account -> source_post -> source_post_media -> media_asset
source_video -> video_transcript -> clip_candidate -> media_asset
media_asset + public_post_text + alignment_run -> queue -> content_slot_run
queue -> posted_result + media_post_result -> metrics / PDCA
```

Required joins:

- Direct media: `source_post_id`, ordered `source_post_media_id[]`,
  `media_asset_id[]`, original-text hash, Cloudinary public ID/secure URL,
  understanding ID, alignment ID, queue ID, slot ID, posted result ID.
- Clip media: `source_video_id`, transcript hash, semantic segment evidence,
  clip candidate ID, start/end/duration, local content hash, media asset ID,
  Cloudinary public ID/secure URL, alignment ID, queue/slot/result IDs.
- `content_slot_runs` stores `business_date_jst`, attempt number, claimed at,
  terminal status, failure signature, quarantine action, fallback level, and
  the exact output IDs. Stale `RUNNING` rows are recovered idempotently.

## Work Packages For The Implementation Model

### WP-A: Data Integrity Repair And Contracts

Files: `scripts/ingest_direct_reference_media.py`,
`scripts/run_direct_reference_media_pipeline.py`, `scripts/content_slot_runs.py`,
`src/sheets_client.py`, relevant schema tests.

1. Trace why `media_assets` has uploaded records without primary/parent IDs.
   Fix the mapper/upsert instead of backfilling guessed IDs.
2. Add strict read-after-write assertions for asset parent linkage, Cloudinary
   identity, and slot business date.
3. Add a bounded reconciliation that converts stale `RUNNING` rows to a
   deterministic retryable terminal/recovery state; it must never create a
   second slot claim.
4. Add migration-safe schema tests and a read-only report before any repair.

Acceptance: zero new blank IDs; current-scope asset graph is joinable; no
stale RUNNING row remains after recovery; duplicate claim tests pass.

### WP-B: Source-Grounded Caption Evidence

Files: `src/generation/source_grounded_caption.py`,
`src/generation/semantic_alignment.py`,
`scripts/run_direct_reference_media_pipeline.py`, media understanding/OCR/ASR
adapters and tests.

1. Build a compact evidence packet from original text, OCR, transcript,
   representative frames, comments, main claim, supporting points, factual
   constraints, and prohibited inferences.
2. Require every public major claim to reference evidence keys internally.
   Delete unsupported clauses before the final evaluator runs.
3. On a block: regenerate from the same packet, try the approved bounded
   fallback provider, then select the next candidate; after two identical
   signatures, quarantine the asset.
4. Persist claim-support mapping and all nine alignment metrics without full
   transcript/OCR logging.

Acceptance: Liver and Night prepared direct items meet all thresholds without
threshold changes; blocked candidates move to next/quarantine deterministically.

### WP-C: Generated-Clip Completion

Files: `scripts/discover_approved_source_videos.py`,
`scripts/transcribe_approved_source_videos.py`, `scripts/run_media_growth_engine.py`,
`scripts/cut_approved_clips.py`, `scripts/run_media_production_pipeline.py`.

1. Ensure account/channel discovery produces bounded individual video records
and deduplicates by platform/source/video/canonical URL.
2. Normalize transcript persistence and preserve timestamps. Combine transcript
boundaries, pause/semantic markers, and visual/audio duration; never divide
time uniformly.
3. Create only standalone 8-45 second segments. Validate start/end sentences,
audio/video sync, non-overlap, and public caption evidence.
4. Cut vertical video without subtitles, upload idempotently, register the
same asset contract as WP-A, and prepare `MEDIA_READY` inventory.

Acceptance: three unused validated clip assets per account, including Night;
each has semantic-segment evidence and all parent/Cloudinary identifiers.

### WP-D: Canonical Ten-Slot Automation And Recovery

Files: `config/autonomous_mode.json`, schedule/workflow YAML files,
`scripts/run_autonomous_loop.py`, `scripts/backfill_missed_content_slots.py`,
`scripts/check_autonomous_health.py`, slot tests.

1. Encode exactly these canonical slots: Night `14 reference`, `16 original`,
`18 direct`, `21 clip`, `01 pdca`; Liver `10 original`, `13 reference`,
`16 direct`, `18 clip`, `21 pdca`.
2. Map each to a non-zero-minute UTC cron and retain JST 04:00 business dates.
Do not use long random sleeps. Dispatchers must honor a delayed canonical slot.
3. Verify scheduled workflows call only the designated path; remove duplicate
or contradictory scheduling routes after a migration test.
4. Rehearse all ten slots through source/caption/queue/claim/READY/fallback/
save paths using injected time. Run each slot twice and next-business-day once.
5. Test recovery for delayed events, 429, Cloudinary/API transient failure,
caption block, no READY inventory, post-save failure, and workflow interruption.

Acceptance: health is PASS; all ten slots produce a terminal record; second
run is idempotent; recovery picks a next candidate or safe fallback.

### WP-E: Goal Evidence And Canary Harness

Files: `scripts/collect_goal_evidence.py`, `scripts/evaluate_goal.py`,
`docs/goal-status.json`, `docs/runtime-health.json`, `docs/goal-evidence.md`,
new read-only canary verifier.

1. Generate evidence from exact final-main SHA, CI run IDs, Sheets rows,
Cloudinary metadata and public Threads verification. Reject legacy/out-of-scope
records.
2. Add machine checks for carousel ordering, public media rendering, correct
account, caption integrity, posted-result save, and duplicate prevention.
3. Do not relax evaluator criteria. A missing evidence key remains failure.

Acceptance: evaluator fixture coverage remains fail-closed; every new canary
has all required evidence fields before evaluator promotion.

### WP-F: Bounded Production Canary Sequence

Prerequisites: WP-A through WP-E green, final CI green, 63/63 Sheets verifier,
three validated inventories/path, and active tokens.

1. Night direct media -> independently verify -> Night generated clip.
2. Liver direct media -> independently verify -> Liver generated clip.
3. Stop on any mismatch, quarantine the source asset, repair root cause, and
continue from a new asset. Never repost a canary asset/text.
4. Run final ten-slot rehearsal, recovery replay, full test/CI/security suite,
then collect evidence and require `35/35 PASS`.

## External Blocker

The audit searched Sheets `source_accounts`, `reference_sources`,
`media_permissions`, `source_candidates`, `source_posts`, `source_videos`,
default sources, docs, and Git history. No approved third-party
`liver_manager` Threads reference account exists. This blocks only the
`liver_account_url_discovery` criterion. It does not block permitted
YouTube/TikTok direct-media or clip work. The user must eventually provide or
explicitly approve a third-party/self-owned Liver Threads account URL; the
Liver posting account cannot be repurposed.

## Required Evidence At Completion

`docs/goal-status.json` must be regenerated at the exact final `main` SHA and
the evaluator must return `35/35 PASS`. Required external evidence includes
the repository URL/visibility check, protected environment, CI run, Sheets
63/63 run, source/post/video IDs, parent text/transcript hashes, Cloudinary
public ID and secure URL, alignment values, four Threads permalinks with media
verification, all ten rehearsal results, delay/idempotency/recovery results,
and a clean local/fetched-main match.
