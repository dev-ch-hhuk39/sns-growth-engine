# Growth attribution and bounded learning loop

## Production lifecycle

1. The account-scoped workflow resolves one canonical content slot.
2. `run_autonomous_loop.py` generates a `WAITING_REVIEW` candidate.
3. The generation contract records `post_features_v1`: topic, hook, body, closing, structure, CTA, content type, media alignment, and strategy policy.
4. `auto_approve_queue.py` may promote only a candidate whose public validator and `generation_quality_v3` evidence both pass.
5. `process_threads_queue.py` posts one `READY` row and copies the complete feature record to `posted_results`.
6. The posting read-after-write check succeeds before 24h, 72h, and 168h metric jobs are created.
7. Daily aftercare collects available metrics and runs `run_growth_attribution_cycle.py`.
8. The attribution cycle compares only posts from the same account and measurement window. It writes evidence-qualified explanations to `post_attributions`.
9. A feature enters `strategy_state=ACTIVE` only after at least eight measured account posts, three observations for the feature, and sufficient confidence.
10. Active primary topics influence four of five deterministic generation decisions. One of five remains exploration. Prompt and code rewriting are prohibited.

## Interpretation contract

Attribution is an association analysis, not proof of causality. Every explanation contains metric evidence, comparison-window evidence, feature evidence, reason codes, and confidence. Missing metrics are not converted to zero. Rows without `post_features_v1` are excluded from learning.

## Scheduled publishing activation

Scheduled account workflows always run a dry-run first. Real scheduled execution occurs only when all of the following are true in `config/autonomous_mode.json`:

- `autonomous_mode_enabled=true`
- `production_publish_activation_approved=true`
- `scheduled_publish_enabled=true`
- `kill_switch=false`

`activate_scheduled_publish.py` evaluates the twelve canonical canary slots before setting the two activation flags. Batch-specific canary IDs are accepted, but posting and metric evidence from different canary IDs are never combined.

## Fail-closed guarantees

- Generation quality status never overwrites the queue lifecycle status.
- New feature-bearing rows cannot become `READY` without the complete generation contract.
- Real-post environment flags are scoped only to the activated apply step.
- X, unknown-rights media, downloads, cuts, transcription, and Cloudinary uploads stay disabled in the text loop.
- A kill switch or missing credentials blocks the apply step.
