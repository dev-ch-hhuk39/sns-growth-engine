# End-to-end scheduled Threads autopost

## Daily operational mix for both accounts

Each account has five canonical daily slots:

- 20% fully new text
- 20% reference-derived text
- 20% PDCA-derived text
- 20% directly permitted reference media
- 20% newly produced approved-source clip media

Source-preserving copyedit is available only when the persisted permission and
caption policy explicitly allow it. Reference-only sources remain structurally
rewritten and cannot reuse third-party media.

## Runtime chain

1. Prepare one slot-specific candidate.
2. Keep or normalize it to `WAITING_REVIEW`.
3. Review only the newest exact `slot_id` candidate with the budgeted Gemini gate.
4. Promote only the exact reviewed `queue_id` to `READY`.
5. Recheck production activation, rights, permissions, evidence, limits and kill switch.
6. Publish only that exact queue ID.
7. Persist slot completion, posted result, metrics jobs and health evidence.

The previous generic Gemini schedules are manual-only after this rollout, so
they cannot consume the daily request budget ahead of the ten exact slots.

## Pre-activation migration

All legacy `READY` and `WAITING_REVIEW` rows for Night Scout and Liver Manager
are archived and excluded before activation. The migration verifies that
`posted_results` remains unchanged.
