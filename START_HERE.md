# SNS Growth Engine - Current Work

Updated: 2026-09-25

## Current task

- Current main: `2697ed64aff20f5145554bff8e7a804732c9d479` (PRs #346/#347 merged); base for the pending pip fix: PR #347.
- Follow-up branch: `fix/xserver-pinned-pip-bootstrap` (to be created from current main).
- Objective: close production reliability gaps for the existing Text V1, Media V1, buffered runtime, Xserver scheduler and reconciler. No architecture redesign and no relaxation of rights, quality, publisher or account-isolation gates.
- Changes add a bounded Xserver media-preparation cron using existing Direct and approved-clip preparation commands, and correct acceptance metrics to separate text slot coverage from media inventory and use the actual publisher's non-posting dry-run for usable-media counts.
- GitHub media preparation is explicit-confirmation/manual fallback only; Xserver remains the single natural preparation scheduler. Publisher/X gates are forced off in preparation children.

## Evidence and limits

- Focused contracts, 923/923 repository regression, Ruff fatal rules, Python compilation, workflow YAML parsing, source registry validation, 116-check completion audit, 509 workflow safety checks, workflow permissions/capability registry, and `git diff --check` passed for PR #346. PR #347 checks passed. Exact-head CI for the pip bootstrap fix remains pending.
- Live pre-change read-only snapshot: Xserver disk 72.31%, preparation permitted. Text READY coverage calculation was wrong (58.33%) because it counted media slots; observed text slots were all covered. Actual publisher dry-runs showed Night Direct/Clip 3/3, Liver Direct/Clip 4/3, Beauty Direct 3. Evergreen bank Night/Liver/Beauty 50/30/50. Current-scope duplicate, unverified and missing-metrics counts were zero; legacy audit remains separate and unchanged.
- Required repository secret NAMES for Cloudinary/Gemini are present. Deploy `36112819390` failed on the line-count check; PR #347 fixed it. Deploy `36113687899` passed env validation but pip 22.0.2 hit an internal resolver AssertionError while installing media requirements. Current release/cron remain unchanged; runtime.env is mode 0600 and contains the authorized deployment variables. A pinned pip bootstrap fix is pending.
- No media cleanup, historical Sheets mutation, publish, Cloudinary upload or manual post was initiated during local implementation. Natural replenishment remains unverified until an Xserver cron run follows deployment.
- Preserve untracked `.runtime/`; never stage, clean, or delete it.

## Next steps

1. Merge the pinned pip bootstrap follow-up after required CI.
2. Deploy latest main to the existing Xserver runtime and verify runtime revision, cron, service, disk and secret presence (presence only).
3. Run read-only production readiness; then verify a natural Xserver preparation cycle refills routes to their minimums. Manual dispatch is not natural-run evidence.
4. Verify Text 72-hour coverage, evergreen reserve, current duplicate/unverified counts, read-after-write, metrics and PDCA without altering historical evidence.
5. Claim `FULL_SCHEDULE_PRODUCTION_COMPLETE=YES` only if every requested production condition is evidenced; otherwise list the exact external/runtime blocker.

## Safety

- Never publish from preparation; never post to X or Beauty outside existing account gates.
- Never weaken rights/provenance, persona/quality, account isolation, duplicate/idempotency, read-after-write, or kill-switch checks.
- Do not remove production data, assets, queues, evidence, logs, credentials, current release, or `.runtime/`.
