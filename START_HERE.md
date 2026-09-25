# SNS Growth Engine - Current Work

Updated: 2026-09-25

## Current task

- Base main: `ecfddbd9440e4284623e33c2ed44ad944b62d0b2`.
- Branch: `fix/xserver-primary-media-replenishment`.
- Objective: close production reliability gaps for the existing Text V1, Media V1, buffered runtime, Xserver scheduler and reconciler. No architecture redesign and no relaxation of rights, quality, publisher or account-isolation gates.
- Changes add a bounded Xserver media-preparation cron using existing Direct and approved-clip preparation commands, and correct acceptance metrics to separate text slot coverage from media inventory and use the actual publisher's non-posting dry-run for usable-media counts.
- GitHub media preparation is explicit-confirmation/manual fallback only; Xserver remains the single natural preparation scheduler. Publisher/X gates are forced off in preparation children.

## Evidence and limits

- Focused contracts, 923/923 repository regression, Ruff fatal rules, Python compilation, workflow YAML parsing, source registry validation, 116-check completion audit, 509 workflow safety checks, workflow permissions/capability registry, and `git diff --check` pass. Exact-head PR CI and post-merge deployment are pending.
- Live pre-change read-only snapshot: Xserver disk 72.31%, preparation permitted. Text READY coverage calculation was wrong (58.33%) because it counted media slots; observed text slots were all covered. Actual publisher dry-runs showed Night Direct/Clip 3/3, Liver Direct/Clip 4/3, Beauty Direct 3. Evergreen bank Night/Liver/Beauty 50/30/50. Current-scope duplicate, unverified and missing-metrics counts were zero; legacy audit remains separate and unchanged.
- Runtime secret-presence check found Cloudinary credentials missing before redeploy. The deployment workflow now stages required existing Cloudinary/Gemini runtime secrets without printing values; preparation must still fail closed if Cloudinary usage cannot be verified.
- No media cleanup, historical Sheets mutation, publish, Cloudinary upload or manual post was initiated during local implementation. Natural replenishment remains unverified until an Xserver cron run follows deployment.
- Preserve untracked `.runtime/`; never stage, clean, or delete it.

## Next steps

1. Complete full local regression and inspect the final diff.
2. Commit and push the one focused branch/PR; wait for exact-head required CI and merge normally.
3. Deploy merged main to the existing Xserver runtime and verify runtime revision, cron, service, disk and secret presence (presence only).
4. Run read-only production readiness; then verify a natural Xserver preparation cycle refills routes to their minimums. Manual dispatch is not natural-run evidence.
5. Verify Text 72-hour coverage, evergreen reserve, current duplicate/unverified counts, read-after-write, metrics and PDCA without altering historical evidence.
6. Claim `FULL_SCHEDULE_PRODUCTION_COMPLETE=YES` only if every requested production condition is evidenced; otherwise list the exact external/runtime blocker.

## Safety

- Never publish from preparation; never post to X or Beauty outside existing account gates.
- Never weaken rights/provenance, persona/quality, account isolation, duplicate/idempotency, read-after-write, or kill-switch checks.
- Do not remove production data, assets, queues, evidence, logs, credentials, current release, or `.runtime/`.
