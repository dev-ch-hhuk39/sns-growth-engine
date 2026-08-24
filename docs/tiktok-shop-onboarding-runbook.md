# TikTok Shop Threads Onboarding

`tiktok_shop` is implemented in the shared engine but remains `CREDENTIAL_PENDING`. Do not invent an account identity or publish before the real account exists.

## Required external values

- `THREADS_HANDLE_TIKTOK_SHOP`
- `THREADS_USER_ID_TIKTOK_SHOP`
- `THREADS_ACCESS_TOKEN_TIKTOK_SHOP`
- final tracked CTA URLs when LINE is enabled

## Onboarding

1. Add the three account-specific values to the GitHub `production` environment without printing them.
2. Dispatch `TikTok Shop Threads Onboarding` in preflight mode. It verifies presence, account isolation and publisher dry-run without posting.
3. Generate one candidate. The first 20 candidates always remain `WAITING_REVIEW`; factual, numeric, news, rule, case-study and media content permanently requires review.
4. Approve one exact queue and run the bounded canary. Verify account identity, permalink, `posted_results` read-after-write and 24h/72h/168h metric jobs.
5. Activate production through config/environment state only after the canary passes. X publishing remains off.

Content, Voice Corpus, customer language, metrics and PDCA are scoped to `tiktok_shop`. Only records explicitly marked `scope=global_fact` may be shared, and they must keep source type, publisher, date, attribution and freshness evidence. Missing downstream KPI values remain null/`UNAVAILABLE`, never fabricated zeroes.
