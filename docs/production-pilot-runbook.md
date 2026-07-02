# Production Pilot Runbook

Date: 2026-07-02

This pilot is a small source-fetch validation step. It is not full automation.

## 2026-07-02 Autonomous Pilot Update

`config/autonomous_mode.json` now enables a command-level autonomous mode for text-only Threads operation. This means the user does not need to approve every individual post, but hard gates still apply:

- `night_scout` / `liver_manager` only.
- Threads posting only.
- X fetch/post remains blocked.
- `beauty_account` remains blocked.
- Media posts, third-party media, video download/cut, Cloudinary upload, and transcription API remain blocked.
- Daily cap is 1 post per account, with max 1 post per run.
- `kill_switch=true` stops the autonomous workflow.

Autonomous dry-run:

```bash
python3 scripts/run_autonomous_loop.py --account-id all --dry-run
```

Autonomous apply requires explicit command-level confirmation:

```bash
python3 scripts/run_autonomous_loop.py --account-id all --apply --confirm-autonomous
```

The first selected autonomous sources are the same pilot candidates listed below.

## Purpose

Validate that a tiny, reviewed set of source URLs can be enabled for reference collection without enabling posting, X fetch/post, media download, media cut, Cloudinary upload, transcription API, or AUTOPOST.

## What Can Be Enabled First

Only sources that satisfy all conditions may be considered:

- Real `source_url` is present.
- Target account is `night_scout` or `liver_manager`.
- Platform is `threads`, `youtube`, or an individual TikTok `/video/` URL.
- X is excluded.
- `beauty_account` is excluded.
- TODO placeholders are excluded.
- `rights_status` is `reference_only`, `third_party_reference_only`, `owned`, `licensed`, or `approved_creator_clip`.
- `unknown` rights are excluded from the first pilot.
- Media download/cut/upload remains disabled.

## Current Pilot Candidates

These are dry-run candidates only. `fetch_enabled` is still `false`.

| account_id | source_id | platform | source_url | rights_status | pilot use |
|---|---|---|---|---|---|
| `night_scout` | `src_ns_threads_required_001` | threads | `https://www.threads.com/@kyaba_ryo` | reference_only | reference metadata/text collection |
| `night_scout` | `src_ns_threads_required_002` | threads | `https://www.threads.com/@mizuno9120` | reference_only | reference metadata/text collection |
| `liver_manager` | `src_lm_yt_cand_001` | youtube | `https://www.youtube.com/@suu-san_pococha` | reference_only | metadata/transcript analysis only |

## Pilot Apply Procedure

Dry-run first:

```bash
python3 scripts/prepare_pilot_sources.py --account-id all --max-per-account 2 --dry-run
python3 scripts/collect_source_posts.py --platform threads --account-id all --dry-run
python3 scripts/run_growth_loop.py --dry-run --account-id all
```

Apply only after human review:

```bash
python3 scripts/prepare_pilot_sources.py --account-id all --max-per-account 2 --apply --confirm-pilot
```

After apply, run collection dry-runs again before any Sheets write. Do not bulk-enable sources.

## Rules That Do Not Change

- `fetch_enabled=true` is currently 0 and that is correct until human pilot approval.
- YouTube/TikTok TODO placeholders must not be enabled.
- X fetch/post remains OFF.
- `beauty_account` remains inactive/draft-only.
- `third_party_reference_only` and `reference_only` are analysis only.
- Media pipeline is only for `owned`, `licensed`, or `approved_creator_clip`.
- AUTOPOST remains OFF.
- Generated queue rows must remain DRAFT or WAITING_REVIEW unless a separate human approval flow promotes them.

## Rollback

If pilot apply was run by mistake or needs to be reverted:

1. Set `fetch_enabled=false` on the pilot source rows.
2. Set `manual_only=true` again if the source should return to manual review.
3. Remove `pilot_enabled` / `pilot_enabled_at` fields or mark notes as rolled back.
4. Verify counts: `fetch_enabled=true` should return to 0 unless another approved pilot is running.
5. Re-run safety tests and `run_growth_loop.py --dry-run --account-id all`.

## Human Input Still Needed

- Real YouTube channel/video URL for `youtube_night_scout_reference_todo`.
- Real YouTube channel/video URL for `youtube_liver_reference_todo` if a second liver source is needed.
- Real TikTok individual `/video/` URL for `tiktok_night_scout_reference_todo`.
- Real TikTok individual `/video/` URL for `tiktok_liver_reference_todo`.
- Owned/licensed media evidence for `owned_media_assets_todo`: owner/creator, permission evidence, permission dates, allowed/prohibited uses, reviewer.

## AUTOPOST ON Conditions

AUTOPOST must stay OFF until all of these are true:

- Source pilot collection is stable and duplicate-safe.
- Metrics/posted_results loop is verified.
- Queue review and approval policy is passing.
- No reference-only media can enter media queue.
- Human explicitly approves production AUTOPOST gates.
