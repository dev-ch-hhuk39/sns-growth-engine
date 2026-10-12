# Phase 5B-6K + 6L: read-only Google metadata preflight & mirror canary classifier

**Status: code-only, not provisioned and not run against actual Google accounts.**
No production Sheets/Drive changes, SNS posts, credential loads or VPS
commands were performed. This is not an authorization to activate
`IsolatedSheetsMirrorDelivery(allow_reporting_write=True)`.

## Previous baseline

Phase 5B-6J (merged PR #387) added a disabled-by-default reporting-only
gspread `values.update` adapter, server-scoped service JWT and SQLite
PREPARED-before-write event ledger with no blind retry after an uncertain
outcome. A trusted reviewer can claim the protected mirror outbox.
However, the code did not include an independently verified provider
principal/ACL inspection. Google Sheets itself does **not** provide a
transactional compare-and-swap with the local SQLite queue.

## 6K: current-principal, read-only provider metadata checks

`scripts/media_mirror_readonly_acl_preflight.py` provides
`ReadOnlyGoogleMirrorMetadata` and `read_only_acl_preflight`.

- Requires an **explicitly supplied, separately approved** service account
  credential object with a pinned `service_account_email`. It does
  **not** invoke ADC, open local keys, discover credentials or call
  Google until an operator explicitly calls a GET method.
- Uses only three fixed **GET** endpoints, with bounded field masks,
  8-second timeout, redirect refusal and a 32-KiB response limit:
  1. Google Drive `files.get` for the configured operational
     spreadsheet: exact ID, Sheets MIME type, not trashed,
     `capabilities.canEdit=false` **and**
     `capabilities.canModifyContent=false`.
  2. Google Drive `files.get` for the configured isolated reporting
     spreadsheet: exact ID, Sheets MIME type, not trashed,
     `canEdit=true` and `canModifyContent=true`.
  3. Google Sheets `spreadsheets.get` for reporting only: exact ID,
     unique pinned tab title, `GRID` type, numeric sheet ID,
     adequate row and column dimensions.
- All checks use one credential-bound metadata client and never issue
  `permissions.update`, `values.update`, `batchUpdate`,
  `files.create`, `insertDimension`, or any other mutation.
- Missing/unknown capabilities, 403/404, timeout, inconsistent IDs,
  tab mismatch, or malformed responses **fail closed** with safe codes.
- Passing returns `READ_ONLY_ACL_PASSED_NOT_ACTIVATED`, a non-secret
  target/principal fingerprint, an observation time, and
  `reporting_write_authorized=false`.

**Important limit:** These are observations of capabilities for the current
Google principal at the time of the GET, not proof that all sharing
methods, future ACL changes, group membership, user aliases, sheet
protections or separate credentials are safe. No live provider evidence
exists in this PR. The same actual principal and approved credential
must be used for the future reporting writer; a last-moment ACL
recheck and isolated operator canary are still required.

References:
- Drive files/get:
  https://developers.google.com/workspace/drive/api/reference/rest/v3/files/get
- Drive capability semantics:
  https://developers.google.com/workspace/drive/api/reference/rest/v3/files
- Sheets spreadsheets/get:
  https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/get

## 6L: no-write canary decision support

`scripts/media_mirror_readonly_canary.py` provides
`MirrorReadOnlyCanary`.

- `allow_provider_reads=False` by default, even though it cannot write.
- Takes the exact active, separately authenticated 6J service verifier,
  current 6G signed reviewer **CLAIMED_BLOCKED** outbox record (within
  its bounded reviewer lease), same-DB protected mirror preview and
  only the pinned 6J reporting row.
- New, backwards-compatible binding in
  `GspreadReportingFixedRow.from_trusted_client` captures the
  `client.auth` credential object. A 6L inspection is refused unless
  the Drive metadata reader holds **that same object identity**.
  A direct unbound worksheet, two different credential objects with
  the same email, or a token for another role cannot pass.
- Rejects unresolved PREPARED, OUTCOME_UNKNOWN or CONFLICT deliveries
  for previous event versions before inspecting the reporting row.
- Performs the 6K three-GET ACL check **before** the single existing
  exact-row gspread `get()`. Never calls `update` or mutates SQLite.
- Compares the 12-column, hash-checked, formula-free row to the current
  managed preview. Classification:
  - `MATCHED_BLOCKED`: exact same report copy.
  - `EMPTY_REQUIRES_APPROVAL_BLOCKED`: no existing reporting row.
  - `OLDER_REQUIRES_APPROVAL_BLOCKED`: same protected candidate,
    lower writer version.
  - `CONFLICT_BLOCKED`: foreign candidate or equal/newer version
    that does not match.
  - Any provider/permission/source/row error: fail closed with
    `mirror_canary_evidence_unavailable` or a specific safe code.

All output has `reporting_write_authorized=false`,
`reporting_write_executed=false`, `sqlite_mutated=false`,
`operational_queue_modified=false`,
`sns_publish_authorized=false` and
`requires_separate_operator_approval=true`.

**No code path converts a passing read-only canary into a live write
permit or a media posting permit.** Passing does not mean a production
Google test has been executed. It is not a substitute for Google
workspace/API scope review and production change approval.

## Validation

```bash
python3 scripts/test_media_mirror_readonly_canary.py
python3 scripts/test_media_mirror_reporting_delivery.py
python3 scripts/test_phase5b6h_legacy_sheets_mutation_inventory.py
python3 scripts/test_phase5b6d_network_sink_inventory.py
python3 scripts/run_repository_tests.py
python3 scripts/test_all_workflows_safety_flags.py
python3 -m ruff check --select E9,F63,F7,F82 src scripts
python3 -m ruff check --select F401 \
    scripts/media_mirror_readonly_acl_preflight.py \
    scripts/media_mirror_readonly_canary.py \
    scripts/media_mirror_sheets_adapter.py \
    scripts/test_media_mirror_readonly_canary.py
python3 -m compileall -q src scripts
git diff --check
```

Fixtures contain only ephemeral RSA keys, temp SQLite, isolated gspread
mocks and synthetic provider GET responses. They exercise wrong current
user capabilities, missing Drive fields, expired/revoked sessions,
different credential objects, empty/older/foreign data, unknown prior
delivery, malformed formulas, provider outage and non-mutation. No
Google app connector, live API, real Sheet, VPS or secret was used.

## Next work (heavy approval-dependent stage)

1. Operations must create or select an **independent** Google Workspace
   service identity and a dedicated reporting spreadsheet. Review OAuth
   scopes, actual Drive/Sheets ACL and business ownership. The
   operational spreadsheet must not be editable by that identity.
2. Use the dedicated common VPS management chat to provision the service
   and the disabled-by-default 0010 DB migration after backup/restore
   verification, approvals and monitored deployment. This development
   chat must never access a shared VPS or production secrets.
3. With explicit approval, perform a bounded read-only **real** Google
   preflight first; no actual Google check has been performed here.
4. A separate approval is required for a **reporting-only canary write**
   to a disposable pre-provisioned row. Before any change, confirm
   rollback strategy, external writers isolation, real current ACL and
   unknown outcome handling; do not treat Sheets `values.update`
   as a transactional cross-store CAS.
5. The main operational Sheets -> SQLite source-of-truth cutover still
   needs per-caller review of the 6H legacy writer inventory.
   Independent SNS publisher identity, source-rights check and guarded
   one-use network posting claim remain separate milestones.
