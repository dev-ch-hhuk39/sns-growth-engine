# SNS Growth Engine | encrypted R2 backup and isolated VPS cleanup

2026-10-22 evidence (Japan Standard Time). This document controls SNS-only
operations; it is not permission to modify the shared VPS's other services.

## Authoritative persistent recovery locations

- SNS SQLite P0: AgentOps root-managed daily client-encrypted Restic backup
  to the existing private shared R2 repository, tagged
  tool:sns-growth-engine,sns-p0-sql.
- SNS runtime recovery configuration, initial SQLite image and token tree:
  tagged tool:sns-growth-engine,sns-recovery-files.
- SNS Google Sheets master: its live source of truth remains Google Sheets.
  Root-managed exporter captures values, formulas, and bounded native
  structures into R2, tagged tool:sns-growth-engine,sns-sheet-master.
- SNS-owned work/media: part of existing AgentOps
  chadult,all-tools,media snapshots under /var/lib/sns-growth-engine/work.
- Existing central AgentOps R2 job and timer are the only owner of offsite
  backup writes. Do not create an SNS-specific duplicate timer, repository,
  credentials, bucket, or local dump. Do not touch backups of other tools.

Latest verified independent Mac R2 readbacks: P0 logical SQLite and initial
image each restore four application tables; recovery config passes with
24 structural keys. Google Sheets R2 snapshot validates 59 tabs, 104
value/formula segments and native structure v2. Full disposable Google
Sheets workbook rebuild, token payload parity and second independent device
credential escrow are separate acceptance criteria.

## Data which must remain on the VPS

Current running immutable release; previous rollback release; independent
bootable emergency release; pending staged release (when any); private live
runtime configuration; active token/SQLite/runtime state; active scheduling
and their locks. This data cannot simply be deleted because an encrypted
copy also exists in R2.

Old immutable releases have a minimum seven-day age hold plus exact SHA,
SNS owner marker, shared deploy lock, all-process open-file scan, protected
pointer and independent emergency constraints. Only the already reviewed
SNS-specific pruner may remove individually approved eligible SHA targets.
The other services and shared Docker volumes are out of scope.

The dedicated SNS Runner Python setup-python toolcache is about 597MB,
but THREE retained release pyvenv.cfg files still point at it. The
existing cleanup guard therefore blocks its deletion, correctly. The SNS
Whisper model cache is also required for media cold-start/reliability; it is
not an obsolete backup and must not be indiscriminately deleted.

## Reinstallable old SNS diagnostics

Only Chrome files with a UUID-based .dmp or .meta basename inside
/var/lib/sns-growth-engine/.config/google-chrome/Crash Reports/completed
may expire after 14 days, through the owner-checked, global-lock,
no-active-Chrome process guard. No current browser profile, video model,
media, backups, databases, tokens, other projects or immutable releases may
be deleted. The main-only SNS workflow audits before running this bounded
weekly cleanup. First audited, manual one-time cleanup on 2026-10-22
removed 2,396 old telemetry files and increased free space by 76,775,424
bytes; no current runtime or external backup was changed.

## Capacity and R2 constraints

At the 2026-10-22 read-only audit the SNS release set contained eleven
directories (6,827,139,072 allocated bytes), and no release was seven-day
eligible for exact-SHA cleanup. The shared VPS disk was at 81% by df;
SNS media preparation has a hard 80% usage cutoff. Do not lower that
safety cutoff to make a deployment appear successful.

Independent R2 repository statistics (read-only/no-lock) returned
3,416,455,030 raw-data bytes against the existing local admin policy
of 5,000,000,000 bytes. This is a company-imposed safety stop, not a claim
about Cloudflare's free-plan quota. Shared repository retention or
increasing the cap affects other tools and requires separate owner
authorization. Backups cannot honestly be guaranteed forever under a
fixed quota without continued monitoring and capacity policy.

Any unproven cleanup target remains protected. Report blocked gates rather
than touching data owned by another service.
