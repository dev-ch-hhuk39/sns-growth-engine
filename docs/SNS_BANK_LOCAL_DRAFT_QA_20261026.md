# Bank audit and local pending-draft QA — 2026-10-26

## Live Bank evidence

The owner explicitly authorized one execution of `/private/tmp/sns-bank-live-readonly-20261026.py` on `fukuri-vps`. The sandboxed, read-only audit completed at **14:32:00 JST** using the existing runtime's canonical inventory, public quality, Hybrid and publisher dry-run checks. The one-off unit was bounded to 420 seconds and 300MB. It returned only aggregates; no draft text, credential values or identifiers were printed.

| Account | Usable distinct entries | Canonical slot-effective | Minimum | Shortfall |
| --- | ---: | ---: | ---: | ---: |
| night_scout | 12 | 12 | 30 | 18 |
| liver_manager | 11 | 11 | 30 | 19 |
| beauty_account | 36 | 30 | 30 | 0 |

Beauty's effective count is capped by the canonical per-slot targets. The overall result is **INVENTORY_SHORTFALL**, not completion. This read was performed once: Sheets writes 0, paid AI calls 0, posts 0. Private receipt: `/private/tmp/sns-bank-live-readonly-result-20261026.json`. It does not establish current media reserve or actual publication.

## Reusable read-only local QA

`scripts/sns_local_ollama_draft_bank.py` now supports:

```sh
python3 scripts/sns_local_ollama_draft_bank.py --account night_scout --qa-only
python3 scripts/sns_local_ollama_draft_bank.py --account liver_manager --qa-only
```

These commands read the existing account-specific private pending file and apply the unchanged public-post validator, V2 hard gate and generation diversity/topic gates. Imported claims or approval fields cannot provide factual evidence. Only original-text, locally unverified, pending records with matching account/unique draft IDs are accepted. Private regular files are read with no symlink following and a size bound; a source-content change invalidates the result. Output contains indexes, fixed reason codes and counts, without private copy or draft IDs.

Individual checks compare local novelty while whole-batch checks also consider structure across every other candidate. A batch failure does not imply that every candidate is individually unusable. Neither result grants approval: global historical duplicates, slot joins and runtime publisher acceptance remain unchecked. The CLI exits 0 when the **audit completes**, even if every candidate fails; inspect the counts and `PENDING_HUMAN_QA` status. Generation mode is unchanged.

## Actual 48-draft result

The saved files under the owner's private Mac draft directory were audited at **14:45:05 JST**, without generation or editing:

| Account | Audited | Public checks pass | Hard gate pass | All individual local checks pass | Whole-batch checks pass |
| --- | ---: | ---: | ---: | ---: | ---: |
| night_scout | 24 | 2 | 20 | 1 | 0 |
| liver_manager | 24 | 4 | 24 | 0 | 0 |

Night failures included account/reader fit, insufficient scout perspective, first-person mismatch and unsupported high-risk claims. Liver failures included account/reader fit, missing next-stream actions and hook/conclusion topic mismatch. Both batches repeated structures. The one individual Night pass still needs factual/editorial review and all downstream gates; it is not a Bank entry. The 48 raw drafts cannot cover the accepted reserve shortfall of 37.

All sources were hash-checked unchanged. Canonical readiness remains false, READY promotions 0, model calls 0, Sheets writes 0, paid calls 0, posts 0. Private detailed receipt: `/private/tmp/sns-local-draft-formal-qa-20261026.json`; private text is deliberately excluded. No private draft data is committed.

## Verification and next work

Nine dedicated offline tests cover account/state boundaries, forged evidence, private storage, concurrent source change, output privacy and absence of generation/network/write calls. Four existing generation tests also pass. Both suites are included in the focused local quality gate; the repository runner discovers the new suite normally, without new exclusions.

Full local quality gate PASS: **1,093/1,093 repository scripts**, **619/619 workflow checks** across 64 workflows, fatal Ruff, compileall, staged/unstaged diff checks and branch-history Gitleaks. Existing 8 external probes and 3 optional local-tool probes remain excluded; no new exclusions. Redacted working-tree Gitleaks also PASS. Report: `/private/tmp/sns-bank-qa-quality-20261026.json`; logs: `/private/tmp/sns-bank-qa-quality-logs-20261026/`. These are local code checks, not production acceptance.

Reserve replenishment still requires quality revisions or new candidates through the existing approved routes, then independent duplicate/slot/approval/publisher checks and authorized writes with readback. No gate was relaxed. Liver token renewal separately awaits the owner-confirmed Threads App ID, which the owner cannot check until later. Keep the renewal utility inert and preserve all unknown-operation records. `docs/goal-status.json` is unchanged.
