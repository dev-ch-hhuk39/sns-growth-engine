# Autonomous Mode Runbook

Date: 2026-07-07

## Purpose

Autonomous mode allows the reviewed text-only Threads pilot to run without per-post human approval. It is rules-based automation, not an unrestricted bot.

Initial scope:

- Accounts: `night_scout`, `liver_manager`
- Posting platform: Threads only
- Source fetch platforms: Threads and reviewed YouTube metadata/reference paths only
- Media: disabled
- X: disabled for fetch and post
- `beauty_account`: blocked

## Configuration

Primary config:

```bash
config/autonomous_mode.json
```

Important initial values:

- `autonomous_mode_enabled=true`
- `auto_source_fetch_enabled=true`
- `auto_idea_generation_enabled=true`
- `auto_ready_enabled=true`
- `auto_post_enabled=true`
- `human_review_required=false`
- `daily_post_cap_per_account=5`
- `daily_ready_cap_per_account=8`
- `max_posts_per_run=1`
- `cooldown_minutes=90`
- `max_similarity_to_source=0.45`
- `kill_switch=false`

Existing `config/auto_approval_rules.json` remains integrated for legacy AUTO_READY policy and safety defaults. Autonomous priority order is:

1. kill switch
2. account/platform block
3. rights/media block
4. safety/risk/similarity
5. daily cap/cooldown
6. auto_ready/auto_post gates

## Current Autonomous Sources

The first autonomous pilot uses only reviewed source candidates:

| account_id | source_id | platform | URL | use |
|---|---|---|---|---|
| `night_scout` | `src_ns_threads_required_001` | threads | `https://www.threads.com/@kyaba_ryo` | public reference metadata/text |
| `night_scout` | `src_ns_threads_required_002` | threads | `https://www.threads.com/@mizuno9120` | public reference metadata/text |
| `liver_manager` | `src_lm_yt_cand_001` | youtube | `https://www.youtube.com/@suu-san_pococha` | metadata/transcript analysis only, no download |

TODO placeholders, X sources, beauty sources, unknown-rights media, and media pipeline rows are excluded.

## Commands

Dry-run, no posting:

```bash
python3 scripts/run_autonomous_loop.py --account-id all --dry-run
```

Production apply command:

```bash
python3 scripts/run_autonomous_loop.py --account-id all --apply --confirm-autonomous
```

There is no per-post approval prompt in autonomous mode. The explicit run approval is the command-level `--confirm-autonomous` gate plus the rules in `config/autonomous_mode.json`.

## GitHub Actions

Workflows:

```bash
.github/workflows/autonomous-growth-loop.yml
.github/workflows/autonomous-growth-loop-night-scout.yml
.github/workflows/autonomous-growth-loop-liver-manager.yml
```

The manual workflow is `workflow_dispatch` only. The account-specific workflows have schedules and fixed `ACCOUNT_ID`; scheduled runs apply automatically while preserving the real-post gates.

### Actions Enablement And Firing Check

As of 2026-07-09 JST, GitHub Actions is enabled for the repository and these autonomous workflows are `active`:

- `Autonomous Growth Loop Night Scout`
- `Autonomous Growth Loop Liver Manager`
- `Autonomous Growth Loop`

The account-specific scheduled workflows are firing. Recent observed scheduled runs:

- Night Scout: run `29003612060`, event `schedule`, conclusion `success`, created `2026-07-09T08:05:56Z`
- Liver Manager: run `29000408859`, event `schedule`, conclusion `success`, created `2026-07-09T07:04:06Z`

Important distinction: a green scheduled run can still mean `NO_POST`. In the 2026-07-09 runs, the workflows reached **Apply autonomous Threads loop**, but `health_summary.posted_count=0` and `health_summary.no_post_reason=NO_READY_QUEUE`. That is a queue/auto-ready issue, not an Actions firing issue.

GitHub UI checks when a user sees "not running":

1. Open **Actions**.
2. Select **Autonomous Growth Loop Night Scout** or **Autonomous Growth Loop Liver Manager**.
3. Confirm the banner does not say the workflow is disabled.
4. If disabled, click **Enable workflow**. This only enables the workflow; it does not post immediately.
5. Open the latest scheduled run and check the first steps: **Schedule heartbeat**, **Dry-run autonomous plan**, then **Apply autonomous Threads loop** for scheduled events.
6. Read `health_summary.no_post_reason` before assuming the schedule failed.

Equivalent read-only CLI checks:

```bash
gh workflow list --all
gh run list --workflow "Autonomous Growth Loop Night Scout" --limit 10
gh run list --workflow "Autonomous Growth Loop Liver Manager" --limit 10
gh run view <run_id> --log
```

If a workflow is disabled and a maintainer explicitly wants to re-enable it:

```bash
gh workflow enable "Autonomous Growth Loop Night Scout"
gh workflow enable "Autonomous Growth Loop Liver Manager"
```

Do not use `gh workflow run` for immediate apply unless the user explicitly asks for a manual run.

### First Apply From GitHub UI

Use GitHub Actions for the first real autonomous apply because the local Codex approval reviewer can block real-post capable commands.

1. Open the repository on GitHub: `dev-ch-hhuk39/sns-growth-engine`.
2. Open the **Actions** tab.
3. Select **Autonomous Growth Loop**.
4. Click **Run workflow**.
5. Set `confirm_autonomous` to `true`.
6. Set `account_id` to `all` for the first combined pilot, or choose `night_scout` / `liver_manager` for a narrower run.
7. For a smoke test with no apply/post, set `dry_run_only=true`. This runs **Dry-run autonomous plan** and **Autonomous health summary** only.
8. Click **Run workflow**.
9. Open the created run and confirm **Dry-run autonomous plan** completed before **Apply autonomous Threads loop**.
10. If the run fails, read the failing step summary first. The expected safe failures are missing secrets, `kill_switch=true`, Sheets verify failure, source selection empty, daily cap/cooldown, or publisher credential failure.
11. Confirm the posted URL in the workflow log summary and in Google Sheets `posted_results`. If the Threads post succeeded but Sheets save failed, use the `POSTED_SAVE_FAILED` fallback/recovery path rather than retrying blindly.

Do not enable X, beauty, media, download, cut, upload, Cloudinary, or transcription flags for this workflow.

The workflow sets:

- `PUBLISH_ENABLED=true`
- `ALLOW_REAL_THREADS_POST=true`
- `ALLOW_REAL_X_POST=false`
- `ALLOW_VIDEO_DOWNLOAD=false`
- `ALLOW_VIDEO_CUT=false`
- `ALLOW_CLOUDINARY_UPLOAD=false`
- `ALLOW_TRANSCRIPTION_API=false`

The apply step also checks `config/autonomous_mode.json` and stops when `kill_switch=true`.

The workflow has a required-secrets guard before apply. It stops when the Sheets spreadsheet secret or service-account secret is missing. Threads publisher credentials are checked by `scripts/run_autonomous_loop.py` / the publisher preflight without printing secret values.

Required GitHub Actions secrets for the first `account_id=all` run:

- `SNS_MASTER_SHEET_ID` or `SPREADSHEET_ID`
- `SA_JSON_BASE64` or `GCP_SA_JSON_BASE64`
- `THREADS_ACCESS_TOKEN_NIGHT_SCOUT`
- `THREADS_USER_ID_NIGHT_SCOUT`
- `THREADS_ACCESS_TOKEN_LIVER_MANAGER`
- `THREADS_USER_ID_LIVER_MANAGER`

Optional/unused in the initial text-only run:

- Cloudinary secrets may exist, but `ALLOW_CLOUDINARY_UPLOAD=false` keeps upload disabled.
- Threads app ID/secret may exist for refresh flows, but the autonomous post path relies on the publish credentials above.

### Schedule Policy

The first Actions apply succeeded on run `28571552118`. The original daily combined schedule has been replaced by account-specific schedules.

Current schedules:

```yaml
night_scout:
  # JST 14:00/16:00/18:00/21:00/25:00 targets, cron starts 15 min earlier.
  - cron: "45 4 * * *"
  - cron: "45 6 * * *"
  - cron: "45 8 * * *"
  - cron: "45 11 * * *"
  - cron: "45 15 * * *"

liver_manager:
  # JST 10:00/13:00/16:00/18:00/21:00 targets, cron starts 15 min earlier.
  - cron: "45 0 * * *"
  - cron: "45 3 * * *"
  - cron: "45 6 * * *"
  - cron: "45 8 * * *"
  - cron: "45 11 * * *"
```

Operational rules:

- Scheduled runs apply automatically in the account-specific windows above.
- Each scheduled run sleeps a random `0-1800` seconds before dry-run/apply.
- Each workflow declares `permissions: contents: read` and `actions: read`.
- Each account-specific workflow has `concurrency` with `cancel-in-progress: false` so close schedule slots do not cancel each other.
- Each run prints **Schedule heartbeat** with workflow name, event, account, and UTC time before dependency install.
- Manual dispatch includes `dry_run_only`; when `dry_run_only=true`, guard/apply are skipped even if `confirm_autonomous=true`.
- Manual runs still use `workflow_dispatch` and `confirm_autonomous=true`.
- Keep `max_posts_per_run=1`, `daily_post_cap_per_account=5`, and `cooldown_minutes=90`.
- If a bad post appears, set `kill_switch=true` in `config/autonomous_mode.json`, commit, and push.
- To stop a schedule without changing runtime config, comment out the `schedule` block in the account-specific workflow and push.

Next configured schedule windows from 2026-07-09 18:50 JST:

- `night_scout`: JST 21:00 ±15min, then JST 25:00 ±15min.
- `liver_manager`: JST 21:00 ±15min.

### 2026-07-07 Posting Recovery

Recent scheduled runs were firing but failed before posting. The direct cause was `run_autonomous_loop.py` treating `recover_production_sheets_threads_first.py --verify-only --json` registry reflection failures as a hard blocker:

- `source_registry_reflected`
- `video_sources_reflected`

The runner now records that as a non-blocking warning and lets the actual Sheets/worker steps validate. Source fetch, video reference, and reference scoring failures are also warnings so safe fallback generation can proceed.

Fallback behavior:

- If reference posts/scores are empty, `generate_threads_ideas_from_references.py` creates reader-facing original candidates.
- Candidates are written as `WAITING_REVIEW`.
- `auto_approve_queue.py` promotes only validator-passing text-only candidates to `READY`.
- `process_threads_queue.py` posts only `READY` and reports no-post as JSON.

Health check:

```bash
python3 scripts/check_autonomous_health.py --account-id all --dry-run
```

Check `health_summary` in scheduled run logs:

- `posted_count`
- `ready_count`
- `blocked_count`
- `no_post_reason`

Common no-post reasons:

- `NO_READY_QUEUE`
- `AUTO_READY_REJECTED_ALL`
- `VALIDATOR_BLOCKED_ALL`
- `DUPLICATE_BLOCKED_ALL`
- `DAILY_CAP_REACHED`
- `COOLDOWN_ACTIVE`
- `THREADS_API_FAILED`
- `POSTED_SAVE_FAILED`

### 2026-07-09 READY Recovery

The scheduled workflows were firing, but no post was created when all existing generated queue rows were stale, rejected, or locked. The recovery path now handles this without weakening the final public post validator:

- `generate_threads_ideas_from_references.py` refreshes existing non-locked generated rows (`WAITING_REVIEW`, `REJECTED`, blocked/stale rows) with the current validated public text.
- Existing `READY`, `PROCESSING`, `MEDIA_READY`, and `POSTED` rows are never overwritten.
- If reference-generated rows are all locked/skipped and no queue row is added or refreshed, the runner writes timestamped safe fallback `WAITING_REVIEW` candidates.
- `auto_approve_queue.py` can promote those fallback candidates to `READY` when they pass quality, reader value, account fit, risk, similarity, and internal-leak gates.
- `run_autonomous_loop.py` now reports `AUTO_READY_REJECTED_ALL` when AUTO_READY evaluates rows but selects none, instead of only surfacing the worker-level `NO_READY_QUEUE`.

Expected next scheduled behavior:

1. Generate or refresh at least one safe `WAITING_REVIEW` text-only candidate.
2. AUTO_READY promotes at most one candidate per run.
3. `process_threads_queue.py` posts only `READY`.
4. If no post occurs, inspect `health_summary.no_post_reason`; `AUTO_READY_REJECTED_ALL` means generation quality still failed, while `NO_READY_QUEUE` means no eligible row reached the worker.

## Hard Blocks

Autonomous mode must not:

- post to X
- fetch X
- post or READY `beauty_account`
- download third-party video
- cut video
- upload to Cloudinary
- use transcription API
- post media
- use unknown-rights or third-party media as reusable media
- exceed one post per account per day or one post per run

## Stopping Bad Posts

Fast stop:

1. Set `kill_switch=true` in `config/autonomous_mode.json`.
2. Commit and push.
3. Disable or avoid running the workflow.
4. If a bad Threads post exists, remove/handle it in Threads manually and mark the related Sheets rows for review.

Pause only posting while keeping planning:

1. Set `auto_post_enabled=false`.
2. Keep `auto_ready_enabled` or `auto_idea_generation_enabled` as needed.
3. Re-run dry-run and confirm `auto_post_plan.enabled=false`.

## Rollback

Rollback the autonomous loop by reverting:

- `config/autonomous_mode.json`
- `.github/workflows/autonomous-growth-loop.yml`
- `scripts/run_autonomous_loop.py`

If apply mode ran and posted, do not re-run the same queue row. `process_threads_queue.py` writes `POSTED_SAVE_FAILED` fallback if Sheets save fails, so use recovery scripts rather than retrying blindly.

## Future Media Conditions

Media can only be considered after all are true:

- source has `rights_status` of `owned`, `licensed`, or `approved_creator_clip`
- permission evidence exists
- `allow_media_posts=true`
- `allow_third_party_media` remains false unless explicit legal review changes policy
- Cloudinary/video download/cut flags are intentionally enabled with separate tests

Until then, all source media is reference analysis only.

## Media Growth Engine Boundary (2026-07-04)

Text-only scheduled posting remains ON through the account-specific autonomous workflows. Media Growth Engine is implemented for permitted `liver_manager` sources, but scheduled media posting remains OFF.

Current boundary:

- `approved_creator_clip`, `owned`, or `licensed` plus permission evidence is required before a source can enter the media pipeline.
- `third_party_reference_only`, `reference_only`, `unknown`, `restricted`, and `not_allowed` are blocked from download/cut/upload/video post.
- YouTube channel URLs and TikTok account URLs are not unlimited download sources. A reviewed individual video URL is required for real download/cut.
- Real video download requires `ALLOW_VIDEO_DOWNLOAD=true`, `--download`, and `--confirm-download`.
- Real cut requires `ALLOW_VIDEO_CUT=true`, `--cut`, and `--confirm-cut`.
- Real Cloudinary upload requires `ALLOW_CLOUDINARY_UPLOAD=true`, `--upload`, and `--confirm-upload`.
- Video + text Threads posting requires the media validator, `ALLOW_MEDIA_POSTS=true`, `ALLOW_REAL_THREADS_VIDEO_POST=true`, and `ALLOW_REAL_THREADS_POST=true`.
- `public_post_text` is still the only text allowed to reach the publisher.

Do not enable media posting in scheduled workflows until a separate reviewed production rollout explicitly changes the media gates.

## 2026-07-02 Video Reference Connection

`scripts/run_autonomous_loop.py` now includes a video reference analysis step before scoring and queue work.

- Selected YouTube/TikTok pilot sources are analyzed as reference-only inputs.
- YouTube metadata uses the existing safe metadata/transcript path; channel URLs may return transcript `UNAVAILABLE` because no individual `video_id` exists.
- TikTok is connected only for individual `/video/` URLs. TODO placeholders and profile-only URLs are skipped.
- Transcript body/preview is not returned in autonomous output.
- Generated ideas from video references are text-only Threads candidates. They do not attach media.
- Third-party video download, cut, upload, repost, and Cloudinary upload remain blocked.

Initial production apply attempt on 2026-07-02 was not executed because the local approval reviewer rejected the real-post capable command. Do not work around that gate. Re-run only with an explicit operator approval path for real Threads posting.

## Public Post Quality Gate (2026-07-03)

The 2026-07-03 review found a real `night_scout` Threads post that leaked internal memo text into the public body. The failure pattern was an analysis note such as "今回の切り口は..." being promoted as if it were reader-facing copy.

Current invariant:

- Generation output is treated as `{internal_analysis, public_post_text, safety_notes, blocked_reasons}`.
- Only `public_post_text` may be passed to `ThreadsPublisher`.
- `internal_analysis`, source names, source URLs, score fields, queue ids, result ids, transcript metadata, dry-run/apply labels, and AI notes must never appear in posted text.
- `final_public_post_validator` runs before AUTO_READY and again immediately before posting.
- If the validator fails in the worker, the queue row is changed to `BLOCKED_INTERNAL_LEAK` and no post is sent.

Blocked internal/public-mismatch examples include:

- `今回の切り口`
- `threads /`
- `night_work_scout`, `night_scout`, `liver_manager`
- `source`, `reference`, `source_url`, `source_id`, `queue_id`, `result_id`
- `category`, `usage_scope`, `trend_signal`, `clip_candidate`
- `投稿案`, `生成`, `分解して使う`, `そのまま真似るのではなく`
- `構成・フック`, `投稿アイデア`
- `AI`, `内部`, `metadata`, `transcript`, `PLAN_ONLY`, `AUTO_READY`, `WAITING_REVIEW`, `dry-run`, `apply`, `score`, `safety_score`, `risk_score`

Account copy rules:

- `night_scout`: write to women considering night work, store changes, or side-income anxiety. Use reader-facing posts about anxiety, store selection criteria, common mismatch reasons, and soft consultation. Avoid strong recruitment tone, income guarantees, source names, internal analysis, and AI-like explanations.
- `liver_manager`: write to beginner or struggling streamers. Explain why streaming is hard to start or grow, beginner mistakes, concrete changes, and soft consultation. Avoid gift-begging tone, easy-money claims, office-only promotion, source names, internal analysis, and AI-like explanations.

Account rotation:

- `max_posts_per_run=1` remains unchanged.
- `daily_post_cap_per_account=1` remains unchanged.
- The autonomous loop now prefers the account different from the latest posted account among `night_scout` and `liver_manager`.
- If the preferred account has no postable candidate, fallback to another available account is allowed.

Schedule is now account-specific as of 2026-07-04. If another bad public post appears, set `kill_switch=true`, commit, and push before the next scheduled run.

## Account-Specific Scheduled Operation (2026-07-04)

The old single daily schedule was replaced by account-specific workflows:

- `Autonomous Growth Loop Night Scout`
- `Autonomous Growth Loop Liver Manager`

The manual `Autonomous Growth Loop` workflow is still available for explicit dispatch and `account_id=all`, but it has no scheduled trigger.

Schedules:

| account | JST targets | UTC cron starts |
|---|---|---|
| `night_scout` | 14:00, 16:00, 18:00, 21:00, 25:00 | `45 4`, `45 6`, `45 8`, `45 11`, `45 15` |
| `liver_manager` | 10:00, 13:00, 16:00, 18:00, 21:00 | `45 0`, `45 3`, `45 6`, `45 8`, `45 11` |

Each schedule starts 15 minutes early and applies a random 0-1800 second jitter. Manual dispatch skips schedule jitter because the jitter step runs only when `github.event_name == 'schedule'`.

`max_posts_per_run=1` remains per workflow run. Daily cap is now `5` per account.

## READY Recovery Diagnostics (2026-07-09)

The main operational failure mode is no longer "workflow did not fire"; it is usually one of these queue states:

- `NO_READY_QUEUE`: no `READY` row reached `process_threads_queue.py`.
- `AUTO_READY_REJECTED_ALL`: `auto_approve_queue.py` evaluated candidates but none passed.
- `VALIDATOR_BLOCKED_ALL`: candidates contained internal terms or public-copy risks.
- `DUPLICATE_BLOCKED_ALL`: queue text was too close to an already posted item.
- `DAILY_CAP_REACHED` or `COOLDOWN_ACTIVE`: account-level posting controls stopped the run.

What to inspect:

1. GitHub Actions `health_summary`.
2. Sheets `自動運用ヘルス` / `autonomous_health`.
3. Sheets `投稿キュー` / `queue` columns: `validator_status`, `internal_leak_status`, `account_fit_status`, `rejected_reason`, `blocked_reason`, `public_post_quality_score`.
4. Sheets `投稿結果` / `posted_results`: `queue_id`, `post_url`, `external_post_id`, `posted_text`, `validator_status`, `generation_mode`.

Safe production check before posting:

```bash
python3 scripts/run_autonomous_loop.py --account-id night_scout --apply --confirm-autonomous --stop-before-post
python3 scripts/run_autonomous_loop.py --account-id liver_manager --apply --confirm-autonomous --stop-before-post
```

This mode may write generation/AUTO_READY updates, but it never calls `process_threads_queue.py` and therefore never posts. Running `--stop-before-post` without `--apply --confirm-autonomous` is blocked.

AUTO_READY output now includes:

- `checked_count`
- `approved_count`
- `rejected_count`
- `ready_count`
- `rejected_reasons`
- `sample_rejected_public_post_preview`

If references are empty or stale, safe original fallback candidates are generated as `WAITING_REVIEW`, then AUTO_READY promotes only validator-passing text-only candidates to `READY`. `final_public_post_validator` is not weakened; generation is responsible for producing reader-facing public copy.
