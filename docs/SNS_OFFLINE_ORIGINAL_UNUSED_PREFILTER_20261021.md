# SNS Growth Engine | Offline original catalogue prevalidation filter (2026-10-21)

## Source evidence

While trying to recover missing next-slot READY for Night Scout and Liver Manager without paid AI or real posts, all four reference/PDCA slot offline-original plan-only generations returned QUALITY_EXHAUSTED. The read-only 4-slot trial took approximately 346 seconds on the shared VPS. No paid AI calls, Sheets writes or posts occurred.

Source inspection showed that offline_original_catalog._prepared_candidates(account_id) applied each candidate's expensive final text validator, hard safety/quality gate, score and ranking **before** select_original() filtered out candidates already used in historical queue and posts. This re-ran for isolated per-slot generation workers.

The live immutable catalog contained 174 entries for Night Scout and 226 for Liver Manager. Exact normalized preliminary history filtering showed only 37 / 85 respectively were not already used. These counts do not imply that those candidates meet safety, novelty, owner review or publisher checks.

## Safe optimization

- Pass the existing exact-normalized previously used-text set into _prepared_candidates().
- After the same deterministic style repair, drop items that are *already unselectable* by select_original() before running the expensive validator and quality ranking. The selection-time exact-used check is deliberately retained.
- All remaining candidates continue through unchanged final public text validator, content-v2 hard gate, generation-quality evaluation, candidate ranking, similarity check, persisted original-catalog evidence, AI and owner approval gates.
- No change to the original catalog text, model version, safeguards, scoring thresholds, Sheets mutations or external posting.
- Keep optional default exclusion empty for legacy callers; in-process lru_cache(maxsize=3) stores no persistent text outside RAM.

## Tests and operational guard

Five synthetic no-network tests prove that used items do not hit expensive validators, while unused content still passes the exact same quality/hard gates and default API remains compatible. Existing 18 offline reserve, 4 owner-review and 9 paid-provider budget regression tests also PASS. GitHub CI/security audit is mandatory before merge.

This reduces avoidable compute for used candidates; it does **NOT** promise that any remaining catalogue item will pass novelty/quality. Four observed slots remain unfilled, and unresolved READY SLO is tracked Issue #441 and overall Issue #439. Do not create an extra approximately 700MiB immutable release solely for this optimization while protected previous releases are inside seven-day grace and shared VPS disk is around 80 percent.
