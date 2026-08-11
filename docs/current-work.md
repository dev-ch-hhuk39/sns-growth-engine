# Current Work

status: V21_SOFTWARE_COMPLETE_THREADS_ZERO_AUTH_DISCOVERY_EXTERNAL_BLOCKED
assigned_agent: Codex
branch: refactor/reference-first-media-core-20260811-20260811-054925
base_head: f0d938c6080ad580eb5e86f46c1ab8b880151565
scope: finalize official Threads optional-auth/oEmbed/search routing, exact YouTube permission activation, future-platform registry, tests and docs
working_tree: v21 bounded implementation; exactly one local checkpoint commit authorized; no push/PR/merge
production_operations: exact owner-authorized YouTube permission rows only; no Cloudinary upload or SNS publish
x_permission_state: OWNER_AUTHORIZED_APPLIED; 24 exact source/account/handle rows verified read-after-write; third-party inheritance false
youtube_permission_state: EXACT_2_OF_2_APPLIED_READ_AFTER_WRITE_PASS; physical A/V and WAITING_REVIEW 2/2 PASS
threads_state: tokenless individual oEmbed live PASS; zero-auth profile-to-permalink discovery unavailable; official Graph optional-auth implemented
safe_next: supply a dedicated Meta app token with approved threads_profile_discovery/threads_keyword_search, or wait for public index/profile payload recovery
do_not_do: reset/clean/rebase/amend/push/PR/merge; do not upload Cloudinary or publish
checkpoint_scope: durable Reference-first code/config/workflows/docs/tests only; local owner context and /tmp evidence excluded
completion_gate: pending final v21 regression; SOFTWARE_COMPLETE target true, PLATFORM_LIVE_EVIDENCE partial only because Threads profile discovery needs external authorization/public recovery, PRODUCTION_PUBLISH_EVIDENCE_COMPLETE=false

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
