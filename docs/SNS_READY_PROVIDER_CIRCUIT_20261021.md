# SNS READY provider circuit breaker (2026-10-21)

## Observed problem

No-post AUTO_READY pilot #39522078604 and Issue #441 previously showed budget exhaustion and 480-second subprocess generation timeouts. PR #444 stops repeated paid generation routes **inside one slot** after budget, timeout, rate-limit and configured provider failures. However subsequent slots of the SAME account reused a new local paid-route state; a failed first slot could still generate paid requests on slots 2 and 3 of the same inventory run.

## Account-scoped fix

- Pure `paid_generation_pause_required` checks only fixed, sanitized status/failure categories or per-stage reason codes. It cannot parse private text, raw provider responses, tokens, queue IDs or account payloads.
- On a confirmed AI budget exhaustion, subprocess generation timeout, provider timeout/rate-limit/unavailability/configuration/credential failure, subsequent slots of the SAME account run `replenish(..., offline_only=True)`, skipping all primary paid generation routes.
- The existing deterministic offline-original candidate and all final hybrid AI, owner review, content validator and publisher dry-run gates remain intact. This is NOT permission to turn rejected candidates into READY.
- Ordinary quality rejection remains eligible for existing bounded safe paid fallback: a quality failure is not a provider outage.
- Existing invariant applies: all CLI results have `would_post=false`; no real SNS publishing, no new AI budgets, no Sheets writes in tests.
- Diagnostic result includes a boolean `paid_generation_paused`, never provider response or confidential IDs.
- 5 synthetic no-network tests validate three-slot state propagation, separate quality rejection, sanitized categories and no-post behavior. Focused existing 9+12+18+4 readiness safety tests remain PASS.

## Deployment and acceptance

This is only a source change until complete GitHub CI security checks and bundled production deployment. Avoid creating a separate ~700MiB immutable release while shared VPS capacity is near 80% and protected older releases remain inside seven-day grace. No live paid provider calls or Google Sheets mutations are part of this PR. Continue Issue #441 for Night Scout/Liver Manager zero publishable future-slot READY and Issue #439 for overall operational readiness.
