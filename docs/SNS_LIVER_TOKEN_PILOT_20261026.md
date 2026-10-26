# Liver token pilot — 2026-10-26, installed / preflight blocked

## Approved scope and exact source

The owner explicitly approved installation of two audited Python files on `fukuri-vps`, followed by one real `liver_manager` refresh **only if** the read-only preflight passed. Night's unknown-operation record, Beauty, existing timers, publishing and Sheets were excluded from modification.

Source: merged protected main `cc578f8a5cef169679583aca05652a95398a8fbc` / [PR #472](https://github.com/dev-ch-hhuk39/sns-growth-engine/pull/472). Before that approval, CI passed all four checks, including 1,092 repository scripts and 150 pytest cases; the approved Linux payload passed 22 offline tests.

Installed bundle (root owned, directory 0555, files 0444):

`/usr/local/libexec/chadult-sns-token-renewal/cc578f8a5cef169679583aca05652a95398a8fbc/`

| File | SHA-256 |
| --- | --- |
| sns_local_threads_token_renewal.py | 0d6416cb9d2f46868e0050964d4873a699857e4f76e8e8eb27f3821de837ff35 |
| sns_local_threads_expiry_watch.py | 989b227fef1b7da1d45a3dc66ae13169374325975c9eb60a8e7f624ef5818160 |

Both source and installed hashes were checked before execution. Existing expiry-watch source/service was not overwritten. No new full immutable release was installed; the live release remains `94b744f431199ea52e9444aa02552b83c982bdff` and the existing 9GiB full-release floor remains unmet.

## Observed preflight

At the initial 13:46 JST check, the shared token directory was 0700/snsrunner, runtime environment 0600/snsrunner, and the existing Night unknown marker 0600/snsrunner. Renewal and review-write timers were inactive/disabled. No Liver unknown marker was present.

The preflight ran as `snsrunner` in a bounded, sandboxed one-off systemd unit, with the existing protected EnvironmentFile and exclusive refresh flock. The command selected **only** `liver_manager` and did **not** include `--apply`.

Result:

```json
{"status":"BLOCKED","accounts":{"liver_manager":{"status":"BLOCKED","reason":"CURRENT_TOKEN_LIFECYCLE_UNVERIFIED","posts":0}},"posts":0,"github_secrets_changed":false}
```

A second read-only diagnostic using the unchanged verifier isolated the missing input:

```json
{"account":"liver_manager","app_id_configured":false,"reason":"META_APP_ID_MISMATCH","status":"BLOCKED","posts":0,"refreshes":0}
```

This does **not** establish that the actual token belongs to a wrong app. The expected app ID is absent, so the verifier has no independently configured app anchor to compare. No app ID was inferred or installed from the token itself, and no gate was relaxed.

A separate candidate-only diagnostic produced no accepted result; no candidate app ID is trusted or recorded as configuration. Owner-confirmed Threads App ID is required. Public repository configuration has only secret-name references, not an independent approved value.

## Preservation and actual effects

The post-preflight metadata check confirmed:

- Night marker unchanged (inode/mode/size/mtime and content digest).
- Beauty token-file state unchanged.
- Protected runtime environment unchanged.
- Live immutable release unchanged.
- Liver token JSON still absent and no Liver unknown marker created.
- **Actual token refresh calls: 0.** The apply controller was not invoked.
- SNS posts, Sheets writes, timer changes and credential overwrites: 0.

The utility is installed but inert; no auto-renewal timer was enabled. The unknown-operation barrier in Night remains in place.

Private, credential-free receipts reside under `/private/tmp/sns-liver-pilot-evidence-20261026/`: baseline, install manifest, preflight, lifecycle diagnostic and preservation verification. The local plan is `/private/tmp/sns-token-renewal-pilot-20261026.md`.

## Required input / safe resumption

Ask the owner for the **Threads App ID** for Liver from Meta for Developers, target application, App settings / Basic / Threads App ID. Do not request the App Secret or token in chat. Check the selected app against owner-controlled configuration; do not silently choose an app or copy a value from another account.

The existing pilot authorization remains conditional on a passing preflight. The blocked run does not authorize pin changes. Once the owner confirms the correct app identity and the scoped configuration action, recheck source/state and repeat read-only preflight. Only then may the previously approved single Liver refresh attempt occur. No real refresh has consumed that one-attempt allowance yet. Any later uncertain refresh result requires the server barrier and manual reconciliation, never blind retry.

## Independent Bank audit

A prepared aggregate-only Bank query was not executed. Automatic approval review rejected execution of this new query on the named VPS and access to Sheets without direct payload/destination approval. No alternate execution path was attempted, and no Bank counts are claimed from it. A separate approval question is pending; it is unrelated to the missing Threads App ID.

That local query is `/private/tmp/sns-bank-live-readonly-20261026.py`, bounded to 420 seconds / 300MB, uses existing validation functions and a dry-run Sheets client, and would return only counts. It does not authorize writing, generation, approval, or publication.

## Remaining rollout limits

This checkpoint is not successful token renewal or production completion. Night recovery, Beauty rollout, Bank minimums, storage/security release, review-writer restoration and signed P0 canaries remain open. `docs/goal-status.json` is unchanged.
