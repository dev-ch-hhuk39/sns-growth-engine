# Gemini hybrid AI activation

## Decision

Use deterministic code for rights, permissions, account IDs, queue state, duplicate prevention, source policy and hard safety rules. Use Gemini only for semantic classification, constrained copyediting or generation, and final language/source-fit review.

## Fail-closed sequence

1. Deterministic preflight.
2. Gemini account/audience/source-use classification.
3. Route-specific generation:
   - external Direct: constrained source copyedit;
   - owned media, clips, original/reference/PDCA text: grounded transform.
4. Deterministic public-quality and source-preservation validation.
5. Gemini final review.
6. Persist the audit in `generation_policy_json` while keeping `WAITING_REVIEW`.
7. READY approval and posting independently verify a current persisted PASS hash.

AI failure, no API key, quota exhaustion, malformed JSON or stale hashes never fall back to publishable local copy.

## Internal request caps

- Per execution: 20 actual API requests.
- Per JST day: 40 actual API requests.
- Per JST month: 1000 actual API requests.
- Cache hits consume zero requests.
- A single candidate uses at most three requests.
- Each scheduled account run processes at most two candidates, therefore at most six requests.
- Two staggered runs per account per day have a theoretical maximum of 24 requests per day and 744 requests in a 31-day month.

These are internal safety caps, independent from provider-side quotas.

## Production schedules

- `night_scout`: 09:10 and 18:10 JST.
- `liver_manager`: 09:30 and 18:30 JST.
- Both workflows share one concurrency group and never overlap.

## Credentials and model configuration

Required GitHub Actions secret:

- `GEMINI_API_KEY`

Optional repository variables:

- `GEMINI_CLASSIFIER_MODEL`
- `GEMINI_GENERATOR_MODEL`
- `GEMINI_REVIEW_MODEL`

Default free-tier-oriented stable models:

- classifier/reviewer: `gemini-3.1-flash-lite`
- generator: `gemini-3.5-flash`

The workflows skip safely when the secret is absent. The integration test suite uses fake transports and never calls Gemini.


## Freshness and repeat suppression

The persisted audit hashes both the queue fields and the resolved source evidence/policy. READY approval and posting rebuild the source context, so a rights, permission, source-account, transcript or use-policy change invalidates the old PASS. A current PASS or BLOCKED audit is not re-run on later schedules; it is reconsidered only after the queue or source-context hash changes.

Budget ledger reads are fail-closed. If the persistent Sheets request ledger cannot be read, no Gemini request is sent.
