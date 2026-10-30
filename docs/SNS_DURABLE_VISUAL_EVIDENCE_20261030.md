# Durable visual evidence for the current owner accounts

The direct ingest path previously saved summaries, transcripts and status in
`source_media_understanding`, while losing full visual evidence, provider HTTP
and schema results, observed facts and asset binding. Its local media workspace
is removed after each preparation run. A later strict caption check could not
reconstruct VISUAL_VERIFIED from the saved row.

Existing complete analysis for Night Scout/Liver Manager X/YouTube videos is
now retained in a private evidence directory under the explicitly configured
BUFFERED_RUNTIME_ROOT shared area. There is no home, Mac or default credential
lookup. Raw video is still removed by the existing cleanup. No production
Sheets column or schema is added, and existing summary rows remain compatible.

Receipts bind the account, registered source/profile, exact parent and media
IDs, media index, native post identity, independently bound asset ID and actual
video SHA256. Full Gemini evidence must satisfy the existing strict semantic
contract. OCR/ASR-only and legacy summary/status rows cannot create a receipt.
Readers verify the current context, byte hashes, registry and semantic evidence
again; current rights gates remain independent and may revoke eligibility.

The runtime/shared directories must already be trusted and owned by the runtime
user; the new evidence directory is 0700 and files/lock are 0600. Descriptor
based access rejects links, ownership/mode changes, malformed/oversized data and
concurrent changes. Atomic no-replace publication plus fsync retains unknown
outcomes; existing identical receipts may be reused, while conflicting receipts
are never overwritten. A nonblocking lock serializes writers. Storage is capped
at 64MiB and 512 receipts. Unknown files, a full store or a busy lock block new
writes; no retention deletion, cache cleanup or threshold relaxation is added.

Uploaded-asset hash disagreement now blocks before another analysis or summary
write. Existing legacy assets need an explicitly requested understanding refresh
to obtain missing raw proof. The optional --refresh-visual-evidence flag requires
one exact --source-post-media-id and a current managed account; normal apply
confirmation and operation/rights gates still apply. It inspects only the
existing stored video, uses its existing asset ID, checks private storage before
a provider operation, and avoids another call when valid proof already exists.
The flag is never selected automatically by schedules. Dry-run remains offline.
This implementation did not execute a real refresh or call any provider.

Direct selection restores validated complete analysis over the legacy summary,
then passes it through existing strict content checks. A revoked or missing
owner permission row cannot fall back to older source policy. A BLOCKED ingest
result is a failed result, never a counted successful asset. The current owner
policy still stops candidates for human review and keeps posting OFF.

The receipt store does not retain raw media or extracted downloader metadata,
and therefore is not itself an actual Golden bundle. Real Golden evidence,
current rights, human review/READY reserves, schedules and actual publishing/
observation remain separate acceptance requirements. No goal status is edited
by these offline tests or source changes.

## Rights and binding verification

The current ledger must explicitly bind the account and known author. Missing or
revoked grants do not fall back to older source policy. The caption path discards
its cached permission snapshot and reads current grants for each candidate before
a provider call. Actual owner video ingest reads current grants immediately
before downloading and again immediately before analysis; analysis additionally
requires allow_analysis. Read failures or revoked/mismatched grants stop the
operation before the provider, proof persistence, summary write or upload.

Independent child, asset and understanding hashes must agree before rows are
combined. Stored URLs and asset IDs cannot contradict one another. The asset
row cannot overwrite a child's account, parent, source, index, native URL or byte
hash to conceal a conflict. These checks preserve existing rights and content
thresholds; historical regression fixtures now explicitly supply valid account
and author grants while retaining their original assertions.

Focused verification passed 62 new tests (store 28, operation permissions 12,
pipeline 17, CLI 5) and all 65 Direct scripts. Full repository regression 1,108/1,108, isolated pytest 173/173 and workflow
safety 619/619 also passed. Existing eight external and three optional exclusions
remain unchanged. Compile, fatal Ruff, diff and working/history secret scans passed. No live operation or formal acceptance is
implied by these synthetic fixtures.

The source implementation is ec217b2; the validation follow-up changes only
documentation. Source/config/scripts remain exactly equal to that tested commit.
The administrator disk preflight subsequently passed after separate owner
capacity work. Runtime promotion remains a separate exact-revision transaction
requiring fresh backup and health evidence, posting OFF and unchanged-current
guards. This does not satisfy the heavier real-media resource/rights/review gates.
