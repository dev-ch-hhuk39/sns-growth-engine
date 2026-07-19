# SNS Growth Engine Completion Goal

This repository is complete only when the machine-readable acceptance criteria
in `config/goal_acceptance.json` all have real production evidence and
`python3 scripts/evaluate_goal.py` exits with status 0.

The required production system:

- discovers posts from approved Threads, YouTube, and TikTok account URLs;
- keeps source text and every media item attached to one source-post identity;
- prepares direct-reference media posts and transcript-grounded generated clips;
- validates rights, media integrity, public text, and semantic alignment;
- stores media in Cloudinary and state/evidence in Google Sheets;
- posts the configured Night Scout and Liver Manager slots through the official
  Threads publishing path;
- recovers delayed slots without duplicate posts and quarantines repeatedly
  failing assets;
- runs production only on finite standard GitHub-hosted jobs;
- never fetches or posts X and never activates or posts `beauty_account`.

Mock, fixture, dry-run, workflow-success, text-fallback, or permalink-only
evidence cannot satisfy a media acceptance criterion. Optional CPU/GPU-heavy
generators may be unavailable on the free standard runner, but direct-media
reuse and approved YouTube/TikTok clipping are required.

Current evidence is tracked in `docs/goal-status.json` and
`docs/goal-evidence.md`. Secrets, cookies, tokens, storage state, source media,
and production-only configuration must never be committed.
