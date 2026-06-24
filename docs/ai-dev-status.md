# AI Dev Status

## Current Status

- Date: 2026-06-24
- Branch: `main`
- Start HEAD: `5e4197eba17c25730d59b400df0113a5ef381169`
- Status: Threads queue worker / metrics import / refill loop implemented; true dry-run fixed; local safety tests PASS; live local Sheets checks blocked by approval credits; GitHub Actions dry_run blocked by missing repository Sheets secrets.

## Latest What Changed

- Added `scripts/process_threads_queue.py` for one-row Threads queue processing.
- Added `scripts/import_threads_metrics_manual.py` for manual Threads insights import.
- Added `scripts/refill_threads_queue.py` for night/liver Threads review queue refill.
- Added `.github/workflows/threads-queue-worker.yml` as manual-only worker.
- Switched `.github/workflows/content-daily-dry-run.yml` to Threads-first queue dry-run/refill dry-run/publisher dry-run.
- Strengthened `posted_results` schema and recovery verification.
- Added local safety tests for worker, duplicate guards, posted_results integrity, metrics import, refill, and workflow safety.
- Added true dry-run tests: no `setup_all()` in queue/refill dry-run and metrics dry-run has no Sheets connection.
- GitHub Actions run `28136692522` and `28136764181`: both failed before queue processing because Sheets secrets were missing in the repository.

## Previous Phase 13 What Changed

- Replaced production source placeholders with user-provided real source URLs.
- Added query source candidates for `night_scout`, `liver_manager`, and `beauty_account`.
- Added safe media asset planning, download/upload gates, and media preflight.
- Added safe video clip execution planner.
- Extended PipelineStore for Phase 13 output stages and queue safety.
- Connected media assets/preflight/clip plans into the source-to-post orchestrator output.
- Hardened publisher and support CLIs for specified dry-run/BLOCKED commands.
- Added Phase 13 production path, media, query, article, publisher, and PDCA tests.

## Test Status

- Phase 9-13 regression and added tests: 39 / 39 PASS, 0 FAIL
- Dry-run / BLOCKED command sweep: 35 / 35 PASS, 0 FAIL

## Remaining Warnings

- Real smoke plan reports NOT_READY when credentials are absent. This is expected in dry-run audit.
- Abstract publisher/fetcher base classes retain `NotImplementedError`.
- Legacy docs/tests mention older NotImplementedError behavior.

## Safety State

- `beauty_account`: `WAITING_REVIEW`, draft-only.
- Real fetch/download/cut/upload/post: not executed.
- Secrets/cookies: not displayed.
- Learning rule auto-activation: not changed.
- Source priority auto-change: not added.
