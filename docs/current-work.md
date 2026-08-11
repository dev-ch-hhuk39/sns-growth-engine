# Current Work

status: REFERENCE_FIRST_SOFTWARE_AND_INTEGRATION_COMPLETE_EXTERNAL_BLOCKERS_ONLY
assigned_agent: Codex
branch: refactor/reference-first-media-core-20260811-20260811-054925
base_head: 2a886b8e79d833300081688ecc841965ee15ca64
scope: reconcile active acquisition/media/review paths and durable docs to the Reference-first Source of Truth
working_tree: validated checkpoint candidate; one local commit is authorized by CODEX_CHECKPOINT_TASK.md and should leave tracked state clean
production_operations: only the explicitly authorized media_permissions activation was performed; Cloudinary/upload/publish were not
x_permission_state: OWNER_AUTHORIZED_APPLIED; 24 exact source/account/handle rows verified read-after-write; third-party inheritance false
safe_next: obtain explicit X auth or a registered-author video-bearing individual status for each account, then rerun bounded X Golden
do_not_do: reset/clean/rebase/amend/push/PR/merge; do not upload Cloudinary or publish
checkpoint_scope: durable Reference-first code/config/workflows/docs/tests only; local owner context and /tmp evidence excluded
completion_gate: PASS; SOFTWARE_COMPLETE=true, INTEGRATION_COMPLETE=true, PRODUCTION_EVIDENCE_COMPLETE=false; 820/820 repository tests and 455/455 workflow safety

## 2026-08-11 Agent Reach and Owner Permission Activation

- Agent Reach 1.5.0 was installed from the official repository at commit
  `1221ecd0c3e0502ee37406f03543bedf7503f2c7` into
  `~/.agent-reach-venv`. Doctor measured 4/15 usable channels. The repo adapter
  now calls official WebChannel behavior and remains optional/analysis-only.
- Live bounded probes: YouTube metadata/captions passed for both accounts;
  Threads and TikTok profile text was readable only through generic Web and did
  not discover individual posts; X required explicit authentication.
- The owner decision covered 24 exact identities: Night Scout X 10, Threads 8;
  Liver Manager X 2, Threads 1, TikTok 3. Two missing Night X handles received
  collision-free source IDs. No Night TikTok or blanket YouTube/note permission
  was added.
- Production `media_permissions` activation was explicitly authorized for this
  task. Final apply was idempotent (`written=0`, `updated=24`) and read-after-
  write passed. No Cloudinary upload, SNS publish, or mass operation occurred.
- X Golden remains externally blocked: the known Night status had no video;
  registered-profile discovery requires explicit auth, and no Liver individual
  status was available. Do not weaken author provenance or infer a URL.
