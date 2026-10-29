# Current owner reference and physical acquisition policy

The current owner rules in AGENTS.md take precedence over historical source
and media-capability records. This change applies the TikTok, Threads, X,
YouTube discovery order and limits Night/Liver physical acquisition to X and
YouTube. Threads/TikTok metadata discovery remains on the existing non-browser
routes; new physical acquisition is deferred for these two accounts.

Both registered-source selectors sort stably before their caller limits. For
all-account selection, only each managed account's existing positions are
reordered. The shared preference score follows the same canonical order.

Account policy is enforced before physical source scan budgets, at direct
download dispatch, both pending-media selectors, complete-parent direct and
clip/saved-clip candidate selection, clip-source acquisition and Golden
verification. Metadata-only discovery keeps the full reference platform set;
physical source planning excludes deferred platforms before bounded scans. The direct ingest entrypoint refuses deferred media
before existing-asset reads, reuse or stored-asset refresh. Clip-source policy
runs before cache lookup; X also verifies the exact registered status author
before accepting a cached source. Known platform/URL mismatches and relabelled
registered deferred sources are refused before acquisition. An explicit account cannot override a
conflicting parent account. Permission and availability remain independent:
valid source-specific ledger permission does not activate a deferred platform.

The existing source registry, historical permission attestations, current
permission-ledger writer, legacy helper implementations and other accounts'
physical-capability settings are retained. No permission is granted or revoked.
The account entrypoints pass their bound account explicitly. The current-owner
configuration and completion architecture checks verify the exact two-account
scope, acquisition order, physical providers and deferred platforms. Existing
acceptance thresholds, geometry, review/publisher gates and route mix remain.
No formal goal-status artifact was edited.

New offline coverage exercises actual source selection, permission-approved
and cached-source refusal, X cached-author denial, both pending selectors,
complete-parent selection, early direct ingest, account mismatch and Golden
refusal before media probing or text generation. Existing cooldown/recovery
contracts are also retained for the legacy capability; current-owner cases
assert that cooldown expiry cannot reopen a deferred platform. The generic
Hybrid-blocked candidate fixture now uses an eligible YouTube source so it
continues testing candidate failover. Focused owner-policy21 and direct-media48
regressions pass. Full Mac validation passes 1,102/1,102 repository scripts,
619/619 workflow safety checks, 173/173 isolated pytest cases, fatal Ruff,
compile, diff and secret scans.
Existing eight external and three optional exclusions remain unchanged.
Inventory-aware clip rotation is verified with eligible YouTube sources.
Pytest retains legacy HTTP/author/CDN behavior and additionally verifies both
current accounts refuse deferred platforms before cache/network access even
with valid permission; revoked permission still denies independently.
Validation is recorded in the handoff.

No production acquisition, generation, upload, write, timer change or publication
was invoked by this source batch. The policy has not yet been deployed. Actual
rights, X/YouTube Golden evidence, human review/READY reserves and production
acceptance remain independent requirements.
