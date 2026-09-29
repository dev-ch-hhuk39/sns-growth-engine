# Content Quality V2 Media-First Review

Draft only. Existing previews are read-only; no production writes or uploads.
Historical preview links do not establish current rights. Captions are withheld without verified visual evidence and permission.
MEDIA_FIRST_QUALITY_PROVEN=NO

## Execution limitations

- `MEDIA_VISION_CAPABILITY_BLOCKED=YES`: the existing GitHub Models vision provider is not enabled/authenticated in the current process. No credentials were displayed or changed.
- Six read-only preview requests failed with `ConnectionError` in the sandbox. The automatic permission review for network access timed out twice, including the single permitted retry. No frames were extracted.
- Historical preview URLs are retained below for manual inspection. None is presented as visually verified, rights-approved, or a completed media-caption package.
- Direct and Clip now prepare asset-bound context, relevance and angle before requesting a caption. An unavailable visual context withholds captions rather than substituting transcript claims.

## Verification and remaining limits

- Initial focused run: 16/16 behavioral tests passed, including both pipeline call orders.
- Single full repository run: 926/934 test scripts passed. Eight legacy media tests expected transcript-only/copyedit generation without visual evidence.
- After updating those contracts and adding verified asset fixtures, the permitted focused retry passed 10/10 scripts, including all eight failures, the 16 new behavioral tests and the existing V2 contract tests. The full suite was not repeated under the owner's test budget; a final all-green full-suite result is not claimed.
- Workflow safety: 522 PASS, 0 FAIL, 47 workflows.
- `DEGRADED_TO_TEXT` is emitted separately from media success. The existing text-candidate selector is tested, but automatic text-candidate replenishment is not added or exercised here; Text Engine and production are outside this task.
- Existing Sheets understanding rows without asset-bound frame evidence remain unverified. No evidence was manufactured from old captions, transcripts or frame counts.
- No publish, READY promotion, production Sheets write, upload, deploy or scheduler action was performed.

Changed code: `src/generation/content_quality_v2.py`, `src/generation/source_grounded_caption.py`,
`src/media/direct_content_understanding.py`, `scripts/run_direct_reference_media_pipeline.py`,
`scripts/run_media_production_pipeline.py`, `scripts/build_media_first_review_pack.py`,
`scripts/test_media_first_pipeline.py`, and the eight media regression tests listed by the full-suite failure report.

## night_scout / ma_395a948147c699033d0a5b28

MEDIA_PREVIEW: [video](https://res.cloudinary.com/dzvfpd3ma/video/upload/v1788422529/sns-growth/direct/395a948147c699033d0a5b2896c2bdd91011ef87b8f6999a6586ecc3ee3d24dc.mp4)
FETCH_STATUS: PREVIEW_UNAVAILABLE
REPRESENTATIVE_FRAME_EVIDENCE:
VISUAL_STATUS: VISUAL_UNVERIFIED
VISUAL_SUMMARY: UNVERIFIED
WHAT_VIEWER_SEES: UNVERIFIED
WHAT_VIEWER_HEARS: AUDIO_UNVERIFIED
WHY_THIS_ACCOUNT_SHOULD_POST_THIS: UNVERIFIED
POST_ANGLE_OPTIONS: NOT_GENERATED
SELECTED_ANGLE: NONE
MEDIA_ANCHOR: UNVERIFIED
PUBLIC_CAPTION: NOT_GENERATED
REMOVE_MEDIA_TEST: NOT_RUN
FABRICATED_EXPERIENCE_CHECK: NOT_RUN
RIGHTS/PERMISSION_STATUS: UNVERIFIED / UNVERIFIED
QUALITY_RANK: NOT_RANKED
WARNINGS: ConnectionError

## night_scout / ma_4b3066440b1323fec3e16227

MEDIA_PREVIEW: [video](https://res.cloudinary.com/dzvfpd3ma/video/upload/v1789461706/sns-growth/direct/4b3066440b1323fec3e16227886ed5039fcaaa6c3447b6dabf198e1e0df30072.mp4)
FETCH_STATUS: PREVIEW_UNAVAILABLE
REPRESENTATIVE_FRAME_EVIDENCE:
VISUAL_STATUS: VISUAL_UNVERIFIED
VISUAL_SUMMARY: UNVERIFIED
WHAT_VIEWER_SEES: UNVERIFIED
WHAT_VIEWER_HEARS: AUDIO_UNVERIFIED
WHY_THIS_ACCOUNT_SHOULD_POST_THIS: UNVERIFIED
POST_ANGLE_OPTIONS: NOT_GENERATED
SELECTED_ANGLE: NONE
MEDIA_ANCHOR: UNVERIFIED
PUBLIC_CAPTION: NOT_GENERATED
REMOVE_MEDIA_TEST: NOT_RUN
FABRICATED_EXPERIENCE_CHECK: NOT_RUN
RIGHTS/PERMISSION_STATUS: UNVERIFIED / UNVERIFIED
QUALITY_RANK: NOT_RANKED
WARNINGS: ConnectionError

## liver_manager / ma_2e698a351e98a14f6b4aa308

MEDIA_PREVIEW: [video](https://res.cloudinary.com/dzvfpd3ma/video/upload/v1787617972/sns-growth/direct/2e698a351e98a14f6b4aa30821f9b213f2616a9990f85e9848a2e45a49ff835b.mp4)
FETCH_STATUS: PREVIEW_UNAVAILABLE
REPRESENTATIVE_FRAME_EVIDENCE:
VISUAL_STATUS: VISUAL_UNVERIFIED
VISUAL_SUMMARY: UNVERIFIED
WHAT_VIEWER_SEES: UNVERIFIED
WHAT_VIEWER_HEARS: AUDIO_UNVERIFIED
WHY_THIS_ACCOUNT_SHOULD_POST_THIS: UNVERIFIED
POST_ANGLE_OPTIONS: NOT_GENERATED
SELECTED_ANGLE: NONE
MEDIA_ANCHOR: UNVERIFIED
PUBLIC_CAPTION: NOT_GENERATED
REMOVE_MEDIA_TEST: NOT_RUN
FABRICATED_EXPERIENCE_CHECK: NOT_RUN
RIGHTS/PERMISSION_STATUS: UNVERIFIED / UNVERIFIED
QUALITY_RANK: NOT_RANKED
WARNINGS: ConnectionError

## liver_manager / ma_6ef1a98162cac7c39187dd91

MEDIA_PREVIEW: [video](https://res.cloudinary.com/dzvfpd3ma/video/upload/v1785793953/sns-growth/direct/6ef1a98162cac7c39187dd91812e4bf8a5cbd6e194f92bcb0fe496b891183cc0.mp4)
FETCH_STATUS: PREVIEW_UNAVAILABLE
REPRESENTATIVE_FRAME_EVIDENCE:
VISUAL_STATUS: VISUAL_UNVERIFIED
VISUAL_SUMMARY: UNVERIFIED
WHAT_VIEWER_SEES: UNVERIFIED
WHAT_VIEWER_HEARS: AUDIO_UNVERIFIED
WHY_THIS_ACCOUNT_SHOULD_POST_THIS: UNVERIFIED
POST_ANGLE_OPTIONS: NOT_GENERATED
SELECTED_ANGLE: NONE
MEDIA_ANCHOR: UNVERIFIED
PUBLIC_CAPTION: NOT_GENERATED
REMOVE_MEDIA_TEST: NOT_RUN
FABRICATED_EXPERIENCE_CHECK: NOT_RUN
RIGHTS/PERMISSION_STATUS: UNVERIFIED / UNVERIFIED
QUALITY_RANK: NOT_RANKED
WARNINGS: ConnectionError

## beauty_account / ma_74b386ea406f8b9810a6d551

MEDIA_PREVIEW: [video](https://res.cloudinary.com/dzvfpd3ma/video/upload/v1787620594/sns-growth/direct/74b386ea406f8b9810a6d551b96ac154ff607e99655b9c0caa7f4a87c0afcec0.mp4)
FETCH_STATUS: PREVIEW_UNAVAILABLE
REPRESENTATIVE_FRAME_EVIDENCE:
VISUAL_STATUS: VISUAL_UNVERIFIED
VISUAL_SUMMARY: UNVERIFIED
WHAT_VIEWER_SEES: UNVERIFIED
WHAT_VIEWER_HEARS: AUDIO_UNVERIFIED
WHY_THIS_ACCOUNT_SHOULD_POST_THIS: UNVERIFIED
POST_ANGLE_OPTIONS: NOT_GENERATED
SELECTED_ANGLE: NONE
MEDIA_ANCHOR: UNVERIFIED
PUBLIC_CAPTION: NOT_GENERATED
REMOVE_MEDIA_TEST: NOT_RUN
FABRICATED_EXPERIENCE_CHECK: NOT_RUN
RIGHTS/PERMISSION_STATUS: UNVERIFIED / UNVERIFIED
QUALITY_RANK: NOT_RANKED
WARNINGS: ConnectionError

## beauty_account / ma_954ee8cae2824d9b6185d77c

MEDIA_PREVIEW: [video](https://res.cloudinary.com/dzvfpd3ma/video/upload/v1788769782/sns-growth/direct/954ee8cae2824d9b6185d77ca55018ad4f99c81859a991368dfa4991f4cf674e.mp4)
FETCH_STATUS: PREVIEW_UNAVAILABLE
REPRESENTATIVE_FRAME_EVIDENCE:
VISUAL_STATUS: VISUAL_UNVERIFIED
VISUAL_SUMMARY: UNVERIFIED
WHAT_VIEWER_SEES: UNVERIFIED
WHAT_VIEWER_HEARS: AUDIO_UNVERIFIED
WHY_THIS_ACCOUNT_SHOULD_POST_THIS: UNVERIFIED
POST_ANGLE_OPTIONS: NOT_GENERATED
SELECTED_ANGLE: NONE
MEDIA_ANCHOR: UNVERIFIED
PUBLIC_CAPTION: NOT_GENERATED
REMOVE_MEDIA_TEST: NOT_RUN
FABRICATED_EXPERIENCE_CHECK: NOT_RUN
RIGHTS/PERMISSION_STATUS: UNVERIFIED / UNVERIFIED
QUALITY_RANK: NOT_RANKED
WARNINGS: ConnectionError
