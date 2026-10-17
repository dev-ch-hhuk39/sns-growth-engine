# SNS Growth Engine — security and VPS capacity audit (2026-10-17 JST)

This report is a bounded verification, not a guarantee of zero vulnerabilities.

## Findings and fixes

- Code reference during audit: GitHub main 4af37a96db83e4543d33aa2de99120363cf03b4a, while VPS still ran f6b78bacd6fa4a72d67894bd3c09cbac38391d99.
- Threads identity read-only preflight previously put the access token in the request URL. It now uses OAuth2 Bearer headers, refuses redirects, and blocks missing or mismatched identity.
- Encrypted P0 backup restore previously risked unbounded age output / gzip header expansion. The verification path now caps age plaintext to 80MiB, tar total to 80MiB, each member to its role, and refuses unknown or duplicate members. Restores only to disposable private storage and verifies signed P0 journals and SEND records.
- Prior real operator-encrypted production P0 backup verified with the updated restore code. No SNS post or live SQLite replacement.
- Current GitHub CI checks dependencies with pip-audit and secret history with Gitleaks. Extra focused tests cover redirected token exfiltration and malformed archives.

## Exact SNS-only VPS storage inventory

- SNS runner directory: approximately 5.6GB total.
- Buffered runtime releases: approximately 4.3GB. Keep current, previous, and all existing releases today: oldest is Oct 11 at 15:46 JST, not yet 7 days old.
- Dedicated setup-python cache: approximately 570MB. Existing minimum recoverable cache policy is 600MiB; do not bypass or break CI.
- Runner _work: approximately 611MB; runner checkouts, action dependencies and toolcache, not an indiscriminate deletion target.
- Runner diagnostic logs: approximately 65MB. Of this, logs aged more than 7 days total about 40MB; older than 14 days about 21MB. Preserve incident diagnostics unless separately archived and reviewed.
- Live SNS shared runtime and private ledger: approximately 16MB. Absolutely protect tokens, HMAC keys, runtime.env, once.sqlite3, lock files, backups, posting records.
- Other applications and system-level Docker/volume files: out of scope; do not touch.
- Shared VPS disk free is variable and near the >=8GiB strict deployment minimum. Never lower the gate. Installing a fresh immutable release requires additional space beyond the preflight.

No release, old log or production data was deleted during this audit.

## Unresolved release conditions

1. Night Scout account handle is absent from GitHub secrets and installed VPS runtime. Read-only provider identity must be verified before authorizing any real post.
2. External old writers, historical SEND uncertainty and duplicates have not all been independently reconciled.
3. Operator's age decryption key needs a separately protected recovery copy and rotation plan; one Mac is not independent key custody.
4. Preserve exact owner-approved post text but no queue insert, host signature or posting switch change until other prerequisites.
5. Run full CI and signed secret-history audit for this change. Perform no-post deploy only when staging headroom, all shared locks and rollback conditions are confirmed; then independently re-audit installed SHA and both posting OFF switches.

The approved post candidate and snapshots remain Mac-local in a project-specific owner-only private folder and are not added to Git.


## Continuous CI fallback for disabled repository security services

At the audit date GitHub reported: native Dependabot alerts disabled,
native Secret Scanning disabled, and no Code Scanning analysis available.
These are not proof of zero findings. Hosted-runner CI now schedules daily at
03:20 JST with the existing pinned pip-audit and Gitleaks jobs. The
schedule intentionally skips PR-only and integration-test jobs and does
not use the SNS VPS runner, post, deploy, delete, or modify external data.
Enable native GitHub alerts separately with appropriate repository admin
permissions; this workflow does not automatically enable GitHub settings.
