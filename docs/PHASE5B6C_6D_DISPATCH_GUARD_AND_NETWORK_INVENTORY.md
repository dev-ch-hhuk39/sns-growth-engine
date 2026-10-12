# Phase 5B-6C + 6D — Local dispatch staging & network sink inventory

## Completed scope (development code only, no live posting)

Base main: `f5d1628f6de4c7623f9c8bedd99e9460438d69ca`, merged
Phase 5B-6B PR #381.

Phase **5B-6C** adds migration
`db/migrations/0005_sns_media_dispatch_guards.sql` and
`scripts/media_dispatch_guard.py`. These introduce an append-only SQLite
dispatch-preparation journal, linked by foreign key to the previously guarded
media intent. This is a **local-only blocked state machine**, not a source
of production publish permissions.

Phase **5B-6D** inventories current Python HTTP write sinks in
`scripts/test_phase5b6d_network_sink_inventory.py`, tightens the
Threads media creation primitives and runs the inventory in PR CI.
This catches accidental new direct write paths, but is a static heuristic:
dynamic imports, alternate HTTP clients and runtime routing require separate
security review and platform-side egress controls.

### 6C trusted preconditions (no request-supplied authorization)

- Explicit, manual migrations 0001 through 0005 in order on a private
  SQLite volume. Both reviewer and intent ledgers must be in this same DB.
- Caller-injected `PinnedRS256SessionVerifier`, live per-account reviewer
  RBAC, active revocable session and MFA. Source and protected proof vault
  must also use the same SQLite connection. No user-provided identity,
  receipts, mock source, environment toggle or JSON approval is trusted.
- The existing intent must be `HELD_BLOCKED`, unexpired, not reused, with
  the precise expected version and event hash. The original review
  must still have an active head and a `MATCHED_BLOCKED` queue binding,
  and the bound source, caption, media ID, proof metadata and permissions
  must match a newly fetched trusted canonical snapshot. Revoked proof,
  stale rights, changed caption, expired verification, disabled grant or
  explicit reviewer session revocation deny staging.
- `BEGIN IMMEDIATE`, foreign keys, unique media/content reservation and
  optimistic head version/hash updates ensure no second **local** staging
  action can succeed for that candidate. Parent source record and events
  are verified under the same transaction. A fail-injected event write
  rolls back its head row.

### State machine (all states are permanently non-authorizing)

| Operation | Local state | Effects |
|---|---|---|
| `stage` | `STAGED_BLOCKED`, for at most 60 seconds | One SQLite head + immutable journal event |
| `RECHECK` with matching source/rights | Stays `STAGED_BLOCKED` | No new journal event |
| `RECHECK` with expiry/drift/revocation/source outage | `DRIFT_BLOCKED` | Terminal; no reuse or auto-retry |
| `CANCEL` with authorized reviewer | `CANCELLED_BLOCKED` | Terminal even if external queue is offline |
| `MARK_UNCERTAIN` after unverified external outcome | `OUTCOME_UNCERTAIN_BLOCKED` | Terminal; records manual uncertainty, never retry |
| `inspect` | Read-only state inspection | Hash-chain consistency checks |

All returned results have `publish_authorized=false`,
`dispatch_allowed=false`, `publish_attempted=false`,
`effective_approval=false`, and
`external_queue_atomicity_guaranteed=false`.

This journal does **not** issue an execution permit, call Threads, change
`READY`, write Sheets, upload to Cloudinary, or connect the live IdP.
Even a successful `STAGED_BLOCKED` must never be passed to a real SNS
network sender. The Phase 5B-6A real-media network interlock remains
unchanged and mandatory.

### 6D sink inventory

The static inventory lists and counts the present direct Python
`requests.post` / HTTP write calls and fails CI when these change without
an explicit approved update. At this revision, legitimate write sinks are
in:

- `src/publishers/threads_publisher.py`: four `requests.post` calls
  (container creation + publish)
- `src/publishers/x_publisher.py`: one call (outside current Goal scope)
- `src/llm_client.py`, `src/generation/reference_source_rewriter.py`,
  `src/generation/source_grounded_caption.py`: external LLM endpoints
- `src/media/cloudinary_client.py`: media upload endpoint
- `src/transcription/cloudflare_whisper_client.py`,
  `scripts/gemini_hybrid_client.py`: `urllib.request.Request` POST calls

`src/publishers/threads_publisher.py` also refuses **direct helper**
calls to `_create_container` for image/video/carousel types, even if all
environment flags are true, and refuses all direct calls to
`_create_carousel_container` before making an HTTP request. Existing text
creation and its safety gates are preserved.

`scripts/recover_orphan_threads_post.py` only performs read-only Threads
API retrieval and local recovery writes; it does not issue a new SNS post.
Recovery operations and all direct Sheets clients remain subject to the
separate audit and production authorization process.

### Validation

```bash
python3 scripts/test_media_dispatch_guard.py
python3 scripts/test_phase5b6d_network_sink_inventory.py
python3 scripts/test_phase5b6a_media_runtime_interlock.py
python3 scripts/test_media_publish_intent_authority.py
python3 scripts/run_repository_tests.py
python3 scripts/test_all_workflows_safety_flags.py
python3 -m ruff check --select E9,F63,F7,F82 src scripts
python3 -m compileall -q src scripts
git diff --check
```

The test suite uses temporary SQLite DBs, ephemeral RS256 keys and
fake operational sources; no production Secrets, Threads posts or Google
Sheets mutations are involved.

## Remaining production blockers / next priorities

1. **No single authoritative operational queue exists yet.** SQLite can
   atomically stage an intent relative to local reviews, but it cannot
   freeze or write the current Google Sheets queue transactionally.
   Any queue/permission change after the trusted snapshot read may race.
   The correct solution is a server-owned canonical queue + review + dispatch
   state in **one ACID transaction**, plus reconciliation to Sheets used as
   a view/mirror. Do not treat a local 60-second stage as atomic Sheets lock.
2. **Actual dispatch needs a distinct, scoped service identity**, not a
   reused reviewer token. Current operator claims are authenticated audit
   staging only. Provision IdP integration, service credentials and roles
   independently.
3. **External APIs lack transactional exact-once delivery.** A timeout after
   Threads accepted a post requires an `OUTCOME_UNCERTAIN` path and later
   API-based reconciliation. No silent retry or duplicate publish.
4. **Network sink inventory is not a sandbox.** Production defense needs
   egress/firewall allowlisting, secrets separation, validated deployments,
   signed release acceptance and end-to-end tests including alternative
   libraries and workflows. Direct Python calls outside repository tests
   can still reach external APIs if OS access is unrestricted.
5. **No media release flag is enabled.** Phase 5B-6A interlock must remain
   active until the canonical queue+review+publish authority is built and
   the end-to-end user-approved production canary passes.

## Common VPS handoff — execute only in dedicated VPS chat

No VPS, deploy, service restart, cron, production migration or real post
was performed in this development chat. No immediate deployment is requested.
Any later deployment must run the common deploy lock and resource preflight,
preserve current service state and backups, perform restore rehearsal,
apply migration 0005 in a private environment only after approvals, and
confirm the media network stop is still enforced on the merged release.
