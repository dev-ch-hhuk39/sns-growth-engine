# Physical Golden evidence contract

The local verifier checks existing artifacts for Night Scout and Liver Manager.
It does not acquire media, call an understanding provider, upload an asset,
write a review or queue row, or publish. The opt-in `--use-sheets` flag reads
only the live media permission ledger through the existing protected runtime.
Do not transfer credentials or raw operational data to development machines.

A playable video plus a manifest description previously could appear understood;
independent author/ID substring searches could also pair unrelated artifacts.
The verifier now requires one active, nonretired, account-bound registered source,
positive extracted identity, one exact post filename and same-basename metadata
sidecar. X requires extracted status display ID and author, rejects quotes and
retweets, and permits the media ID to differ from the status ID. YouTube requires
an exact video ID and extracted uploader or registered channel identity. A
requested or echoed URL alone does not establish authorship. Registry duplicates
remain visible to strict verification instead of being silently deduplicated.

For `post_123.mp4`, the corresponding files are `post_123.info.json` and
`post_123.understanding.json`. Actual filenames must contain the complete post ID;
a profile handle or numeric ID prefix is insufficient. Ambiguous candidates,
missing metadata, linked artifacts, oversized input, changed files and probe
failure block the result. ffprobe is limited to 30 seconds. A technical PASS
requires actual positive audio/video streams, dimensions and finite duration.

The understanding JSON must be an existing, trusted, complete raw analysis in
this envelope (the identifiers and hashes below are placeholders):

```json
{
  "schema_version": 1,
  "account_id": "liver_manager",
  "source_id": "registered_source_id",
  "canonical_url": "https://x.com/registered_author/status/123",
  "external_post_id": "123",
  "media_asset_id": "ma_<first 24 characters of actual SHA256>",
  "content_hash": "<actual video bytes SHA256>",
  "analysis": {"status": "PASS", "visual_evidence": "<complete existing Gemini proof>"}
}
```

The abbreviated `analysis` above is explanatory and is not valid proof. Real
analysis must satisfy the existing `understand_media_contract`: approved Gemini
provider, HTTP 200, passing response schema, visual summary/action/key moment,
observed facts, UNDERSTOOD visual evidence, nonempty SHA256 frame hashes and the
same asset ID and actual video hash throughout. OCR-only, ASR-only, retired
provider evidence and summary/status-only legacy rows remain unverified. The
source-post hash derived from text/URLs is not the actual video file hash.

The current legacy `source_media_understanding` rows do not retain all raw visual
evidence fields. A PASS status in those rows cannot reconstruct missing proof.
This change does not alter the production Sheets schema. A local envelope also
cannot establish acquisition origin or the authenticity of arbitrarily fabricated
files; use retained trusted acquisition/analysis evidence and independent review.

The latest valid ledger row must explicitly bind the account and registered
handle, include rights evidence and all required operation flags, and remain
unrevoked/unexpired. Registration or public availability never grants reuse.
The existing caption composer is local and deterministic; it receives verified
observations. Its full generation gate and the media/text quality gate must pass
without relaxing thresholds. Complete results stop at WAITING_REVIEW and always
report publisher eligibility false. This verifier's PASS is not overall goal
acceptance, a READY transition or a publishing permit.

Run the verifier separately for X and YouTube against approved existing local
artifact directories. The default all-platform mode also retains the deferred
TikTok manifest entries and therefore cannot certify those physical artifacts.
Threads/TikTok metadata discovery remains available under the current owner
policy; new physical media remains deferred. Actual Golden acceptance still
requires real artifacts and current rights, not the synthetic regression fixtures.

## Validation and delivery

The reconstructed implementation is carried by PR #491. Full local regression
passed 1,104/1,104 repository scripts, isolated pytest 173/173 and workflow safety
619/619. New helper/integration tests total 47 and include actual local composer
success and quality rejection. Independent review, compile, fatal Ruff, diff and
working/history secret scans passed. Existing external/optional exclusions remain
unchanged. Synthetic fixture success is not actual Golden evidence.

PR #491 passed all four required checks and was merged as
`97f31b8cb580f6a098387a03602e27954b35c928`. The verifier was subsequently deployed
together with PR #492 as exact main `1bf36eb61c34c1c331d087900e75069616763678`,
after fresh complete encrypted-backup and independent health success. Actual
observation confirms a completed transaction, two read-only Sheets health
receipts, posting OFF, no pending candidate or rollback, preserved token-file/
marker metadata and dependency consistency. The prior f1a8d98 release is retained.

All 25 pure Golden tests and 28 durable-store tests also passed once under the
installed Linux runtime, with temporary synthetic fixtures and no protected
settings loaded. This is runtime verification, not actual Golden acceptance.
The latest read-only resource check still shows about 2GiB total host memory,
below the existing 4GiB total / 1.5GiB available media-preparation floors.
Capacity management remains with the owner's separate work; retention and
resource floors were not changed. Actual approved source artifacts, human
review/READY reserves, schedule integration and publishing/observation acceptance
remain open. No real media acquisition, generation, upload, production Sheets
mutation or SNS publication was invoked by this rollout.
