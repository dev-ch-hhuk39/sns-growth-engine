# Strict legacy text READY isolation — 2026-10-19

## Scope

This change decouples the **legacy text-only** generator opt-in from Content Quality V2 editorial draft-only enforcement. It does not enable live Threads publishing, bypass human review of V2 drafts or authorize media reuse.

## Preconditions

- Both `config/content_quality_v2.json` and `config/autonomous_mode.json` must exist, parse and satisfy the explicit isolation policy.
- V2 remains `draft_only=true` and `publishing_enabled=false`.
- Text account must be one of `night_scout`, `liver_manager`, `beauty_account`; platform stays Threads-only and X is blocked.
- Autonomous prepare/READY flags must be enabled while kill switch, unsafe media and unknown rights remain disabled.
- Quality threshold floors and risk/similarity ceilings cannot be weakened.
- `--autonomous-text-generation` requires `--apply --confirm-generate` and `--source references`. Default generation continues to fail closed as `DRAFT_ONLY`.
- The generated queue begins `WAITING_REVIEW`, never `READY` or `POSTED`; its exact ID must separately pass existing Hybrid AI and auto-approval, including final public-text validation, identity, duplicates, rights/media isolation, account-fit, budget and validation safeguards.

## Intended automatic recovery

The bounded `scripts/maintain_text_ready_inventory.py` route calls legacy generation with the opt-in. Publication authority still resides in the separately signed, locked and guarded VPS publisher. No legacy GitHub direct-post workflow is reenabled.

## Validation and limits

Local regression: `python3 scripts/test_autonomous_text_ready_isolation.py`; existing gate/owner-review tests; `python3 scripts/run_local_quality_gate.py --mode focused|full`. The offline tests do not establish successful production Sheets writes, eligible READY coverage, user-visible posts, media provenance or end-to-end metrics. Treat these as pending until independent live evidence exists. No GitHub Actions should be re-run only to disguise failing external systems.

## Deployment conditions

Verify green required CI, VPS capacity >=9GiB before staging and >=8GiB after staging, backup and restore, immutable `current`/`previous`/`pending` pointers and unreferenced process proof, lock ownership, and no cross-service changes. Start with real posting OFF; do not touch unrelated services or perform global deletion. No production release or canary may be claimed from this local QA alone.
