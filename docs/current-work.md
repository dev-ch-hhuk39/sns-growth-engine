# Current Work

status: V1_FINAL_DIRECT_MEDIA_PR_READY
assigned_agent: Codex
branch: fix/v1-direct-evidence-voice-final-20260827
base_main: 2f1749d4167d91d8c4d6d45ef0abdb3333bb00df
scope: finish strict autonomous Direct Media READY for Night Scout and Liver Manager, retain Beauty human review, then prove production E2E
working_tree: intentional implementation changes plus untracked runtime data; never reset or clean
production_operations: after normal merge, bounded preparation and read-after-write verification; Direct publisher dry-run only for this acceptance

## Completed locally

- Liver deterministic evidence caption produces canonical female-manager voice while preserving source claims.
- Stored uploaded media requiring understanding refresh is prioritized ahead of new external acquisition.
- Source posts without usable original text are rejected before network/download cost.
- Downstream caption/alignment/persona/public validation failures are separated from physical media failures.
- Legacy downstream-only false quarantine and pre-fix blocked queues have bounded one-time recovery.
- Direct preparation promotes at most one strict Hybrid-approved Night/Liver candidate to READY.
- Autonomous READY CLI requires explicit apply confirmation and performs no publishing.
- Beauty is structurally excluded from autonomous READY and remains human-review-only.
- Direct Media focused tests 46/46, repository tests 876/876, pytest 146/146, completion audit 100/100, workflow safety 504/504 PASS.

## Remaining sequence

1. Commit/push/PR/exact-head CI/normal merge/main sync.
2. Liver production Direct preparation: require `READY`, non-empty queue ID, and Sheets read-after-write.
3. Liver Direct scheduled publisher path: dry-run only.
4. Night production Direct preparation: READY when eligible, otherwise exact fail-closed reason.
5. Beauty preparation: reviewable WAITING_REVIEW only.
6. Night/Liver text route dry-runs, active workflow/schedule/config audit.
7. Final evidence report; only then decide whether the Owner's V1 completion sentence is truthful.

## Do not do

- Do not weaken safety, rights, permission, provenance, account, persona, semantic, quality, or Hybrid AI gates.
- Do not auto-approve Beauty or publish to X.
- Do not commit `.runtime/`, `.ai-tmp/`, secrets, tokens, cookies, or storage state.
- Do not claim production evidence from local tests or dry-runs.
