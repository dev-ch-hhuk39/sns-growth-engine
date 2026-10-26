# Existing GitHub App ID handoff — 2026-10-26

## Owner request and verified cause

The owner asked to check the existing GitHub App ID configuration and use it if verified, while continuing the remaining completion work. This supersedes waiting for the owner to manually obtain the Liver ID if the independent GitHub configuration can be validated.

Read-only GitHub metadata confirms repository secrets `THREADS_APP_ID_LIVER_MANAGER` (updated 2026-06-21) and `THREADS_APP_ID_NIGHT_SCOUT` (updated 2026-06-21). No same-name production-environment override or App-ID variable was found. No Beauty-specific or shared App-ID secret appeared in this scoped audit. Only names/timestamps were read; no secret values, App Secrets or access tokens were retrieved or printed.

The old token workflow references the existing IDs, but `deploy-buffered-production-runtime.yml` and `write_buffered_runtime_env.py` omitted them from the VPS runtime environment. This explains why a GitHub setting can exist while the independently configured VPS anchor is missing. Metadata existence alone does not prove that the ID matches the live token.

## Source changes

- Forward the three account-specific App ID names through the immutable deploy environment writer, accepting only numeric IDs. Missing pins remain missing, and a global/other-account fallback is not introduced. App Secrets are not added to the runtime writer.
- Add a manual-only `verify-liver-threads-app-pin.yml` job on protected main. It receives only the existing Liver App ID secret and runs on the existing trusted VPS runner. It has contents-read permission, no schedule, no token/App-Secret injection, no secret export artifact, and no publisher or refresh command.
- `verify_github_liver_app_pin.py` locks the existing refresh namespace and invokes the installed, hash-verified `cc578f8` helper in read-only Liver preflight mode, with the candidate independent App ID. Official user/handle/app/issue/expiry/scope and posting-OFF gates remain unchanged.
- Only after verified preflight may explicit `--apply-pin` create the App-ID-only `shared/threads_app_ids.env` with mode 0600, fsync and readback. It cannot overwrite a different existing pin. The protected runtime environment and tokens are not rewritten. Output contains only fixed status/counts; no ID value or provider payload is printed.
- The source renewal service can load that optional protected pin file. The live timer remains disabled. The one already-approved Liver real refresh is a separate operation after a passing preflight; this configuration job cannot consume that allowance.

The protected-main workflow is a one-time configuration bridge requested by the owner, not a replacement scheduled Actions dependency. Do not re-enable the disabled legacy refresh workflow.

## Validation and pending production evidence

Dedicated offline tests cover passing/blocked preflight, source changes, account scope, malformed output, private storage, overwrite refusal, idempotence, absence of token refresh and output privacy. Runtime writer tests cover correct account mapping and malformed/newline ID rejection. No assertions or production gates were relaxed.

Actual pin verification, saved-pin state and subsequent pilot result must be recorded from the workflow/host receipts after delivery. Until then, actual refresh count remains 0 and no ID match is claimed. Night's unknown-operation marker is preserved, and Beauty is outside this bridge.

## Other completion work

The local Ollama generator now uses the canonical account voice prompt and supports `--qualified-only`. This mode writes to a separate private `quality-reserve/` directory and accepts only candidates passing the unchanged public, hard, local novelty/diversity and topic gates. Resumed files are audited again; completion cannot be inferred from raw row count. All output remains pending human QA, with no global-history/slot/publisher acceptance. Existing 48 raw drafts are preserved. Actual bounded model results: Night 0 passing drafts / 95 rejected, Liver 1 passing draft / 99 rejected (25 calls each). Existing account-owned catalog selection additionally prepared Night 5 / Liver 4 with local public/hard/topic/batch checks. These are separate pending batches, not a Bank refill or a combined accepted batch. Private receipts: `/private/tmp/sns-qualified-generation-result-20261026.json` and `/private/tmp/sns-qualified-catalog-plan-20261026/summary.json`. All 48 raw originals were hash-verified unchanged.

Fresh host metadata shows 8,616,275,968 free bytes, below the unchanged 9GiB release floor. All eight releases remain within the seven-day grace period; current `94b744f`, previous `7be8dc6`, no pending pointer. No release was deleted or full release deployed. Read-only review/READY/missed-slot monitors are active; review writer and renewal timers are disabled. Thirteen active hosted operational schedules still require equivalent live replacements; stopping them alone is not migration proof.

`docs/goal-status.json` is unchanged. Source/CI success does not establish accepted reserves, review-writer recovery, signed real canaries, timed metrics or autonomous production completion.

Official references: [GitHub Actions Secrets API](https://docs.github.com/en/rest/actions/secrets#get-a-repository-secret), [Meta Threads API collection](https://www.postman.com/meta/threads/documentation/dht3nzz/threads-api).

The fresh capacity audit also proves every retained venv depends on runner toolcache Python 3.11.17; that 583,392KiB cache is live and cannot be purged. Runner `_update` occupies 697,984KiB, whose removal alone would still fail the 9GiB floor; no cache was deleted. VPS user crontab has three separate five-minute account reconcilers, a daily media-preparation job and an existing daily helper. These existing jobs are not fresh successful equivalence evidence for all 13 hosted schedules.
