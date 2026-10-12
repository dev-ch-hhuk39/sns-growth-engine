# Phase 5B-6P — Independent operator authentication and MFA proof gate

**Source-code only. No real sign-in, IdP connection, credential handling,
Google Drive/Sheets call, reporting PUT, shared VPS operation or SNS post.**

## Previously unresolved trust gap

6N requires two different, signed short-lived operator approvals and 6O
enforces current, narrowly scoped human authorization grants. However,
those checks did **not** require a distinct identity provider to certify
the operator's actual authentication session and recent MFA. A valid
cryptographic canary signature or a grant alone cannot prove a person
recently signed in with phishing-resistant MFA.

6P adds a **separate, pinned RS256 identity-proof verifier**, an
independent server-controlled IdP session journal and required binding
from the original operator signatures to their IdP proof fingerprints.

## Files and contracts

- `db/migrations/0013_sns_canary_idp_sessions.sql`:
  an opt-in private SQLite session record with exact
  `subject`, `issuer`, `signer_kid`, `token_jti`,
  `assertion_sha256`, authentication/MFA times, issue/expiry,
  `authentication_profile`, `enabled`, `revoked_at`, and
  trusted provisioner metadata.
  Sessions default disabled, cannot be retargeted/deleted, and are
  terminal once disabled or revoked. A new sign-in requires a fresh
  session/JTI/token digest. **This migration has not been run in production.**
- `scripts/media_mirror_operator_idp.py`:
  `PinnedOperatorIdpSessionVerifier`, with a separate
  server-pinned IdP signing public key set. It verifies:
  - exact RS256 signature; no dynamic JWK discovery or caller-supplied
    signing keys, no unsigned or HS256/none fallback;
  - an explicit `sns-growth-canary-human-identity` audience,
    `canary_operator_identity` token use and
    `canary:human:identify` scope;
  - distinct configured IdP issuer, expected human subject and
    signed session ID;
  - signed `amr` including both `mfa` and `webauthn` plus
    an explicit custom profile `urn:chadult:acr:phishing-resistant`;
  - recent authentication and MFA times and a token lifetime at
    most five minutes, checked against an independently supplied
    clock;
  - exact SHA-256 hash, JTI, claims and times matching an active,
    unrevoked IdP session provisioned in the protected SQLite DB.
  Any missing registry, disabled session, forged JWT, wrong audience,
  missing MFA, stale evidence or changed token fingerprint fails closed.
- `scripts/media_mirror_canary_approval.py`: each of the two
  separately signed operator-approval JWTs now **also binds**
  `idp_session_id` and `idp_assertion_sha256`. Both distinct
  IdP assertion JWTs must be supplied to verification.
  The same proofs are revalidated at the **last pre-PUT authorization
  check**, using their original protected signoff record. The
  second factor is not merely a client-supplied boolean.
- `scripts/media_mirror_reporting_delivery.py`:
  opt-in reporting delivery refuses enablement if the protected
  IdP verifier is absent, bound to a different database, or uses
  an issuer/signing key shared with the operator-approval service
  or reporting service. `deliver_once` now requires **two**
  distinct IdP proofs in addition to the 6N operator approvals
  before it can even prepare a possible reporting write.
  The default remains **`allow_reporting_write=False`**.

A revoked IdP session after PREPARED but before the optional provider
PUT stops any PUT, preserves the blocked/unknown outcome and does not
permit a blind retry. Read-only reconciliation of a past uncertain
reporting write remains possible with its separately scoped service
identity, even after one original human's authentication session is
revoked; reconciliation does not reauthorize a new write.

**The IdP assertions and operator approvals are never persisted in
plaintext.** The IdP journal contains only verified metadata and
a token fingerprint; the 6N journal holds approval-signature digests.

## Human authentication and provider constraints

This phase implements a strict **verification interface**, NOT a
working sign-in flow. A real trusted external IdP/approval issuer
must independently authenticate each human, perform genuine
phishing-resistant MFA, issue assertions conforming to this custom
profile, provision the protected SQLite session through a privileged,
audited server-only callback, and maintain revocation/key rotation.
The signing system that issues each *operator approval* must bind the
IdP proof fingerprint to the exact human and exact requested canary.

Do not rely on a signed `amr` or `acr` field emitted by an
unverified producer. Real operational evidence must establish that
those claims are enforced by the provider and reflect actual
authentication. This repo does not possess or mint production IdP
credentials, or have authority to assign a real staff user's role.

No OAuth/API scopes, Google service account files, Drive ACLs or
Google reporting workbooks have been inspected or changed in this
PR. A real provisioner must separately validate the service account
does not have write access to operational Sheets. Sheets
`values.update` still cannot atomically CAS with SQLite; ACL or
session revocation after the final check remains a TOCTOU risk.

The optional `as_of` argument is only for offline test clock
injection and must not be exposed in future untrusted runtime APIs.

## Offline validation

```bash
python3 scripts/test_media_mirror_operator_idp.py
python3 scripts/test_media_mirror_operator_grants.py
python3 scripts/test_media_mirror_canary_approval.py
python3 scripts/test_phase5b6h_legacy_sheets_mutation_inventory.py
python3 scripts/test_phase5b6d_network_sink_inventory.py
python3 scripts/run_repository_tests.py
python3 scripts/test_all_workflows_safety_flags.py
python3 -m ruff check --select E9,F63,F7,F82 src scripts
python3 -m compileall -q src scripts
git diff --check
```

Tests use temporary SQLite, ephemeral signing identities, and
synthetic Drive/Sheets responses. They cover missing/wrong IdP JWTs,
unsigned/incorrect signing profile, bad MFA/ACR/AMR/time claims,
different human's JWT, missing/disabled/expired/revoked IDP sessions,
post-PREPARED session revocation, operator replay and read-only
reconciliation. **No real human authentication event took place.**

## Outstanding operational acceptance items

1. Independent real identity-provider/approver system: staff enrollment,
   verified user identities, phishing-resistant MFA enforcement,
   issuer and key lifecycle, privileged protected session provisioner,
   per-account operator grants and two-person approvals.
2. A separately approved reporting-only Google service account and
   disposable workbook with read-only proof that the operational
   workbook is not editable by that principal.
3. Security-reviewed migration and configuration for 0010–0013,
   secrets isolation, backup/restore, rollback and monitoring by the
   dedicated common VPS management chat.
4. Read-only real Google preflight, followed **only after separate
   explicit approval** by a one-row reporting-only canary. Never
   confuse that with operational queue cutover or SNS publication.
5. Distinct approval and rights gate for any future real SNS media
   publishing; the existing unconditional media network stop remains.
